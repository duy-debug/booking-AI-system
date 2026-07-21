# Missing Booking Fields — Booking Drawer (Schedule)

> Tài liệu này liệt kê các trường trong **giao diện cũ (POS/cũ)** được yêu cầu hiển thị
> trong Booking Drawer, nhưng **backend chưa hỗ trợ** (không có cột DB, không có trường
> trong schema request/response). Căn cứ: `docs/frontend-analysis.md` §1.1 (ERD), §3.7 (Booking API).
>
> **Nguyên tắc:** Frontend KHÔNG tự thêm field vào payload nếu DB chưa có. Các section
> tương ứng hiển thị `UnsupportedNote` (xem `features/schedule/booking-form/booking-form-sections.tsx`)
> và KHÔNG gửi dữ liệu đó lên backend.

---

## 1. Danh sách field chưa hỗ trợ

| Field giao diện | Section | Lý do chưa có | Cần bổ sung |
|---|---|---|---|
| **Giới tính khách** (`gender`) | Customer | `customers` chỉ có `name`, `phone`, `is_member`, `member_rank`, `visit_count` (`app/db/models/customer.py:14`). Không có cột giới tính khách. | Migration thêm `customers.gender` (male/female/other). Cập nhật `CustomerCreate`/`CustomerResponse`. |
| **Duration (độc lập)** | Course | `bookings` có `total_duration_minutes` (tính từ courses). Duration gốc lấy từ `courses.duration_minutes`. Không có trường duration riêng cho booking. | Nếu cần ghi đè: thêm `bookings.requested_duration_minutes`. Hiện dùng duration của course. |
| **Option** (phân loại gói/addon chi tiết) | Option | `reservation_courses` chỉ có `course_id`, `course_role` (main/addon), snapshot. Không có bảng `options`. | Migration thêm bảng `course_options` + `reservation_course_option`. API `BookingCreate.courses[].option_id?`. |
| **Vị trí mệt / đau** (body condition) | BodyCondition | `bookings`/`reservations` không có cột mô tả cơ thể. | Migration thêm `bookings.body_notes` (JSON/text) hoặc bảng `booking_body_conditions`. |
| **Vị trí không được chạm** (no-touch) | BodyCondition | Như trên. | Cùng migration body condition. |
| **Therapist preference** (ngoài request type) | Therapist | Backend chỉ hỗ trợ `therapist_request_type` (none/specific/gender) + `requested_therapist_id`/`requested_gender` (`app/db/models/booking.py`). Không có "prefer nhưng không bắt buộc". | Có thể mở rộng enum, nhưng hiện map "cụ thể" → `specific`. |
| **Nguồn booking** (POS/Web/Hotline/Walk-in) | BookingSource | `bookings` không có cột `source`. `pos_booking_code` đã DEPRECATED. | Migration thêm `bookings.source` (enum). API `BookingCreate.source?`. |
| **Interval** (khoảng nghỉ) | Preference | Không có cột. | Migration thêm `bookings.interval_minutes` (nullable). |
| **Mức độ trò chuyện** (chat level) | Preference | Không có cột. | Migration thêm `bookings.chat_level` (enum 1-3). |
| **Lực massage** (pressure) | Preference | Không có cột. | Migration thêm `bookings.pressure_level` (enum 1-3). |
| **Thay quần áo** (change clothes) | Preference | Không có cột. | Migration thêm `bookings.change_clothes` (bool). |
| **Ghi chú** (notes) | Notes | `bookings`/`reservations` không có cột note. | Migration thêm `bookings.note` (text). |

---

## 2. Migration / Model / Schema / API cần bổ sung (tổng hợp)

### 2.1 Migration (SQL)
```sql
-- body condition + notes + source + preferences
ALTER TABLE customers ADD COLUMN gender text CHECK (gender IN ('male','female','other'));

ALTER TABLE bookings
  ADD COLUMN source text,                      -- POS | WEB | HOTLINE | WALK_IN
  ADD COLUMN note text,
  ADD COLUMN interval_minutes int,
  ADD COLUMN chat_level int CHECK (chat_level BETWEEN 1 AND 3),
  ADD COLUMN pressure_level int CHECK (pressure_level BETWEEN 1 AND 3),
  ADD COLUMN change_clothes boolean DEFAULT false,
  ADD COLUMN body_notes text;                  -- vị trí đau / không chạm (JSON hoặc text)

-- option (nếu cần)
CREATE TABLE course_options (
  option_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  course_id uuid REFERENCES courses(course_id),
  name text NOT NULL,
  price numeric(10,2) NOT NULL DEFAULT 0
);
CREATE TABLE reservation_course_options (
  reservation_course_id uuid REFERENCES reservation_courses(reservation_course_id),
  option_id uuid REFERENCES course_options(option_id)
);
```

### 2.2 Model (`app/db/models/*.py`)
- `Customer.gender: Mapped[str|None]`
- `Booking.source`, `Booking.note`, `Booking.interval_minutes`, `Booking.chat_level`,
  `Booking.pressure_level`, `Booking.change_clothes`, `Booking.body_notes`
- `CourseOption`, `ReservationCourseOption` (nếu có option)

### 2.3 Schema (`app/schemas/booking.py`)
- `BookingCreate` thêm các trường optional: `source?`, `note?`, `interval_minutes?`,
  `chat_level?`, `pressure_level?`, `change_clothes?`, `body_notes?`, `customer.gender?`.
- `BookingResponse`/`BookingDetailRaw` trả thêm các trường trên.
- Nếu có option: `courses[].option_ids?: UUID[]`.

### 2.4 API
- `POST /api/bookings` và `PATCH /api/bookings/{id}` chấp nhận & lưu các trường mới.
- `GET /api/admin/bookings/{id}` trả về các trường mới.
- `PATCH` hiện chỉ cho phép `booking_date`/`start_time` (§4.6) — cần mở rộng nếu muốn
  sửa note/source từ drawer.

---

## 3. Trường backend ĐÃ hỗ trợ (được đưa vào payload)

- `shop_id`, `booking_date`, `start_time` (HH:MM), `number_of_people` (1-3)
- `customer: { phone, name }`
- `courses: [{ course_id, course_role: main|addon }]`
- `therapist_request: { type: none|specific|gender, therapist_id?, gender? }`
- `confirmed_by_customer` (luôn `true` từ admin)
- Huỷ: `PATCH` với `status: "cancelled"` + `cancel_reason`
- Tạo bắt buộc header `Idempotency-Key`
- Availability: `GET /api/shops/{shop}/available-slots`, `/available-therapists`,
  `POST /api/booking-eligibility-checks` (nguồn xác thực lịch trống & khách bị cấm)
