# Phân tích Backend cho Frontend — Booking AI System

> Tài liệu này được viết dựa trên việc đọc trực tiếp mã nguồn backend tại `booking-ai-system-be`.
> Mọi kết luận đều có dẫn chiếu file và dòng code cụ thể. Không suy diễn tên field.
> Mục tiêu: làm căn cứ xây dựng frontend quản trị (Next.js App Router, feature-based).

---

## 0. Tóm tắt nhanh cho frontend

- Base URL API: prefix `/api` (public) và `/api/admin` (có auth). Xem `app/main.py:78-91`.
- **Auth admin**: mọi endpoint `/api/admin/*` yêu cầu header `Authorization: Bearer <Supabase JWT>`. Xem `app/core/auth.py:48-57` (`require_admin`).
- Admin được xác định bằng **email whitelist** (`ADMIN_EMAILS` trong `app/core/config.py:35`), **không phải role**. Backend chỉ đọc `email` từ JWT payload.
- Format lỗi đồng nhất RFC 9457 Problem Details (`app/core/exceptions.py`, `app/main.py:31-66`).
- Mọi response thành công được bọc trong `{ "data": ... }` (hoặc `{ "data": [...], "meta": {...} }` với list).
- **Decimal (price) serialize thành STRING** trong JSON. UUID/time/date/datetime serialize theo ISO.
- **Timezone: backend KHÔNG xử lý múi giờ cho booking.** `start_time`/`end_time`/`work_date` chỉ là `Time`/`Date` naive. Xem §9.
- **Booking qua nửa đêm: ngày bị mất, chỉ giữ giờ:phút.** Xem §9.

---

## 1. Sơ đồ Entity & Quan hệ Database

Tất cả PK là `UUID` (default `uuid4`). Mọi model (trừ `Reservation`, `ReservationCourse`) kế thừa `TimestampMixin` (`app/db/mixins.py:10-17`) → có `created_at`, `updated_at` (`DateTime(timezone=True)`, server default `now()`).

### 1.1 Bảng & cột

| Bảng | Cột chính | Ghi chú |
|---|---|---|
| `shops` (`app/db/models/shop.py:14`) | `shop_id` PK, `shop_code` unique, `pos_shop_code` unique, `name`, `address?`, `phone?`, `is_active` (default true) | — |
| `courses` (`app/db/models/course.py:15`) | `course_id` PK, `shop_id` FK, `pos_course_code`, `name`, `duration_minutes`, `price` Numeric(10,2), `course_type` ('main'/'addon'), `is_active` | unique `(shop_id, pos_course_code)` |
| `therapists` (`app/db/models/therapist.py:14`) | `therapist_id` PK, `shop_id` FK, `pos_therapist_code`, `name`, `gender` ('male'/'female'), `is_active` | unique `(shop_id, pos_therapist_code)` |
| `therapist_shifts` (`app/db/models/therapist_shift.py:14`) | `shift_id` PK, `therapist_id` FK, `shop_id` FK, `work_date` Date, `start_time` Time, `end_time` Time, `is_active` | — |
| `customers` (`app/db/models/customer.py:14`) | `customer_id` PK, `phone` unique, `name?`, `pos_customer_code?`, `is_member` (default false), `member_rank?`, `visit_count` (default 0), `last_synced_at?` | — |
| `customer_restrictions` (`app/db/models/customer_restriction.py:14`) | `restriction_id` PK, `phone`, `reason?`, `is_active` | partial unique `(phone) WHERE is_active=true` — 1 restriction active/phone |
| `bookings` (`app/db/models/booking.py:14`) | `booking_id` PK, `shop_id` FK, `customer_id` FK, `pos_booking_code?` (DEPRECATED, unique), `pos_sync_status` (DEPRECATED, default 'pending'), `booking_date` Date, `start_time` Time, `end_time` Time, `number_of_people` (1-3), `total_duration_minutes`, `status` (default 'confirmed'), `therapist_request_type` (default 'none'), `requested_therapist_id` FK?, `requested_gender?`, `idempotency_key` UUID unique NOT NULL, `cancel_reason?`, `cancelled_at?` | — |
| `reservations` (`app/db/models/reservation.py:14`) | `reservation_id` PK, `booking_id` FK, `person_index` (1-3), `therapist_id` FK, `start_time` Time, `end_time` Time, `status` (default 'assigned') | **KHÔNG có TimestampMixin** |
| `reservation_courses` (`app/db/models/reservation_course.py:14`) | `reservation_course_id` PK, `reservation_id` FK, `course_id` FK, `course_role` ('main'/'addon'), `duration_snapshot` int, `price_snapshot` Numeric(10,2), `course_name_snapshot`, `created_at` | **KHÔNG có TimestampMixin** (chỉ `created_at`) |

### 1.2 Quan hệ Foreign Key (căn cứ: các file `app/db/models/*.py`)

```
shops 1───* courses            (courses.shop_id → shops.shop_id)
shops 1───* therapists         (therapists.shop_id → shops.shop_id)
shops 1───* therapist_shifts   (therapist_shifts.shop_id → shops.shop_id)
shops 1───* bookings           (bookings.shop_id → shops.shop_id)

therapists 1───* therapist_shifts   (therapist_shifts.therapist_id → therapists.therapist_id)
therapists 1───* reservations       (reservations.therapist_id → therapists.therapist_id)

customers 1───* bookings        (bookings.customer_id → customers.customer_id)
therapists 1───? bookings.requested_therapist_id  (bookings.requested_therapist_id → therapists.therapist_id)

bookings 1───* reservations     (reservations.booking_id → bookings.booking_id)
courses  1───* reservation_courses (reservation_courses.course_id → courses.course_id)
reservations 1───* reservation_courses (reservation_courses.reservation_id → reservations.reservation_id)

customer_restrictions: KHÔNG có FK, join bằng `phone` ở service layer.
```

### 1.3 ERD (text)

```
+----------------+       +-------------------+       +---------------------+
|     shops      | 1   * |      courses      |       |     therapists      |
+----------------+-------+-------------------+   1 * +---------------------+
| shop_id (PK)   |------>| course_id (PK)    |       | therapist_id (PK)   |
| shop_code (UQ) |       | shop_id (FK)      |       | shop_id (FK)        |
| pos_shop_code  |       | pos_course_code   |       | pos_therapist_code  |
| name           |       | name              |       | name                |
| address?       |       | duration_minutes  |       | gender (male/female)|
| phone?         |       | price (DECIMAL)   |       | is_active           |
| is_active      |       | course_type       |       +----------+--------+
+----------------+       | is_active         |                  | 1
        | 1              +-------------------+                  | *
        | *                                               *    |
        |          +---------------------+       +-----------*-+---------+
        |          |  therapist_shifts   |       |    bookings           |
        +--------->| shift_id (PK)       |       +-----------------------+
        |          | therapist_id (FK)   |<*-----| booking_id (PK)       |
        |          | shop_id (FK)        |       | shop_id (FK)          |
        |          | work_date (Date)    |       | customer_id (FK)      |
        |          | start_time (Time)   |       | booking_date (Date)   |
        |          | end_time (Time)     |       | start_time (Time)     |
        |          | is_active           |       | end_time (Time)       |
        |          +---------------------+       | number_of_people (1-3)|
        |                                         | total_duration_min.. |
        |  +------------------+                   | status               |
        |  |     customers     | 1  *            | therapist_request_type|
        +--| customer_id (PK)  |----->| requested_therapist_id (FK?)   |
           | phone (UQ)        |      | requested_gender?      |
           | name?             |      | idempotency_key (UQ)   |
           | is_member         |      | cancel_reason?        |
           | member_rank?      |      | cancelled_at?         |
           | visit_count       |      +----------+------------+
           +------------------+                 | 1
                                               *|                     +---------------------+
                                          +----*------+              |   reservations       |
                                          | bookings   | 1         *| +---------------------+
                                          +-----------+------------>| reservation_id (PK)  |
                                                                   | booking_id (FK)      |
                                                                   | person_index         |
                                                                   | therapist_id (FK)    |
                                                                   | start_time (Time)    |
                                                                   | end_time (Time)      |
                                                                   | status (assigned)    |
                                                                   +----------+----------+
                                                                              | 1
                                                                              *|        +-------------------------+
                                                                           +--*------->|  reservation_courses    |
                                                                           |          +-------------------------+
                                                                           |          | reservation_course_id PK|
                                                                           |          | reservation_id (FK)     |
                                                                           |          | course_id (FK)         |
                                                                           |          | course_role            |
                                                                           |          | duration_snapshot      |
                                                                           |          | price_snapshot (DEC)  |
                                                                           |          | course_name_snapshot   |
                                                                           |          +-------------------------+
                                                                           |
                                                                   +-------*--+  +---------------------+
                                                                   |  courses  |  | customer_restrictions|
                                                                   +-----------+  +---------------------+
                                                                                  | restriction_id (PK)  |
                                                                                  | phone                |
                                                                                  | reason?              |
                                                                                  | is_active            |
                                                                                  +---------------------+
```

---

## 2. Danh sách API Frontend có thể dùng

### 2.1 PUBLIC (không cần auth)

| Method | Path | Dùng cho |
|---|---|---|
| GET | `/api/shops` | Danh sách shop (public) |
| GET | `/api/shops/{shop_id}` | Chi tiết shop |
| GET | `/api/shops/{shop_id}/courses` | Course của shop |
| GET | `/api/shops/{shop_id}/available-slots` | Khung giờ trống |
| GET | `/api/shops/{shop_id}/available-therapists` | Therapist khả dụng trong khung giờ |
| POST | `/api/booking-eligibility-checks` | Kiểm tra SĐT có được đặt không + thông tin khách |
| POST | `/api/bookings` | Tạo booking (cần header `Idempotency-Key`) |
| GET | `/api/bookings` | Tra cứu booking (cursor pagination) |
| GET | `/api/bookings/{booking_id}` | Chi tiết booking |
| PATCH | `/api/bookings/{booking_id}` | Sửa ngày/giờ hoặc huỷ (`status: "cancelled"`) |
| GET | `/api/bookings/{booking_id}/reservations` | Danh sách reservation của booking |
| GET | `/api/therapists/me/schedule` | Lịch therapist theo ngày (cần `date` + `therapist_id`) |

### 2.2 ADMIN (cần `Authorization: Bearer <Supabase JWT>`, email trong `ADMIN_EMAILS`)

| Method | Path | Dùng cho |
|---|---|---|
| GET | `/api/admin/shops` | Quản lý shop |
| POST | `/api/admin/shops` | Tạo shop |
| GET | `/api/admin/shops/{shop_id}` | Chi tiết shop (admin) |
| PATCH | `/api/admin/shops/{shop_id}` | Sửa shop |
| GET | `/api/admin/shops/{shop_id}/courses` | Course của shop (admin) |
| POST | `/api/admin/shops/{shop_id}/courses` | Tạo course |
| GET | `/api/admin/courses/{course_id}` | Chi tiết course |
| PATCH | `/api/admin/courses/{course_id}` | Sửa course |
| GET | `/api/admin/shops/{shop_id}/therapists` | Therapist của shop |
| POST | `/api/admin/shops/{shop_id}/therapists` | Tạo therapist |
| GET | `/api/admin/therapists/{therapist_id}` | Chi tiết therapist |
| PATCH | `/api/admin/therapists/{therapist_id}` | Sửa therapist |
| GET | `/api/admin/shops/{shop_id}/therapist-shifts` | Ca làm việc (filter `work_date`, `therapist_id`, `is_active`) |
| POST | `/api/admin/therapist-shifts` | Tạo ca |
| GET | `/api/admin/therapist-shifts/{shift_id}` | Chi tiết ca |
| PATCH | `/api/admin/therapist-shifts/{shift_id}` | Sửa ca |
| GET | `/api/admin/customer-restrictions` | Danh sách restriction (filter `phone`, `is_active`) |
| POST | `/api/admin/customer-restrictions` | Tạo restriction (cấm SĐT) |
| GET | `/api/admin/customer-restrictions/{restriction_id}` | Chi tiết restriction |
| PATCH | `/api/admin/customer-restrictions/{restriction_id}` | Sửa restriction |
| GET | `/api/admin/bookings` | Quản lý booking (cursor pagination, filter `shop_id`, `booking_date`, `status`, `phone`, `pos_booking_code`) |
| GET | `/api/admin/bookings/{booking_id}` | Chi tiết booking (admin, có thông tin customer + shop) |

---

## 3. Request & Response của từng API

> Quy ước: mọi UUID/time/date/datetime serialize thành string ISO. `price`/`price_snapshot` (Numeric) serialize thành **string**. Response thành công bọc trong `data` (hoặc `data`+`meta`).

### 3.1 Shops

**GET `/api/shops`** (`app/api/public/shops.py:15`)
- Query: `is_active: bool | None` (mặc định `True` nếu không truyền).
- Response:
```json
{ "data": [ { "shop_id": "uuid", "shop_code": "str", "name": "str", "address": "str|null", "phone": "str|null" } ], "meta": { "total": 0 } }
```
(PublicShopResponse — `app/schemas/shop.py`)

**GET `/api/shops/{shop_id}`** (`app/api/public/shops.py:36`)
- 404 `SHOP_NOT_FOUND` nếu sai.
- Response: `{ "data": PublicShopResponse }`.

**GET `/api/shops/{shop_id}/courses`** (`app/api/public/shops.py:47`)
- Query: `course_type: str|None` (`main`/`addon`), `is_active: bool|None` (mặc định `True`).
- Response: `{ "data": [PublicCourseResponse] }`.
- PublicCourseResponse: `{ "course_id", "shop_id", "name", "duration_minutes": int, "price": "string(Decimal)", "course_type": "main|addon" }`.

**Admin:**

`POST /api/admin/shops` (`app/api/admin/shops.py:28`) — 201
- Body `ShopCreate`: `{ "shop_code": str, "pos_shop_code": str, "name": str, "address"?: str, "phone"?: str, "is_active"?: true }`.
- Response: `{ "data": AdminShopResponse }`.
- AdminShopResponse thêm: `shop_id`, `created_at`, `updated_at`, `is_active`.

`GET /api/admin/shops` (`app/api/admin/shops.py:14`): `{ "data": [AdminShopResponse], "meta": { "total": int } }`.

`PATCH /api/admin/shops/{shop_id}` (`app/api/admin/shops.py:45`): body `ShopUpdate` (mọi field optional): `{ "name"?: str, "address"?: str, "phone"?: str, "is_active"?: bool }`.

### 3.2 Courses (admin)

`POST /api/admin/shops/{shop_id}/courses` (`app/api/admin/courses.py:28`) — 201
- Body `CourseCreate`: `{ "pos_course_code": str, "name": str, "duration_minutes": int (>=15, bội 15), "price": "string|number(Decimal>=0)", "course_type": "main|addon", "is_active"?: true }`.
- Response: `{ "data": AdminCourseResponse }`.
- AdminCourseResponse: thêm `course_id`, `shop_id`, `created_at`, `updated_at`, `is_active`. `price` là string.

`PATCH /api/admin/courses/{course_id}` (`app/api/admin/courses.py:46`): `CourseUpdate` — field optional, ràng buộc như trên.

`GET /api/admin/shops/{shop_id}/courses` (`app/api/admin/courses.py:14`): filter `course_type?`, `is_active?` → `{ "data": [AdminCourseResponse] }`.

### 3.3 Therapists (admin)

`POST /api/admin/shops/{shop_id}/therapists` (`app/api/admin/therapists.py:29`) — 201
- Body `TherapistCreate`: `{ "pos_therapist_code": str, "name": str, "gender": "male|female", "is_active"?: true }`.
- Response: `{ "data": TherapistResponse }` (`therapist_id`, `shop_id`, `pos_therapist_code`, `name`, `gender`, `is_active`, `created_at`, `updated_at`).

`PATCH /api/admin/therapists/{therapist_id}` (`app/api/admin/therapists.py:47`): `TherapistUpdate` (`name?`, `gender?: male|female`, `is_active?`).

### 3.4 Therapist Shifts (admin)

`GET /api/admin/shops/{shop_id}/therapist-shifts` (`app/api/admin/therapist_shifts.py:16`)
- Query: `work_date?: "YYYY-MM-DD"`, `therapist_id?: uuid`, `is_active?: bool`.
- Response: `{ "data": [ShiftResponse] }` (không có `meta`).
- ShiftResponse: `{ "shift_id", "shop_id", "therapist_id", "work_date": "YYYY-MM-DD", "start_time": "HH:MM:SS", "end_time": "HH:MM:SS", "is_active", "created_at", "updated_at" }`.

`POST /api/admin/therapist-shifts` (`app/api/admin/therapist_shifts.py:43`) — 201
- Body `ShiftCreate`: `{ "shop_id": uuid, "therapist_id": uuid, "work_date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM", "is_active"?: true }`.
- Response: `{ "data": ShiftResponse }`.

`PATCH /api/admin/therapist-shifts/{shift_id}` (`app/api/admin/therapist_shifts.py:60`): `ShiftUpdate` (`start_time?`, `end_time?`, `is_active?`).

### 3.5 Customer Restrictions (admin)

`GET /api/admin/customer-restrictions` (`app/api/admin/customer_restrictions.py:18`)
- Query: `phone?: str`, `is_active?: bool`.
- Response: `{ "data": [RestrictionResponse], "meta": { "total": int } }`.
- RestrictionResponse: `{ "restriction_id", "phone", "reason": str|null, "is_active", "created_at", "updated_at" }`.

`POST /api/admin/customer-restrictions` (`app/api/admin/customer_restrictions.py:33`) — 201
- Body `RestrictionCreate`: `{ "phone": str, "reason"?: str, "is_active"?: true }`.
- Response: `{ "data": RestrictionResponse }`.

`PATCH /api/admin/customer-restrictions/{restriction_id}` (`app/api/admin/customer_restrictions.py:50`): `RestrictionUpdate` (`reason?`, `is_active?`).

### 3.6 Booking Eligibility (public)

`POST /api/booking-eligibility-checks` (`app/api/public/booking_eligibility.py:12`) — 201
- Body: `{ "phone": str, "shop_id": uuid }`.
- Nếu SĐT nằm trong NG list → **403 `CUSTOMER_IN_NG_LIST`** (không trả `restriction`).
- Response (`app/services/eligibility_service.py:34-48`, `app/schemas/booking.py:175`):
```json
{
  "data": {
    "check_id": "uuid",
    "phone": "str",
    "eligible": true,
    "customer": {
      "customer_type": "existing",
      "customer_id": "uuid-string",
      "name": "str|null",
      "is_member": false,
      "member_rank": "str|null",
      "visit_count": 0
    },
    "restriction": null
  }
}
```
- Nếu khách chưa tồn tại: `customer: null`, `eligible: true`.

### 3.7 Booking (public create / admin query)

`POST /api/bookings` (`app/api/public/bookings.py:21`) — 201
- **Header bắt buộc**: `Idempotency-Key: <uuid>` (thiếu/ sai format → 400 `MISSING_IDEMPOTENCY_KEY`). Xem `app/services/booking_service.py:176-186`.
- Body `BookingCreate` (`app/schemas/booking.py:31`):
```json
{
  "shop_id": "uuid",
  "booking_date": "YYYY-MM-DD",
  "start_time": "HH:MM",
  "number_of_people": 1,
  "customer": { "phone": "str", "name": "str|null" },
  "courses": [ { "course_id": "uuid", "course_role": "main|addon" } ],
  "therapist_request": { "type": "none|specific|gender", "therapist_id"?: "uuid", "gender"?: "male|female" },
  "confirmed_by_customer": true
}
```
- Response (`app/services/booking_service.py:155-173`) — **là dict inline, KHÔNG phải Pydantic schema**:
```json
{
  "data": {
    "booking_id": "uuid", "shop_id": "uuid", "customer_id": "uuid",
    "booking_date": "YYYY-MM-DD", "start_time": "HH:MM:SS", "end_time": "HH:MM:SS",
    "number_of_people": 1, "total_duration_minutes": 90, "status": "confirmed",
    "therapist_request_type": "none", "requested_therapist_id": "uuid|null", "requested_gender": "male|female|null",
    "cancel_reason": "null", "cancelled_at": "null",
    "created_at": "ISO datetime", "updated_at": "ISO datetime",
    "reservations": [
      {
        "reservation_id": "uuid", "person_index": 1, "therapist_id": "uuid",
        "start_time": "HH:MM:SS", "end_time": "HH:MM:SS", "status": "assigned",
        "courses": [
          { "course_id": "uuid", "course_role": "main", "course_name_snapshot": "str", "duration_snapshot": 90, "price_snapshot": "STRING(Decimal)" }
        ]
      }
    ]
  }
}
```
- Lỗi: 409 `SLOT_CONFLICT`, 403 `CUSTOMER_IN_NG_LIST`, 404 `SHOP_NOT_FOUND`/`COURSE_NOT_FOUND`/`THERAPIST_NOT_FOUND`, 422 `SHOP_INACTIVE`/`INVALID_COURSE_COMBO`/`ADDON_REQUIRES_MAIN_COURSE`/`GROUP_BOOKING_CANNOT_REQUEST_THERAPIST`/`INVALID_THERAPIST_DATA`/`THERAPIST_NOT_AVAILABLE`.

`GET /api/bookings` (`app/api/public/bookings.py:36`) — cursor pagination
- Query: `pos_booking_code?`, `phone?`, `shop_id?`, `booking_date?` (`YYYY-MM-DD`), `status?`, `limit?` (1-100, default 20), `cursor?` (uuid của item cuối trang trước).
- Response: `{ "data": [PublicBookingListItem], "meta": { "limit": int, "next_cursor": "uuid|null" } }`.
- PublicBookingListItem: `{ "booking_id", "shop_id", "booking_date", "start_time", "end_time", "number_of_people", "total_duration_minutes", "status" }`.

`GET /api/bookings/{booking_id}` (`app/api/public/bookings.py:74`): `{ "data": <full booking object như POST> }`.

`PATCH /api/bookings/{booking_id}` (`app/api/public/bookings.py:83`)
- Body `BookingPatchInput`: chỉ áp dụng `booking_date`, `start_time`. Nếu `status: "cancelled"` → gọi huỷ (`app/services/booking_service.py:109-110`).
```json
{ "status": "cancelled", "cancel_reason": "str|null" }
```
- Response: `{ "data": <full booking object> }`. Lỗi: 404 `BOOKING_NOT_FOUND`, 409 `BOOKING_ALREADY_CANCELLED`.

`GET /api/bookings/{booking_id}/reservations` (`app/api/public/bookings.py:92`): `{ "data": [ReservationResponse] }`. `price_snapshot` là **string** tại endpoint này.

### 3.8 Admin Bookings

`GET /api/admin/bookings` (`app/api/admin/bookings.py:18`) — cursor pagination
- Query: `shop_id?`, `booking_date?`, `status?`, `phone?`, `pos_booking_code?`, `limit?` (1-100, default 20), `cursor?`.
- Response (`app/api/admin/bookings.py:48`):
```json
{ "data": [ { "booking_id", "pos_booking_code": "str|null", "shop_id", "customer": { "customer_id", "phone", "name": "str|null" } | null, "booking_date", "start_time", "end_time", "number_of_people", "status" } ], "meta": { "limit": int, "next_cursor": "uuid|null" } }
```

`GET /api/admin/bookings/{booking_id}` (`app/api/admin/bookings.py:74`)
- Response (`app/api/admin/bookings.py:74-106`) — dict inline, **`price_snapshot` ở đây là float (KHÁC public)**:
```json
{
  "data": {
    "booking_id", "pos_booking_code", "status",
    "shop": { "shop_id": "uuid|null", "name": "str|null" },
    "customer": { "customer_id", "phone", "name", "is_member": bool, "member_rank": "str|null", "visit_count": int } | null,
    "booking_date", "start_time", "end_time", "number_of_people", "total_duration_minutes",
    "reservations": [ { "reservation_id", "therapist_id", "start_time", "end_time", "status", "courses": [ { "course_id", "course_role", "course_name_snapshot", "duration_snapshot": int, "price_snapshot": FLOAT } ] } ]
  }
}
```

### 3.9 Available Slots (public)

`GET /api/shops/{shop_id}/available-slots` (`app/api/public/available_slots.py:14`)
- Query bắt buộc: `booking_date` (`YYYY-MM-DD`), `number_of_people` (1-3), `main_course_id` (uuid).
- Query optional: `addon_course_ids` (comma-separated uuid), `therapist_request_type` (`none|specific|gender`), `therapist_id` (uuid), `therapist_gender` (`male|female`).
- Response (`app/services/slot_service.py:124-129`):
```json
{
  "data": [ { "start_time": "HH:MM:SS", "end_time": "HH:MM:SS", "duration_minutes": int, "available": true } ],
  "meta": { "booking_date": "YYYY-MM-DD", "shop_id": "uuid", "number_of_people": int }
}
```
- Lỗi: 404 `SHOP_NOT_FOUND`, 422 `SHOP_INACTIVE`/`INVALID_COURSE_COMBO`/`COURSE_NOT_FOUND`.

`GET /api/shops/{shop_id}/available-therapists` (`app/api/public/available_slots.py:48`)
- Query bắt buộc: `booking_date` (`YYYY-MM-DD`), `start_time` (`HH:MM`), `end_time` (`HH:MM`).
- Query optional: `gender` (`male|female|any`).
- Response (`app/services/slot_service.py:170`): `{ "data": [ { "therapist_id", "shop_id", "name", "gender", "available": bool } ] }`.
- Lỗi: 422 `INVALID_TIME_RANGE`, 404 `SHOP_NOT_FOUND`, 422 `SHOP_INACTIVE`.

### 3.10 Therapist Schedule (public)

`GET /api/therapists/me/schedule` (`app/api/public/therapist_schedule.py:16`)
- Query bắt buộc: `date` (`YYYY-MM-DD`), `therapist_id` (uuid) — backend hiện bắt buộc `therapist_id` (tạm thời, `app/api/public/therapist_schedule.py:27-28`).
- Response (`app/services/therapist_schedule_service.py:40-47`):
```json
{
  "data": {
    "therapist_id": "uuid",
    "date": "YYYY-MM-DD",
    "shift": { "start_time": "HH:MM:SS|null", "end_time": "HH:MM:SS|null" } | null,
    "reservations": [ { "reservation_id", "booking_id", "start_time": "HH:MM:SS", "end_time": "HH:MM:SS", "course_names": ["str"], "booking_status": "str|null" } ]
  }
}
```
- Lỗi: 400 `INVALID_DATE`/`INVALID_THERAPIST_ID`, 404 `THERAPIST_NOT_FOUND`.

---

## 4. Enum & Trạng thái

### 4.1 Booking status (`bookings.status`)
- Giá trị quan sát: `"confirmed"` (default, `app/db/models/booking.py`), `"cancelled"` (khi huỷ, `app/services/booking_service.py:92`).
- Backend **không ép enum đóng** ngoài `cancelled` cho thao tác huỷ (`app/schemas/booking.py:52` `^cancelled$`). Frontend nên hiển thị linh hoạt nhưng kỳ vọng `confirmed`/`cancelled`.
- Reservation `status` default `"assigned"` (`app/db/models/reservation.py`).

### 4.2 therapist_request_type (`bookings.therapist_request_type`)
- `"none"` (default) | `"specific"` | `"gender"` (`app/db/models/booking.py`, `app/schemas/booking.py:19`).

### 4.3 gender (`therapists.gender`, `requested_gender`)
- `"male"` | `"female"` (regex `app/schemas/therapist.py`, `app/schemas/booking.py:21`).

### 4.4 course_type / course_role
- `"main"` | `"addon"` (regex `app/schemas/course.py:12`, `app/schemas/booking.py:14`).

### 4.5 available-therapists gender filter
- `"male"` | `"female"` | `"any"` (`app/schemas/available_slot.py`).

### 4.6 number_of_people
- `1` đến `3` (`app/schemas/booking.py:35`). Booking nhóm (`>1`) **KHÔNG được** yêu cầu therapist cụ thể (`app/services/booking_service.py:239-240` → 422 `GROUP_BOOKING_CANNOT_REQUEST_THERAPIST`).

### 4.7 price
- `Numeric(10,2)`, serialize thành **string** ở hầu hết endpoint. Riêng `GET /api/admin/bookings/{id}` cast thành **float** (`app/api/admin/bookings.py:106`).

---

## 5. Các API CÒN THIẾU để xây màn hình Schedule

Frontend quản trị cần màn hình **Schedule** (lịch theo ngày của shop/therapist).

> **ĐÃ bổ sung (backend):** `GET /api/admin/schedule?shop_id=&date=&from=&to=`
> trả về 1 request gồm `shop` (kèm `timezone` + `business_hours`), `therapists`,
> `shifts`, `blocked_ranges`, `bookings` (kèm reservations + courses eager-loaded),
> `booking_statuses`, `date`, `view_window`. Xem `app/api/admin/schedule.py`,
> `app/services/schedule_service.py`, `app/repositories/schedule_repository.py`.
> Frontend nên chuyển `schedule.queries.ts` sang dùng endpoint này thay vì ghép
> N request (shifts + bookings + N detail).

1. **Thiếu API lịch theo SHOP (ngày)** — ĐÃ CÓ: `GET /api/admin/schedule`. Trước đây
   backend chỉ có `GET /api/therapists/me/schedule` (theo 1 therapist) và
   `/api/admin/shops/{shop_id}/therapist-shifts` (chỉ ca, không có booking).

2. **Thiếu API cập nhật/xoá ca** — chỉ có `POST`/`PATCH` ca, không có `DELETE` shift (`app/api/admin/therapist_shifts.py`). Muốn huỷ ca phải `PATCH is_active=false`.

3. **Thiếu bulk tạo ca** — mỗi ca 1 request (`ShiftCreate`). Làm lịch tuần tốn nhiều request.

4. **`GET /api/therapists/me/schedule` bắt buộc `therapist_id` query** (`app/api/public/therapist_schedule.py:27`) dù path là `/me` — frontend phải tự truyền therapist_id, không tự suy từ JWT.

5. **Thiếu endpoint lấy danh sách therapist kèm ca trong 1 ngày** cho việc render cột. Hiện phải gọi `therapist-shifts` rồi `available-therapists`.

6. **Thiếu API đổi therapist của reservation / đổi giờ reservation** — booking đã tạo chỉ sửa được `booking_date`/`start_time` qua `PATCH` (`app/services/booking_service.py:113` `allowed_fields = {"booking_date","start_time"}`). Không có API sửa reservation.

> Đề xuất: bổ sung `GET /api/admin/shops/{shop_id}/schedule?date=` và `DELETE /api/admin/therapist-shifts/{shift_id}` ở backend trước khi làm màn hình Schedule phức tạp.

---

## 6. Những điểm Frontend cần chú ý

### 6.1 Auth — lưu JWT an toàn
- Admin API cần `Authorization: Bearer <Supabase JWT>`. Supabase JS auto-refresh token; frontend **không lưu JWT dài hạn vào localStorage** mà dùng session của `@supabase/supabase-js` (cookie httpOnly nếu dùng SSR, hoặc in-memory + persist nhẹ). Xem `src/lib/supabase.ts`, `src/contexts/AuthContext.tsx`.
- Email user đăng nhập **phải nằm trong `ADMIN_EMAILS`** backend (`app/core/auth.py:55-57`), nếu không gọi admin API → 403 `FORBIDDEN`.
- Mọi admin request phải gắn header từ `supabase.auth.getSession().data.session.access_token`.

### 6.2 Decimal price là STRING
- `course.price`, `reservation_courses.price_snapshot` trả về là **string** JSON (`Numeric(10,2)` → `model_dump(mode="json")`, `app/services/lot_service.py:120`). Frontend phải parse `Number(price)` khi tính tiền. Riêng admin booking detail là float — cần normalize khi map.

### 6.3 Response luôn bọc `{ data, meta? }`
- List: `{ data: [...], meta: { total|limit|next_cursor } }`. Single: `{ data: {...} }`.
- Frontend viết 1 hàm `unwrap()` chung, không truy cập response gốc trong component.

### 6.4 Validation lỗi RFC 9457
- Mọi lỗi trả body (`app/core/exceptions.py`): `{ type, title, status, detail, code, instance?, errors? }`.
- `errors` là mảng `{ field, message }` (422 validation). Frontend map `errors[].field` vào React Hook Form (`app/main.py:43-47`).
- Một số `code` quan trọng: `AUTHENTICATION_REQUIRED` (401), `FORBIDDEN` (403), `SHOP_NOT_FOUND`/`BOOKING_NOT_FOUND`/`COURSE_NOT_FOUND`/`THERAPIST_NOT_FOUND` (404), `SLOT_CONFLICT` (409), `BOOKING_ALREADY_CANCELLED` (409), `CUSTOMER_IN_NG_LIST` (403), `SHOP_INACTIVE` (422), `INVALID_COURSE_COMBO` (422), `ADDON_REQUIRES_MAIN_COURSE` (422), `GROUP_BOOKING_CANNOT_REQUEST_THERAPIST` (422), `THERAPIST_NOT_AVAILABLE` (422), `MISSING_IDEMPOTENCY_KEY` (400).

### 6.5 Idempotency-Key khi tạo booking
- `POST /api/bookings` **bắt buộc** header `Idempotency-Key: <uuid>` (`app/services/booking_service.py:176-186`). Frontend sinh uuid v4 mỗi lần submit, lưu tạm để retry an toàn.

### 6.6 Pagination cursor
- Booking list dùng cursor (`next_cursor` = uuid item cuối). Không có total count thực sự (`meta.total` ở một số list chỉ là `len(array)`). Frontend dùng "load more" kiểu cursor, không dùng số trang.

### 6.7 Timezone (XEM KỸ §9)
- Backend **không chuẩn hóa múi giờ**. `start_time`/`end_time`/`work_date` là giá trị naive (không có tz). Frontend phải **giả định múi giờ của shop (thường Asia/Ho_Chi_Minh)** khi hiển thị và khi gửi lên phải gửi giờ local của shop, KHÔNG convert sang UTC.
- `created_at`/`updated_at`/`cancelled_at` là TIMESTAMPTZ (UTC trong DB). Hiển thị cần `toLocaleString` với tz của shop.

### 6.8 Booking qua nửa đêm (XEM KỸ §9)
- `end_time` chỉ lưu giờ:phút, **ngày bị mất** (`app/services/booking_service.py:258-262`). Nếu đặt 23:00 + 120 phút → `end_time = 01:00` nhưng vẫn gắn với `booking_date` hôm đó. Frontend hiển thị phải tự cộng ngày nếu `end_time < start_time`.

---

## 7. Đề xuất kiến trúc Frontend

### 7.1 Tech stack (theo yêu cầu)
- Next.js 16 App Router, TypeScript strict.
- Tailwind CSS, TanStack Query (server state), React Hook Form (form), Zod (validation).
- ESLint + Prettier.

### 7.2 Feature-based structure
```
src/
  app/                      # chỉ route + page composition
    (auth)/login/
    admin/
      shops/ courses/ therapists/ shifts/ restrictions/ bookings/ schedule/
  features/
    auth/                   # login, session, useAuth, auth guard
    shop/                   # list, form, queries, DTO
    course/                 # ...
    therapist/
    shift/
    restriction/
    booking/                # list, detail, cancel, DTO/mapper
    schedule/               # (sau khi backend bổ sung API)
    customer/               # (eligibility, history)
  shared/
    api/                    # apiClient (baseURL, attach Bearer, unwrap, error)
    components/             # Button, Input, Table, Dialog, Toast
    hooks/                  # useApiQuery, useApiMutation
    lib/                    # supabase client, format (money, datetime tz)
    config/                 # env validation (zod)
    types/                  # shared types, ApiError type
```

### 7.3 Nguyên tắc (mapping với yêu cầu trước)
1. `app/` chỉ chứa route + composition → business logic trong `features/*`.
2. API client tập trung ở `shared/api/apiClient.ts`: tự động đọc token từ Supabase session, gắn `Authorization`, unwrap `{data}`, ném `ApiError` (RFC 9457).
3. Mỗi feature có `*.schema.ts` (Zod) + `*.dto.ts` (DTO ↔ UI model mapper). Component **không gọi API trực tiếp**, chỉ qua TanStack Query hook trong feature.
4. **Không** dùng 1 Context lớn chứa toàn bộ booking state → mỗi feature quản lý query/mutation riêng.
5. **Không** đẩy response backend thẳng vào UI → qua mapper thành UI model (ví dụ `price` string → `number`, `endTime` qua nửa đêm → `Date` đủ).
6. Server state = TanStack Query; Form state = React Hook Form + Zod resolver.
7. JWT: dùng session Supabase (refresh tự động), không lưu localStorage dài hạn. Với Next.js, có thể dùng Supabase Auth Helpers để truyền session qua cookie cho RSC.
8. Timezone: `shared/lib/datetime.ts` chuẩn hóa hiển thị theo tz shop (mặc định `Asia/Ho_Chi_Minh`). Hàm `formatShopTime`, `combineShopDate` xử lý qua nửa đêm.

### 7.4 Luồng auth đề xuất
- `features/auth`: `AuthProvider` bọc app, lắng nghe `onAuthStateChange`. Guard `admin/layout.tsx` → nếu không có session hoặc email không thuộc admin → redirect `/login`.
- Mỗi query/mutation admin dùng `apiClient` đã gắn token.

### 7.5 Xử lý qua nửa đêm (ví dụ UI model)
```ts
// shared/lib/datetime.ts
function toBookingEndDate(startDate: string, startTime: string, endTime: string): string {
  // nếu endTime < startTime => cộng 1 ngày
  if (endTime < startTime) {
    const d = new Date(startDate + "T00:00:00");
    d.setDate(d.getDate() + 1);
    return d.toISOString().slice(0, 10);
  }
  return startDate;
}
```

---

## 8. Danh mục file backend làm căn cứ (index)

| Nội dung | File: dòng |
|---|---|
| Router mount + CORS | `app/main.py:70-91` |
| Error format RFC9457 | `app/core/exceptions.py:19-29`, `app/main.py:31-66` |
| Auth require_admin (email whitelist, JWT) | `app/core/auth.py:14-57` |
| Config (ADMIN_EMAILS, CORS, JWKS) | `app/core/config.py:33-38` |
| ERD models | `app/db/models/{shop,course,therapist,therapist_shift,customer,customer_restriction,booking,reservation,reservation_course}.py` |
| TimestampMixin | `app/db/mixins.py:10-17` |
| Booking create/cancel/update/get | `app/services/booking_service.py:41-173` |
| End_time qua nửa đêm | `app/services/booking_service.py:258-262` |
| Slot tính toán | `app/services/slot_service.py:32-233` |
| Therapist schedule | `app/services/therapist_schedule_service.py:20-47` |
| Eligibility response | `app/services/eligibility_service.py:34-48` |
| Schemas | `app/schemas/{shop,course,therapist,therapist_shift,customer,customer_restriction,booking,available_slot,common}.py` |
| Admin routers | `app/api/admin/{shops,courses,therapists,therapist_shifts,customer_restrictions,bookings}.py` |
| Public routers | `app/api/public/{shops,available_slots,booking_eligibility,bookings,therapist_schedule}.py` |
| Decimal → string JSON | `app/schemas/booking.py:80` (price_snapshot Decimal), `app/services/slot_service.py:120` |
| Admin booking price float | `app/api/admin/bookings.py:106` |
| Timezone (chỉ TIMESTAMPTZ + 1 chỗ UTC) | `app/db/mixins.py:13,17`, `app/services/booking_service.py:2,94` |
