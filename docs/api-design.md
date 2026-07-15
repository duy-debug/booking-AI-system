# API Design
# Thiết kế Booking API — RESTful Standard

# 1. Nguyên tắc thiết kế

API này được thiết kế theo hướng **resource-oriented RESTful API**:

- Dùng danh từ số nhiều cho collection resource.
- Dùng HTTP method để thể hiện hành động trên resource.
- Không đưa action verb vào URL resource thông thường.
- Dùng query parameter cho filter, search và lookup.
- Dùng `PATCH` cho partial update hoặc state transition.
- Dùng `POST` khi tạo resource mới hoặc tạo command-like resource cần xử lý nghiệp vụ.
- Không mirror database schema 1-1 ra API.
- Response schema, HTTP status code và error format phải thống nhất.
- Dùng `Idempotency-Key` khi tạo booking để tránh tạo booking trùng.


---

# 2. Public Booking APIs

## 2.1. List Shops

```http
GET /api/shops
```

### Query Parameters

| Name | Type | Required | Mô tả |
|---|---:|---:|---|
| `is_active` | boolean | No | Filter shop đang hoạt động |

### Response `200 OK`

```json
{
  "data": [
    {
      "shop_id": "550e8400-e29b-41d4-a716-446655440001",
      "shop_code": "SHOP001",
      "name": "Massage Shop A",
      "address": "Tokyo",
      "phone": "0900000000",
      "is_active": true,
      "links": {
        "self": "/api/shops/550e8400-e29b-41d4-a716-446655440001",
        "courses": "/api/shops/550e8400-e29b-41d4-a716-446655440001/courses",
        "available_slots": "/api/shops/550e8400-e29b-41d4-a716-446655440001/available-slots"
      }
    }
  ],
  "meta": {
    "total": 1
  }
}
```

### Error Responses

| HTTP Status | Error Code | Trường hợp |
|---:|---|---|
| `400 Bad Request` | `INVALID_QUERY_PARAMETER` | `is_active` không phải giá trị boolean hợp lệ. |
| `500 Internal Server Error` | `INTERNAL_SERVER_ERROR` | Backend xảy ra lỗi ngoài dự kiến khi lấy danh sách shop. |

---

## 2.2. Get Shop Detail

```http
GET /api/shops/{shop_id}
```

### Response `200 OK`

```json
{
  "data": {
    "shop_id": "550e8400-e29b-41d4-a716-446655440001",
    "shop_code": "SHOP001",
    "name": "Massage Shop A",
    "address": "Tokyo",
    "phone": "0900000000",
    "is_active": true
  }
}
```

### Error Responses

| HTTP Status | Error Code | Trường hợp |
|---:|---|---|
| `400 Bad Request` | `INVALID_SHOP_ID` | `shop_id` không đúng format UUID. |
| `404 Not Found` | `SHOP_NOT_FOUND` | Không tìm thấy shop tương ứng. |
| `500 Internal Server Error` | `INTERNAL_SERVER_ERROR` | Backend xảy ra lỗi ngoài dự kiến. |

---

## 2.3. List Courses of a Shop

```http
GET /api/shops/{shop_id}/courses
```

### Query Parameters

| Name | Type | Required | Mô tả |
|---|---:|---:|---|
| `course_type` | string | No | `main` hoặc `addon` |
| `is_active` | boolean | No | Filter course đang hoạt động |

### Response `200 OK`

```json
{
  "data": [
    {
      "course_id": "550e8400-e29b-41d4-a716-446655440101",
      "shop_id": "550e8400-e29b-41d4-a716-446655440001",
      "pos_course_code": "POS_COURSE_001",
      "name": "Body Massage 60 min",
      "duration_minutes": 60,
      "price": 6000,
      "course_type": "main",
      "is_active": true
    },
    {
      "course_id": "550e8400-e29b-41d4-a716-446655440102",
      "shop_id": "550e8400-e29b-41d4-a716-446655440001",
      "pos_course_code": "POS_COURSE_002",
      "name": "Head Spa 15 min",
      "duration_minutes": 15,
      "price": 1500,
      "course_type": "addon",
      "is_active": true
    }
  ]
}
```

### Error Responses

| HTTP Status | Error Code | Trường hợp |
|---:|---|---|
| `400 Bad Request` | `INVALID_SHOP_ID` | `shop_id` không đúng format UUID. |
| `400 Bad Request` | `INVALID_QUERY_PARAMETER` | `course_type` hoặc `is_active` không hợp lệ. |
| `404 Not Found` | `SHOP_NOT_FOUND` | Không tìm thấy shop tương ứng. |
| `500 Internal Server Error` | `INTERNAL_SERVER_ERROR` | Backend xảy ra lỗi ngoài dự kiến. |

---

## 2.4. List Available Slots

`available-slots` là computed resource. Slot không được lưu thành bảng riêng.

```http
GET /api/shops/{shop_id}/available-slots
```

### Query Parameters

| Name | Type | Required | Mô tả |
|---|---:|---:|---|
| `booking_date` | date | Yes | Ngày đặt booking |
| `number_of_people` | integer | Yes | Số người, từ 1 đến 3 |
| `main_course_id` | string | Yes | ID của main course |
| `addon_course_ids` | string | No | Danh sách add-on ID, phân tách bằng dấu phẩy |
| `therapist_request_type` | string | No | `none`, `specific`, `gender` |
| `therapist_id` | string | No | Bắt buộc khi `therapist_request_type = specific` |
| `therapist_gender` | string | No | Bắt buộc khi `therapist_request_type = gender` |

### Example

```http
GET /api/shops/550e8400-e29b-41d4-a716-446655440001/available-slots?booking_date=2026-07-20&number_of_people=1&main_course_id=550e8400-e29b-41d4-a716-446655440101&addon_course_ids=550e8400-e29b-41d4-a716-446655440102&therapist_request_type=none
```

### Response `200 OK`

```json
{
  "data": [
    {
      "start_time": "10:00",
      "end_time": "11:15",
      "duration_minutes": 75,
      "available": true
    },
    {
      "start_time": "11:30",
      "end_time": "12:45",
      "duration_minutes": 75,
      "available": true
    }
  ],
  "meta": {
    "booking_date": "2026-07-20",
    "shop_id": "550e8400-e29b-41d4-a716-446655440001",
    "number_of_people": 1
  }
}
```

### Error Responses

| HTTP Status | Error Code | Trường hợp |
|---:|---|---|
| `400 Bad Request` | `INVALID_QUERY_PARAMETER` | Thiếu query parameter bắt buộc hoặc sai format ngày, UUID hay enum. |
| `404 Not Found` | `SHOP_NOT_FOUND` | Không tìm thấy shop. |
| `404 Not Found` | `COURSE_NOT_FOUND` | Không tìm thấy main course hoặc add-on. |
| `404 Not Found` | `THERAPIST_NOT_FOUND` | Không tìm thấy therapist được chỉ định. |
| `422 Unprocessable Entity` | `SHOP_INACTIVE` | Shop hiện không hoạt động. |
| `422 Unprocessable Entity` | `INVALID_NUMBER_OF_PEOPLE` | `number_of_people` không nằm trong khoảng từ 1 đến 3. |
| `422 Unprocessable Entity` | `INVALID_COURSE_COMBO` | Main course và add-on không tạo thành combo hợp lệ. |
| `422 Unprocessable Entity` | `ADDON_REQUIRES_MAIN_COURSE` | Có add-on nhưng không có main course. |
| `422 Unprocessable Entity` | `GROUP_BOOKING_CANNOT_REQUEST_THERAPIST` | Booking nhóm yêu cầu therapist cụ thể hoặc theo gender. |
| `422 Unprocessable Entity` | `BOOKING_TOO_SOON` | Thời gian đặt không đáp ứng điều kiện đặt trước tối thiểu 15 phút. |
| `422 Unprocessable Entity` | `SLOT_NOT_AVAILABLE` | Không có slot phù hợp với điều kiện tìm kiếm. |
| `503 Service Unavailable` | `POS_TEMPORARY_ERROR` | Không thể kiểm tra availability từ POS tại thời điểm hiện tại. |

---

## 2.5. List Available Therapists

```http
GET /api/shops/{shop_id}/available-therapists
```

### Query Parameters

| Name | Type | Required | Mô tả |
|---|---:|---:|---|
| `booking_date` | date | Yes | Ngày đặt booking |
| `start_time` | time | Yes | Giờ bắt đầu đã chọn |
| `end_time` | time | Yes | Giờ kết thúc đã tính |
| `gender` | string | No | `male`, `female`, `any` |

### Response `200 OK`

```json
{
  "data": [
    {
      "therapist_id": "550e8400-e29b-41d4-a716-446655440201",
      "shop_id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "Yuki",
      "gender": "female",
      "available": true
    }
  ]
}
```

### Error Responses

| HTTP Status | Error Code | Trường hợp |
|---:|---|---|
| `400 Bad Request` | `INVALID_QUERY_PARAMETER` | Thiếu query parameter bắt buộc hoặc sai format ngày, giờ, UUID hay gender. |
| `404 Not Found` | `SHOP_NOT_FOUND` | Không tìm thấy shop. |
| `422 Unprocessable Entity` | `SHOP_INACTIVE` | Shop hiện không hoạt động. |
| `422 Unprocessable Entity` | `INVALID_TIME_RANGE` | `end_time` không lớn hơn `start_time` hoặc khoảng thời gian không hợp lệ. |
| `422 Unprocessable Entity` | `THERAPIST_NOT_AVAILABLE` | Không có therapist phù hợp trong khoảng thời gian yêu cầu. |
| `503 Service Unavailable` | `POS_TEMPORARY_ERROR` | Không thể đồng bộ availability từ POS. |

---

## 2.6. Create Booking Eligibility Check

Endpoint này tạo một resource tạm để kiểm tra phone khách hàng và NG list.

```http
POST /api/booking-eligibility-checks
```

### Request Body

```json
{
  "phone": "09012345678",
  "shop_id": "550e8400-e29b-41d4-a716-446655440001"
}
```

### Response `201 Created`

```json
{
  "data": {
    "check_id": "550e8400-e29b-41d4-a716-446655440401",
    "phone": "09012345678",
    "eligible": true,
    "customer": {
      "customer_type": "existing",
      "customer_id": "550e8400-e29b-41d4-a716-446655440301",
      "name": "Nguyen Van A",
      "is_member": true,
      "member_rank": "gold",
      "visit_count": 12
    },
    "restriction": null
  }
}
```

### Response `403 Forbidden`

```json
{
  "type": "https://api.example.com/problems/customer-restricted",
  "title": "Customer is restricted",
  "status": 403,
  "detail": "This phone number is not allowed to create bookings.",
  "code": "CUSTOMER_IN_NG_LIST"
}
```

### Error Responses

| HTTP Status | Error Code | Trường hợp |
|---:|---|---|
| `400 Bad Request` | `INVALID_REQUEST_BODY` | Request body thiếu field bắt buộc hoặc sai JSON format. |
| `404 Not Found` | `SHOP_NOT_FOUND` | Không tìm thấy shop. |
| `422 Unprocessable Entity` | `INVALID_PHONE` | Phone không đúng format được hệ thống chấp nhận. |
| `422 Unprocessable Entity` | `SHOP_INACTIVE` | Shop hiện không hoạt động. |
| `403 Forbidden` | `CUSTOMER_IN_NG_LIST` | Phone nằm trong NG list và không được tạo booking. |
| `503 Service Unavailable` | `POS_TEMPORARY_ERROR` | Không thể kiểm tra dữ liệu khách hàng hoặc NG list từ POS. |

---

## 2.7. Create Booking

```http
POST /api/bookings
```

### Required Header

```http
Idempotency-Key: 7d9f1c8e-1111-2222-3333-123456789abc
```

### Request Body

```json
{
  "shop_id": "550e8400-e29b-41d4-a716-446655440001",
  "booking_date": "2026-07-20",
  "start_time": "10:00",
  "number_of_people": 1,
  "customer": {
    "phone": "09012345678",
    "name": "Nguyen Van A"
  },
  "courses": [
    {
      "course_id": "550e8400-e29b-41d4-a716-446655440101",
      "course_role": "main"
    },
    {
      "course_id": "550e8400-e29b-41d4-a716-446655440102",
      "course_role": "addon"
    }
  ],
  "therapist_request": {
    "type": "specific",
    "therapist_id": "550e8400-e29b-41d4-a716-446655440201",
    "gender": null
  },
  "confirmed_by_customer": true
}
```

### Response `201 Created`

```json
{
  "data": {
    "booking_id": "550e8400-e29b-41d4-a716-446655440501",
    "pos_booking_code": "POS-20260720-001",
    "shop_id": "550e8400-e29b-41d4-a716-446655440001",
    "customer_id": "550e8400-e29b-41d4-a716-446655440301",
    "booking_date": "2026-07-20",
    "start_time": "10:00",
    "end_time": "11:15",
    "number_of_people": 1,
    "total_duration_minutes": 75,
    "status": "confirmed",
    "therapist_request_type": "specific",
    "requested_therapist_id": "550e8400-e29b-41d4-a716-446655440201",
    "reservations": [
      {
        "reservation_id": "550e8400-e29b-41d4-a716-446655440601",
        "person_index": 1,
        "therapist_id": "550e8400-e29b-41d4-a716-446655440201",
        "start_time": "10:00",
        "end_time": "11:15",
        "status": "assigned",
        "courses": [
          {
            "course_id": "550e8400-e29b-41d4-a716-446655440101",
            "course_role": "main",
            "course_name_snapshot": "Body Massage 60 min",
            "duration_snapshot": 60,
            "price_snapshot": 6000
          },
          {
            "course_id": "550e8400-e29b-41d4-a716-446655440102",
            "course_role": "addon",
            "course_name_snapshot": "Head Spa 15 min",
            "duration_snapshot": 15,
            "price_snapshot": 1500
          }
        ]
      }
    ],
    "links": {
      "self": "/api/bookings/550e8400-e29b-41d4-a716-446655440501",
      "reservations": "/api/bookings/550e8400-e29b-41d4-a716-446655440501/reservations"
    }
  }
}
```

### Response `409 Conflict`

```json
{
  "type": "https://api.example.com/problems/slot-conflict",
  "title": "Slot conflict",
  "status": 409,
  "detail": "The selected slot is no longer available.",
  "code": "SLOT_CONFLICT",
  "suggested_slots": [
    {
      "start_time": "11:30",
      "end_time": "12:45"
    }
  ]
}
```

### Error Responses

| HTTP Status | Error Code | Trường hợp |
|---:|---|---|
| `400 Bad Request` | `INVALID_REQUEST_BODY` | Request body sai format hoặc thiếu field bắt buộc. |
| `400 Bad Request` | `MISSING_IDEMPOTENCY_KEY` | Thiếu `Idempotency-Key` header. |
| `403 Forbidden` | `CUSTOMER_IN_NG_LIST` | Phone khách hàng nằm trong NG list. |
| `404 Not Found` | `SHOP_NOT_FOUND` | Không tìm thấy shop. |
| `404 Not Found` | `COURSE_NOT_FOUND` | Không tìm thấy course được yêu cầu. |
| `404 Not Found` | `THERAPIST_NOT_FOUND` | Không tìm thấy therapist được chỉ định. |
| `409 Conflict` | `SLOT_CONFLICT` | Slot đã bị đặt mất trước khi booking được tạo chính thức. |
| `409 Conflict` | `IDEMPOTENCY_CONFLICT` | Cùng `Idempotency-Key` nhưng request payload khác nhau. |
| `422 Unprocessable Entity` | `INVALID_NUMBER_OF_PEOPLE` | Số người không nằm trong khoảng từ 1 đến 3. |
| `422 Unprocessable Entity` | `INVALID_COURSE_COMBO` | Combo main course/add-on không hợp lệ. |
| `422 Unprocessable Entity` | `GROUP_BOOKING_CANNOT_REQUEST_THERAPIST` | Booking nhóm yêu cầu therapist. |
| `422 Unprocessable Entity` | `THERAPIST_NOT_AVAILABLE` | Therapist không khả dụng tại slot đã chọn. |
| `422 Unprocessable Entity` | `BOOKING_TOO_SOON` | Booking không đáp ứng thời gian đặt trước tối thiểu. |
| `503 Service Unavailable` | `POS_TEMPORARY_ERROR` | POS không phản hồi hoặc xảy ra lỗi tạm thời. |

---

## 2.8. List Bookings

```http
GET /api/bookings
```

### Query Parameters

| Name | Type | Required | Mô tả |
|---|---:|---:|---|
| `pos_booking_code` | string | No | Search theo mã booking POS |
| `phone` | string | No | Search theo số điện thoại khách hàng |
| `shop_id` | string | No | Filter theo shop |
| `booking_date` | date | No | Filter theo ngày booking |
| `status` | string | No | Filter theo booking status |
| `limit` | integer | No | Page size |
| `cursor` | string | No | Cursor pagination token |

### Response `200 OK`

```json
{
  "data": [
    {
      "booking_id": "550e8400-e29b-41d4-a716-446655440501",
      "pos_booking_code": "POS-20260720-001",
      "shop_id": "550e8400-e29b-41d4-a716-446655440001",
      "booking_date": "2026-07-20",
      "start_time": "10:00",
      "end_time": "11:15",
      "number_of_people": 1,
      "status": "confirmed"
    }
  ],
  "meta": {
    "limit": 20,
    "next_cursor": null
  }
}
```

### Error Responses

| HTTP Status | Error Code | Trường hợp |
|---:|---|---|
| `400 Bad Request` | `INVALID_QUERY_PARAMETER` | Filter, `limit` hoặc `cursor` không hợp lệ. |
| `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Endpoint yêu cầu thông tin xác thực nhưng request chưa cung cấp. |
| `403 Forbidden` | `BOOKING_ACCESS_DENIED` | Người dùng không có quyền tra cứu các booking tương ứng. |
| `500 Internal Server Error` | `INTERNAL_SERVER_ERROR` | Backend xảy ra lỗi ngoài dự kiến. |

> Không tìm thấy booking phù hợp không phải lỗi; API trả `200 OK` với `data: []`.

---

## 2.9. Get Booking Detail

```http
GET /api/bookings/{booking_id}
```

### Response `200 OK`

```json
{
  "data": {
    "booking_id": "550e8400-e29b-41d4-a716-446655440501",
    "pos_booking_code": "POS-20260720-001",
    "status": "confirmed",
    "shop": {
      "shop_id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "Massage Shop A"
    },
    "customer": {
      "customer_id": "550e8400-e29b-41d4-a716-446655440301",
      "phone": "09012345678",
      "name": "Nguyen Van A"
    },
    "booking_date": "2026-07-20",
    "start_time": "10:00",
    "end_time": "11:15",
    "number_of_people": 1,
    "total_duration_minutes": 75,
    "reservations": [
      {
        "reservation_id": "550e8400-e29b-41d4-a716-446655440601",
        "person_index": 1,
        "therapist": {
          "therapist_id": "550e8400-e29b-41d4-a716-446655440201",
          "name": "Yuki"
        },
        "courses": [
          {
            "course_role": "main",
            "course_name_snapshot": "Body Massage 60 min",
            "duration_snapshot": 60,
            "price_snapshot": 6000
          }
        ]
      }
    ]
  }
}
```

### Error Responses

| HTTP Status | Error Code | Trường hợp |
|---:|---|---|
| `400 Bad Request` | `INVALID_BOOKING_ID` | `booking_id` không đúng format UUID. |
| `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Request chưa có thông tin xác thực cần thiết. |
| `403 Forbidden` | `BOOKING_ACCESS_DENIED` | Người dùng không có quyền xem booking này. |
| `404 Not Found` | `BOOKING_NOT_FOUND` | Không tìm thấy booking. |
| `503 Service Unavailable` | `POS_TEMPORARY_ERROR` | Không thể đồng bộ trạng thái booking mới nhất từ POS. |

---

## 2.10. Update Booking

Dùng `PATCH` cho partial update. Nếu thay đổi ảnh hưởng đến availability, backend phải check lại slot và POS availability.

```http
PATCH /api/bookings/{booking_id}
```

### Request Body

```json
{
  "booking_date": "2026-07-21",
  "start_time": "14:00",
  "courses": [
    {
      "course_id": "550e8400-e29b-41d4-a716-446655440101",
      "course_role": "main"
    }
  ],
  "therapist_request": {
    "type": "none",
    "therapist_id": null,
    "gender": null
  }
}
```

### Response `200 OK`

```json
{
  "data": {
    "booking_id": "550e8400-e29b-41d4-a716-446655440501",
    "status": "confirmed",
    "booking_date": "2026-07-21",
    "start_time": "14:00",
    "end_time": "15:00",
    "total_duration_minutes": 60
  }
}
```

### Error Responses

| HTTP Status | Error Code | Trường hợp |
|---:|---|---|
| `400 Bad Request` | `INVALID_REQUEST_BODY` | Request body sai format hoặc không có field nào cần cập nhật. |
| `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Request chưa có thông tin xác thực cần thiết. |
| `403 Forbidden` | `BOOKING_ACCESS_DENIED` | Người dùng không có quyền sửa booking. |
| `404 Not Found` | `BOOKING_NOT_FOUND` | Không tìm thấy booking. |
| `409 Conflict` | `BOOKING_ALREADY_CANCELLED` | Booking đã bị hủy và không thể cập nhật. |
| `409 Conflict` | `SLOT_CONFLICT` | Slot mới không còn khả dụng tại thời điểm cập nhật. |
| `422 Unprocessable Entity` | `INVALID_COURSE_COMBO` | Combo course sau cập nhật không hợp lệ. |
| `422 Unprocessable Entity` | `THERAPIST_NOT_AVAILABLE` | Therapist mới không khả dụng. |
| `422 Unprocessable Entity` | `INVALID_BOOKING_STATE_TRANSITION` | Không được phép chuyển từ trạng thái hiện tại sang trạng thái yêu cầu. |
| `503 Service Unavailable` | `POS_TEMPORARY_ERROR` | POS không thể cập nhật booking tại thời điểm hiện tại. |

---

## 2.11. Cancel Booking

Cancel là state transition, vì vậy dùng `PATCH` thay vì action URL như `/cancel`.

```http
PATCH /api/bookings/{booking_id}
```

### Request Body

```json
{
  "status": "cancelled",
  "cancel_reason": "Customer requested cancellation"
}
```

### Response `200 OK`

```json
{
  "data": {
    "booking_id": "550e8400-e29b-41d4-a716-446655440501",
    "status": "cancelled",
    "cancelled_at": "2026-07-13T08:30:00+07:00"
  }
}
```

### Error Responses

| HTTP Status | Error Code | Trường hợp |
|---:|---|---|
| `400 Bad Request` | `INVALID_REQUEST_BODY` | `status` hoặc `cancel_reason` không hợp lệ. |
| `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Request chưa có thông tin xác thực cần thiết. |
| `403 Forbidden` | `BOOKING_ACCESS_DENIED` | Người dùng không có quyền hủy booking. |
| `404 Not Found` | `BOOKING_NOT_FOUND` | Không tìm thấy booking. |
| `409 Conflict` | `BOOKING_ALREADY_CANCELLED` | Booking đã bị hủy trước đó. |
| `409 Conflict` | `INVALID_BOOKING_STATE_TRANSITION` | Trạng thái hiện tại không cho phép hủy. |
| `503 Service Unavailable` | `POS_TEMPORARY_ERROR` | POS không thể hủy booking tại thời điểm hiện tại. |

---

## 2.12. List Reservations of a Booking

```http
GET /api/bookings/{booking_id}/reservations
```

### Response `200 OK`

```json
{
  "data": [
    {
      "reservation_id": "550e8400-e29b-41d4-a716-446655440601",
      "booking_id": "550e8400-e29b-41d4-a716-446655440501",
      "person_index": 1,
      "therapist_id": "550e8400-e29b-41d4-a716-446655440201",
      "start_time": "10:00",
      "end_time": "11:15",
      "status": "assigned"
    }
  ]
}
```

### Error Responses

| HTTP Status | Error Code | Trường hợp |
|---:|---|---|
| `400 Bad Request` | `INVALID_BOOKING_ID` | `booking_id` không đúng format UUID. |
| `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Request chưa có thông tin xác thực cần thiết. |
| `403 Forbidden` | `BOOKING_ACCESS_DENIED` | Người dùng không có quyền xem reservation của booking. |
| `404 Not Found` | `BOOKING_NOT_FOUND` | Không tìm thấy booking. |
| `500 Internal Server Error` | `INTERNAL_SERVER_ERROR` | Backend xảy ra lỗi ngoài dự kiến. |

---

# 3. Admin APIs

Các API trong nhóm này dành cho Admin/Quản lý. Những endpoint này thường yêu cầu `Authorization` header.

## 3.1. Shops

```http
GET    /api/admin/shops
POST   /api/admin/shops
GET    /api/admin/shops/{shop_id}
PATCH  /api/admin/shops/{shop_id}
```

Không hard delete shop đã có dữ liệu liên quan. Nên dùng `is_active = false`.

### 3.1.1. List Shops

```http
GET /api/admin/shops?is_active=true
```

### Response `200 OK`

```json
{
  "data": [
    {
      "shop_id": "550e8400-e29b-41d4-a716-446655440001",
      "shop_code": "SHOP001",
      "pos_shop_code": "POS_SHOP_001",
      "name": "Massage Shop A",
      "address": "Tokyo",
      "phone": "0900000000",
      "is_active": true,
      "created_at": "2026-07-01T09:00:00+07:00",
      "updated_at": "2026-07-10T10:30:00+07:00"
    }
  ],
  "meta": {
    "total": 1
  }
}
```

### 3.1.2. Create Shop

```http
POST /api/admin/shops
```

### Request Body

```json
{
  "shop_code": "SHOP001",
  "pos_shop_code": "POS_SHOP_001",
  "name": "Massage Shop A",
  "address": "Tokyo",
  "phone": "0900000000",
  "is_active": true
}
```

### Response `201 Created`

```json
{
  "data": {
    "shop_id": "550e8400-e29b-41d4-a716-446655440001",
    "shop_code": "SHOP001",
    "pos_shop_code": "POS_SHOP_001",
    "name": "Massage Shop A",
    "address": "Tokyo",
    "phone": "0900000000",
    "is_active": true,
    "created_at": "2026-07-13T09:00:00+07:00",
    "updated_at": "2026-07-13T09:00:00+07:00"
  }
}
```

### 3.1.3. Update Shop

```http
PATCH /api/admin/shops/550e8400-e29b-41d4-a716-446655440001
```

### Request Body

```json
{
  "name": "Massage Shop A - Main Branch",
  "phone": "0901111111",
  "is_active": true
}
```

### Response `200 OK`

```json
{
  "data": {
    "shop_id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Massage Shop A - Main Branch",
    "phone": "0901111111",
    "is_active": true,
    "updated_at": "2026-07-13T09:15:00+07:00"
  }
}
```

### Error Responses

| Method và endpoint | HTTP Status | Error Code | Trường hợp |
|---|---:|---|---|
| Tất cả endpoint | `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Chưa cung cấp access token hợp lệ. |
| Tất cả endpoint | `403 Forbidden` | `ADMIN_PERMISSION_REQUIRED` | Tài khoản không có quyền Admin. |
| `GET /api/admin/shops` | `400 Bad Request` | `INVALID_QUERY_PARAMETER` | Query parameter không hợp lệ. |
| `GET/PATCH /api/admin/shops/{shop_id}` | `400 Bad Request` | `INVALID_SHOP_ID` | `shop_id` không đúng format UUID. |
| `GET/PATCH /api/admin/shops/{shop_id}` | `404 Not Found` | `SHOP_NOT_FOUND` | Không tìm thấy shop. |
| `POST /api/admin/shops` | `409 Conflict` | `SHOP_CODE_ALREADY_EXISTS` | `shop_code` đã tồn tại. |
| `POST /api/admin/shops` | `409 Conflict` | `POS_SHOP_CODE_ALREADY_EXISTS` | `pos_shop_code` đã được mapping với shop khác. |
| `POST/PATCH` | `422 Unprocessable Entity` | `INVALID_SHOP_DATA` | Dữ liệu shop không đáp ứng validation rule. |

---

## 3.2. Courses

```http
GET    /api/admin/shops/{shop_id}/courses
POST   /api/admin/shops/{shop_id}/courses
GET    /api/admin/courses/{course_id}
PATCH  /api/admin/courses/{course_id}
```

### 3.2.1. List Courses of a Shop

```http
GET /api/admin/shops/550e8400-e29b-41d4-a716-446655440001/courses?course_type=main&is_active=true
```

### Response `200 OK`

```json
{
  "data": [
    {
      "course_id": "550e8400-e29b-41d4-a716-446655440101",
      "shop_id": "550e8400-e29b-41d4-a716-446655440001",
      "pos_course_code": "POS_COURSE_001",
      "name": "Body Massage 60 min",
      "duration_minutes": 60,
      "price": 6000,
      "course_type": "main",
      "is_active": true
    }
  ]
}
```

### 3.2.2. Create Course

```http
POST /api/admin/shops/550e8400-e29b-41d4-a716-446655440001/courses
```

### Request Body

```json
{
  "pos_course_code": "POS_COURSE_001",
  "name": "Body Massage 60 min",
  "duration_minutes": 60,
  "price": 6000,
  "course_type": "main",
  "is_active": true
}
```

### Response `201 Created`

```json
{
  "data": {
    "course_id": "550e8400-e29b-41d4-a716-446655440101",
    "shop_id": "550e8400-e29b-41d4-a716-446655440001",
    "pos_course_code": "POS_COURSE_001",
    "name": "Body Massage 60 min",
    "duration_minutes": 60,
    "price": 6000,
    "course_type": "main",
    "is_active": true,
    "created_at": "2026-07-13T09:00:00+07:00",
    "updated_at": "2026-07-13T09:00:00+07:00"
  }
}
```

### 3.2.3. Update Course

```http
PATCH /api/admin/courses/550e8400-e29b-41d4-a716-446655440101
```

### Request Body

```json
{
  "name": "Body Massage 75 min",
  "duration_minutes": 75,
  "price": 7500,
  "is_active": true
}
```

### Response `200 OK`

```json
{
  "data": {
    "course_id": "550e8400-e29b-41d4-a716-446655440101",
    "name": "Body Massage 75 min",
    "duration_minutes": 75,
    "price": 7500,
    "is_active": true,
    "updated_at": "2026-07-13T09:20:00+07:00"
  }
}
```

### Error Responses

| Method và endpoint | HTTP Status | Error Code | Trường hợp |
|---|---:|---|---|
| Tất cả endpoint | `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Chưa cung cấp access token hợp lệ. |
| Tất cả endpoint | `403 Forbidden` | `ADMIN_PERMISSION_REQUIRED` | Tài khoản không có quyền Admin. |
| Endpoint chứa `{shop_id}` | `404 Not Found` | `SHOP_NOT_FOUND` | Không tìm thấy shop. |
| Endpoint chứa `{course_id}` | `400 Bad Request` | `INVALID_COURSE_ID` | `course_id` không đúng format UUID. |
| `GET/PATCH /api/admin/courses/{course_id}` | `404 Not Found` | `COURSE_NOT_FOUND` | Không tìm thấy course. |
| `POST` | `409 Conflict` | `POS_COURSE_CODE_ALREADY_EXISTS` | `pos_course_code` đã tồn tại trong phạm vi shop. |
| `POST/PATCH` | `422 Unprocessable Entity` | `INVALID_COURSE_DATA` | Duration, price hoặc `course_type` không hợp lệ. |
| `POST/PATCH` | `422 Unprocessable Entity` | `INVALID_DURATION` | Duration không phải bội số của 15 phút. |

---

## 3.3. Therapists

```http
GET    /api/admin/shops/{shop_id}/therapists
POST   /api/admin/shops/{shop_id}/therapists
GET    /api/admin/therapists/{therapist_id}
PATCH  /api/admin/therapists/{therapist_id}
```

### 3.3.1. List Therapists of a Shop

```http
GET /api/admin/shops/550e8400-e29b-41d4-a716-446655440001/therapists?is_active=true
```

### Response `200 OK`

```json
{
  "data": [
    {
      "therapist_id": "550e8400-e29b-41d4-a716-446655440201",
      "shop_id": "550e8400-e29b-41d4-a716-446655440001",
      "pos_therapist_code": "POS_THERAPIST_001",
      "name": "Yuki",
      "gender": "female",
      "is_active": true
    }
  ]
}
```

### 3.3.2. Create Therapist

```http
POST /api/admin/shops/550e8400-e29b-41d4-a716-446655440001/therapists
```

### Request Body

```json
{
  "pos_therapist_code": "POS_THERAPIST_001",
  "name": "Yuki",
  "gender": "female",
  "is_active": true
}
```

### Response `201 Created`

```json
{
  "data": {
    "therapist_id": "550e8400-e29b-41d4-a716-446655440201",
    "shop_id": "550e8400-e29b-41d4-a716-446655440001",
    "pos_therapist_code": "POS_THERAPIST_001",
    "name": "Yuki",
    "gender": "female",
    "is_active": true,
    "created_at": "2026-07-13T09:00:00+07:00",
    "updated_at": "2026-07-13T09:00:00+07:00"
  }
}
```

### 3.3.3. Update Therapist

```http
PATCH /api/admin/therapists/550e8400-e29b-41d4-a716-446655440201
```

### Request Body

```json
{
  "name": "Yuki Tanaka",
  "is_active": true
}
```

### Response `200 OK`

```json
{
  "data": {
    "therapist_id": "550e8400-e29b-41d4-a716-446655440201",
    "name": "Yuki Tanaka",
    "is_active": true,
    "updated_at": "2026-07-13T09:30:00+07:00"
  }
}
```

### Error Responses

| Method và endpoint | HTTP Status | Error Code | Trường hợp |
|---|---:|---|---|
| Tất cả endpoint | `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Chưa cung cấp access token hợp lệ. |
| Tất cả endpoint | `403 Forbidden` | `ADMIN_PERMISSION_REQUIRED` | Tài khoản không có quyền Admin. |
| Endpoint chứa `{shop_id}` | `404 Not Found` | `SHOP_NOT_FOUND` | Không tìm thấy shop. |
| Endpoint chứa `{therapist_id}` | `400 Bad Request` | `INVALID_THERAPIST_ID` | `therapist_id` không đúng format UUID. |
| `GET/PATCH /api/admin/therapists/{therapist_id}` | `404 Not Found` | `THERAPIST_NOT_FOUND` | Không tìm thấy therapist. |
| `POST` | `409 Conflict` | `POS_THERAPIST_CODE_ALREADY_EXISTS` | `pos_therapist_code` đã tồn tại trong phạm vi shop. |
| `POST/PATCH` | `422 Unprocessable Entity` | `INVALID_THERAPIST_DATA` | Name, gender hoặc trạng thái không hợp lệ. |

---

## 3.4. Therapist Shifts

```http
GET    /api/admin/shops/{shop_id}/therapist-shifts
POST   /api/admin/therapist-shifts
GET    /api/admin/therapist-shifts/{shift_id}
PATCH  /api/admin/therapist-shifts/{shift_id}
```

### Query Parameters

| Name | Type | Required | Mô tả |
|---|---:|---:|---|
| `work_date` | date | No | Filter theo ngày làm việc |
| `therapist_id` | string | No | Filter theo therapist |
| `is_active` | boolean | No | Filter theo trạng thái ca làm việc |

### 3.4.1. List Therapist Shifts

```http
GET /api/admin/shops/550e8400-e29b-41d4-a716-446655440001/therapist-shifts?work_date=2026-07-20&therapist_id=550e8400-e29b-41d4-a716-446655440201
```

### Response `200 OK`

```json
{
  "data": [
    {
      "shift_id": "550e8400-e29b-41d4-a716-446655440701",
      "shop_id": "550e8400-e29b-41d4-a716-446655440001",
      "therapist_id": "550e8400-e29b-41d4-a716-446655440201",
      "work_date": "2026-07-20",
      "start_time": "09:00",
      "end_time": "18:00",
      "is_active": true
    }
  ]
}
```

### 3.4.2. Create Therapist Shift

```http
POST /api/admin/therapist-shifts
```

### Request Body

```json
{
  "shop_id": "550e8400-e29b-41d4-a716-446655440001",
  "therapist_id": "550e8400-e29b-41d4-a716-446655440201",
  "work_date": "2026-07-20",
  "start_time": "09:00",
  "end_time": "18:00",
  "is_active": true
}
```

### Response `201 Created`

```json
{
  "data": {
    "shift_id": "550e8400-e29b-41d4-a716-446655440701",
    "shop_id": "550e8400-e29b-41d4-a716-446655440001",
    "therapist_id": "550e8400-e29b-41d4-a716-446655440201",
    "work_date": "2026-07-20",
    "start_time": "09:00",
    "end_time": "18:00",
    "is_active": true,
    "created_at": "2026-07-13T09:00:00+07:00",
    "updated_at": "2026-07-13T09:00:00+07:00"
  }
}
```

### 3.4.3. Update Therapist Shift

```http
PATCH /api/admin/therapist-shifts/550e8400-e29b-41d4-a716-446655440701
```

### Request Body

```json
{
  "start_time": "10:00",
  "end_time": "19:00",
  "is_active": true
}
```

### Response `200 OK`

```json
{
  "data": {
    "shift_id": "550e8400-e29b-41d4-a716-446655440701",
    "start_time": "10:00",
    "end_time": "19:00",
    "is_active": true,
    "updated_at": "2026-07-13T09:45:00+07:00"
  }
}
```

### Error Responses

| Method và endpoint | HTTP Status | Error Code | Trường hợp |
|---|---:|---|---|
| Tất cả endpoint | `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Chưa cung cấp access token hợp lệ. |
| Tất cả endpoint | `403 Forbidden` | `ADMIN_PERMISSION_REQUIRED` | Tài khoản không có quyền Admin. |
| Endpoint chứa `{shop_id}` | `404 Not Found` | `SHOP_NOT_FOUND` | Không tìm thấy shop. |
| Request có `therapist_id` | `404 Not Found` | `THERAPIST_NOT_FOUND` | Không tìm thấy therapist hoặc therapist không thuộc shop. |
| Endpoint chứa `{shift_id}` | `400 Bad Request` | `INVALID_SHIFT_ID` | `shift_id` không đúng format UUID. |
| `GET/PATCH /api/admin/therapist-shifts/{shift_id}` | `404 Not Found` | `SHIFT_NOT_FOUND` | Không tìm thấy ca làm việc. |
| `POST/PATCH` | `409 Conflict` | `SHIFT_TIME_CONFLICT` | Ca làm việc bị trùng với ca đã tồn tại. |
| `POST/PATCH` | `422 Unprocessable Entity` | `INVALID_SHIFT_TIME_RANGE` | `end_time` không lớn hơn `start_time`. |
| `PATCH` | `409 Conflict` | `SHIFT_AFFECTS_EXISTING_BOOKINGS` | Thay đổi ca làm ảnh hưởng đến booking đã được xác nhận. |

---

## 3.5. Customer Restrictions

Resource này đại diện cho NG list records.

```http
GET    /api/admin/customer-restrictions
POST   /api/admin/customer-restrictions
GET    /api/admin/customer-restrictions/{restriction_id}
PATCH  /api/admin/customer-restrictions/{restriction_id}
```

### Query Parameters

| Name | Type | Required | Mô tả |
|---|---:|---:|---|
| `phone` | string | No | Filter theo số điện thoại |
| `is_active` | boolean | No | Filter record còn hiệu lực |

### 3.5.1. List Customer Restrictions

```http
GET /api/admin/customer-restrictions?phone=09012345678&is_active=true
```

### Response `200 OK`

```json
{
  "data": [
    {
      "restriction_id": "550e8400-e29b-41d4-a716-446655440801",
      "phone": "09012345678",
      "reason": "No-show multiple times",
      "is_active": true,
      "created_at": "2026-07-01T09:00:00+07:00",
      "updated_at": "2026-07-01T09:00:00+07:00"
    }
  ]
}
```

### 3.5.2. Create Customer Restriction

```http
POST /api/admin/customer-restrictions
```

### Request Body

```json
{
  "phone": "09012345678",
  "reason": "No-show multiple times",
  "is_active": true
}
```

### Response `201 Created`

```json
{
  "data": {
    "restriction_id": "550e8400-e29b-41d4-a716-446655440801",
    "phone": "09012345678",
    "reason": "No-show multiple times",
    "is_active": true,
    "created_at": "2026-07-13T09:00:00+07:00",
    "updated_at": "2026-07-13T09:00:00+07:00"
  }
}
```

### 3.5.3. Update Customer Restriction

```http
PATCH /api/admin/customer-restrictions/550e8400-e29b-41d4-a716-446655440801
```

### Request Body

```json
{
  "reason": "No-show multiple times, confirmed by manager",
  "is_active": false
}
```

### Response `200 OK`

```json
{
  "data": {
    "restriction_id": "550e8400-e29b-41d4-a716-446655440801",
    "phone": "09012345678",
    "reason": "No-show multiple times, confirmed by manager",
    "is_active": false,
    "updated_at": "2026-07-13T10:00:00+07:00"
  }
}
```

### Error Responses

| Method và endpoint | HTTP Status | Error Code | Trường hợp |
|---|---:|---|---|
| Tất cả endpoint | `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Chưa cung cấp access token hợp lệ. |
| Tất cả endpoint | `403 Forbidden` | `ADMIN_PERMISSION_REQUIRED` | Tài khoản không có quyền Admin. |
| Endpoint chứa `{restriction_id}` | `400 Bad Request` | `INVALID_RESTRICTION_ID` | `restriction_id` không đúng format UUID. |
| `GET/PATCH /api/admin/customer-restrictions/{restriction_id}` | `404 Not Found` | `CUSTOMER_RESTRICTION_NOT_FOUND` | Không tìm thấy restriction record. |
| `POST` | `409 Conflict` | `CUSTOMER_RESTRICTION_ALREADY_EXISTS` | Phone đã có restriction record còn hiệu lực. |
| `POST/PATCH` | `422 Unprocessable Entity` | `INVALID_PHONE` | Phone không đúng format. |
| `POST/PATCH` | `422 Unprocessable Entity` | `INVALID_RESTRICTION_DATA` | Reason hoặc trạng thái không hợp lệ. |

---

## 3.6. Booking Monitoring

```http
GET /api/admin/bookings
GET /api/admin/bookings/{booking_id}
```

### Query Parameters

| Name | Type | Required | Mô tả |
|---|---:|---:|---|
| `shop_id` | string | No | Filter theo shop |
| `booking_date` | date | No | Filter theo ngày booking |
| `status` | string | No | Filter theo status |
| `phone` | string | No | Filter theo số điện thoại khách hàng |
| `pos_booking_code` | string | No | Filter theo mã booking POS |
| `limit` | integer | No | Page size |
| `cursor` | string | No | Cursor pagination token |

### 3.6.1. List Bookings for Admin

```http
GET /api/admin/bookings?shop_id=550e8400-e29b-41d4-a716-446655440001&booking_date=2026-07-20&status=confirmed&limit=20
```

### Response `200 OK`

```json
{
  "data": [
    {
      "booking_id": "550e8400-e29b-41d4-a716-446655440501",
      "pos_booking_code": "POS-20260720-001",
      "shop_id": "550e8400-e29b-41d4-a716-446655440001",
      "customer": {
        "customer_id": "550e8400-e29b-41d4-a716-446655440301",
        "phone": "09012345678",
        "name": "Nguyen Van A"
      },
      "booking_date": "2026-07-20",
      "start_time": "10:00",
      "end_time": "11:15",
      "number_of_people": 1,
      "status": "confirmed"
    }
  ],
  "meta": {
    "limit": 20,
    "next_cursor": null
  }
}
```

### 3.6.2. Get Booking Detail for Admin

```http
GET /api/admin/bookings/550e8400-e29b-41d4-a716-446655440501
```

### Response `200 OK`

```json
{
  "data": {
    "booking_id": "550e8400-e29b-41d4-a716-446655440501",
    "pos_booking_code": "POS-20260720-001",
    "status": "confirmed",
    "shop": {
      "shop_id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "Massage Shop A"
    },
    "customer": {
      "customer_id": "550e8400-e29b-41d4-a716-446655440301",
      "phone": "09012345678",
      "name": "Nguyen Van A",
      "is_member": true,
      "member_rank": "gold",
      "visit_count": 12
    },
    "booking_date": "2026-07-20",
    "start_time": "10:00",
    "end_time": "11:15",
    "number_of_people": 1,
    "total_duration_minutes": 75,
    "reservations": [
      {
        "reservation_id": "550e8400-e29b-41d4-a716-446655440601",
        "person_index": 1,
        "therapist": {
          "therapist_id": "550e8400-e29b-41d4-a716-446655440201",
          "name": "Yuki"
        },
        "courses": [
          {
            "course_role": "main",
            "course_name_snapshot": "Body Massage 60 min",
            "duration_snapshot": 60,
            "price_snapshot": 6000
          },
          {
            "course_role": "addon",
            "course_name_snapshot": "Head Spa 15 min",
            "duration_snapshot": 15,
            "price_snapshot": 1500
          }
        ]
      }
    ]
  }
}
```

### Error Responses

| Method và endpoint | HTTP Status | Error Code | Trường hợp |
|---|---:|---|---|
| Tất cả endpoint | `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Chưa cung cấp access token hợp lệ. |
| Tất cả endpoint | `403 Forbidden` | `ADMIN_PERMISSION_REQUIRED` | Tài khoản không có quyền xem booking. |
| `GET /api/admin/bookings` | `400 Bad Request` | `INVALID_QUERY_PARAMETER` | Filter, `limit` hoặc `cursor` không hợp lệ. |
| `GET /api/admin/bookings/{booking_id}` | `400 Bad Request` | `INVALID_BOOKING_ID` | `booking_id` không đúng format UUID. |
| `GET /api/admin/bookings/{booking_id}` | `404 Not Found` | `BOOKING_NOT_FOUND` | Không tìm thấy booking. |
| Tất cả endpoint | `503 Service Unavailable` | `POS_TEMPORARY_ERROR` | Không thể lấy trạng thái booking mới nhất từ POS. |

> Danh sách không có kết quả vẫn trả `200 OK` với `data: []`.

---

# 4. Therapist APIs

## 4.1. Get My Schedule

```http
GET /api/therapists/me/schedule
```

### Query Parameters

| Name | Type | Required | Mô tả |
|---|---:|---:|---|
| `date` | date | Yes | Ngày cần xem lịch |

### Example

```http
GET /api/therapists/me/schedule?date=2026-07-20
```

### Response `200 OK`

```json
{
  "data": {
    "therapist_id": "550e8400-e29b-41d4-a716-446655440201",
    "date": "2026-07-20",
    "shift": {
      "start_time": "09:00",
      "end_time": "18:00"
    },
    "reservations": [
      {
        "reservation_id": "550e8400-e29b-41d4-a716-446655440601",
        "booking_id": "550e8400-e29b-41d4-a716-446655440501",
        "start_time": "10:00",
        "end_time": "11:15",
        "course_names": [
          "Body Massage 60 min",
          "Head Spa 15 min"
        ],
        "booking_status": "confirmed"
      }
    ]
  }
}
```

### Error Responses

| HTTP Status | Error Code | Trường hợp |
|---:|---|---|
| `400 Bad Request` | `INVALID_DATE` | Thiếu `date` hoặc ngày không đúng format `YYYY-MM-DD`. |
| `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Chưa cung cấp access token hợp lệ. |
| `403 Forbidden` | `THERAPIST_PERMISSION_REQUIRED` | Tài khoản hiện tại không thuộc role Therapist. |
| `404 Not Found` | `THERAPIST_NOT_FOUND` | Không tìm thấy therapist tương ứng với tài khoản đăng nhập. |
| `500 Internal Server Error` | `INTERNAL_SERVER_ERROR` | Backend xảy ra lỗi ngoài dự kiến. |

> Không có ca làm hoặc reservation trong ngày vẫn trả `200 OK`; `shift` có thể là `null` và `reservations` là mảng rỗng.

---


# 5. Error Response Format

Khi API xử lý thất bại, backend trả response lỗi theo một cấu trúc thống nhất để frontend xử lý theo `code` và đội phát triển dễ trace nguyên nhân.

```json
{
  "type": "https://api.example.com/problems/slot-conflict",
  "title": "Slot conflict",
  "status": 409,
  "detail": "The selected slot is no longer available.",
  "code": "SLOT_CONFLICT",
  "instance": "/api/bookings"
}
```

| Field | Type | Mô tả |
|---|---|---|
| `type` | string | URI định danh loại lỗi. Có thể trỏ đến tài liệu mô tả lỗi. |
| `title` | string | Tên lỗi ngắn gọn, ổn định giữa các response cùng loại. |
| `status` | integer | HTTP status code của response. |
| `detail` | string | Mô tả lỗi cụ thể của request hiện tại. |
| `code` | string | Application error code để frontend xử lý logic. |
| `instance` | string | API path hoặc request instance nơi lỗi xảy ra. |
| `errors` | array | Optional. Danh sách lỗi theo từng field khi validation thất bại. |

### Validation Error Example — `422 Unprocessable Entity`

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Validation error",
  "status": 422,
  "detail": "One or more fields are invalid.",
  "code": "VALIDATION_ERROR",
  "instance": "/api/bookings",
  "errors": [
    {
      "field": "number_of_people",
      "message": "Value must be between 1 and 3."
    }
  ]
}
```

### Authentication Error Example — `401 Unauthorized`

```json
{
  "type": "https://api.example.com/problems/authentication-required",
  "title": "Authentication required",
  "status": 401,
  "detail": "A valid access token is required.",
  "code": "AUTHENTICATION_REQUIRED",
  "instance": "/api/admin/shops"
}
```

### Resource Not Found Example — `404 Not Found`

```json
{
  "type": "https://api.example.com/problems/booking-not-found",
  "title": "Booking not found",
  "status": 404,
  "detail": "The requested booking does not exist.",
  "code": "BOOKING_NOT_FOUND",
  "instance": "/api/bookings/550e8400-e29b-41d4-a716-446655440999"
}
```

---

# 6. Error Code Reference

## 6.1. Common Errors

| Error Code | HTTP Status | Ý nghĩa |
|---|---:|---|
| `INVALID_REQUEST_BODY` | 400 | Request body sai JSON format hoặc thiếu dữ liệu bắt buộc. |
| `INVALID_QUERY_PARAMETER` | 400 | Query parameter sai format hoặc không được hỗ trợ. |
| `AUTHENTICATION_REQUIRED` | 401 | Thiếu hoặc sai access token. |
| `ADMIN_PERMISSION_REQUIRED` | 403 | Tài khoản không có quyền Admin. |
| `THERAPIST_PERMISSION_REQUIRED` | 403 | Tài khoản không có quyền Therapist. |
| `INTERNAL_SERVER_ERROR` | 500 | Backend xảy ra lỗi ngoài dự kiến. |
| `POS_TEMPORARY_ERROR` | 503 | POS không phản hồi hoặc tạm thời không khả dụng. |

## 6.2. Shop and Course Errors

| Error Code | HTTP Status | Ý nghĩa |
|---|---:|---|
| `INVALID_SHOP_ID` | 400 | `shop_id` không đúng format UUID. |
| `SHOP_NOT_FOUND` | 404 | Không tìm thấy shop. |
| `SHOP_INACTIVE` | 422 | Shop không hoạt động. |
| `SHOP_CODE_ALREADY_EXISTS` | 409 | `shop_code` đã tồn tại. |
| `POS_SHOP_CODE_ALREADY_EXISTS` | 409 | `pos_shop_code` đã được sử dụng. |
| `INVALID_COURSE_ID` | 400 | `course_id` không đúng format UUID. |
| `COURSE_NOT_FOUND` | 404 | Không tìm thấy course. |
| `POS_COURSE_CODE_ALREADY_EXISTS` | 409 | `pos_course_code` đã tồn tại trong shop. |
| `INVALID_COURSE_COMBO` | 422 | Combo main course/add-on không hợp lệ. |
| `ADDON_REQUIRES_MAIN_COURSE` | 422 | Add-on được chọn nhưng thiếu main course. |
| `INVALID_DURATION` | 422 | Duration không hợp lệ hoặc không phải bội số của 15 phút. |

## 6.3. Therapist and Shift Errors

| Error Code | HTTP Status | Ý nghĩa |
|---|---:|---|
| `INVALID_THERAPIST_ID` | 400 | `therapist_id` không đúng format UUID. |
| `THERAPIST_NOT_FOUND` | 404 | Không tìm thấy therapist. |
| `THERAPIST_NOT_AVAILABLE` | 422 | Therapist không khả dụng trong thời gian yêu cầu. |
| `POS_THERAPIST_CODE_ALREADY_EXISTS` | 409 | `pos_therapist_code` đã tồn tại trong shop. |
| `INVALID_SHIFT_ID` | 400 | `shift_id` không đúng format UUID. |
| `SHIFT_NOT_FOUND` | 404 | Không tìm thấy ca làm việc. |
| `SHIFT_TIME_CONFLICT` | 409 | Ca làm việc bị trùng. |
| `INVALID_SHIFT_TIME_RANGE` | 422 | Khoảng thời gian ca làm việc không hợp lệ. |
| `SHIFT_AFFECTS_EXISTING_BOOKINGS` | 409 | Thay đổi ca làm ảnh hưởng booking hiện có. |

## 6.4. Booking Errors

| Error Code | HTTP Status | Ý nghĩa |
|---|---:|---|
| `INVALID_BOOKING_ID` | 400 | `booking_id` không đúng format UUID. |
| `BOOKING_NOT_FOUND` | 404 | Không tìm thấy booking. |
| `BOOKING_ACCESS_DENIED` | 403 | Không có quyền xem hoặc thay đổi booking. |
| `INVALID_NUMBER_OF_PEOPLE` | 422 | Số người phải từ 1 đến 3. |
| `GROUP_BOOKING_CANNOT_REQUEST_THERAPIST` | 422 | Booking nhóm không được yêu cầu therapist. |
| `BOOKING_TOO_SOON` | 422 | Booking không đáp ứng thời gian đặt trước tối thiểu 15 phút. |
| `SLOT_NOT_AVAILABLE` | 422 | Không có slot phù hợp. |
| `SLOT_CONFLICT` | 409 | Slot đã bị đặt mất trước khi thao tác hoàn tất. |
| `BOOKING_ALREADY_CANCELLED` | 409 | Booking đã bị hủy trước đó. |
| `INVALID_BOOKING_STATE_TRANSITION` | 409 | Không thể chuyển booking sang trạng thái yêu cầu. |
| `MISSING_IDEMPOTENCY_KEY` | 400 | Thiếu `Idempotency-Key` khi tạo booking. |
| `IDEMPOTENCY_CONFLICT` | 409 | Cùng idempotency key nhưng payload khác nhau. |

## 6.5. Customer Restriction Errors

| Error Code | HTTP Status | Ý nghĩa |
|---|---:|---|
| `INVALID_PHONE` | 422 | Phone không đúng format. |
| `CUSTOMER_IN_NG_LIST` | 403 | Phone thuộc NG list. |
| `INVALID_RESTRICTION_ID` | 400 | `restriction_id` không đúng format UUID. |
| `CUSTOMER_RESTRICTION_NOT_FOUND` | 404 | Không tìm thấy restriction record. |
| `CUSTOMER_RESTRICTION_ALREADY_EXISTS` | 409 | Phone đã có restriction record còn hiệu lực. |

---

# 7. Endpoint Summary

## Public

```http
GET    /api/shops
GET    /api/shops/{shop_id}
GET    /api/shops/{shop_id}/courses
GET    /api/shops/{shop_id}/available-slots
GET    /api/shops/{shop_id}/available-therapists
POST   /api/booking-eligibility-checks
POST   /api/bookings
GET    /api/bookings
GET    /api/bookings/{booking_id}
PATCH  /api/bookings/{booking_id}
GET    /api/bookings/{booking_id}/reservations
```

## Admin

```http
GET    /api/admin/shops
POST   /api/admin/shops
GET    /api/admin/shops/{shop_id}
PATCH  /api/admin/shops/{shop_id}

GET    /api/admin/shops/{shop_id}/courses
POST   /api/admin/shops/{shop_id}/courses
GET    /api/admin/courses/{course_id}
PATCH  /api/admin/courses/{course_id}

GET    /api/admin/shops/{shop_id}/therapists
POST   /api/admin/shops/{shop_id}/therapists
GET    /api/admin/therapists/{therapist_id}
PATCH  /api/admin/therapists/{therapist_id}

GET    /api/admin/shops/{shop_id}/therapist-shifts
POST   /api/admin/therapist-shifts
GET    /api/admin/therapist-shifts/{shift_id}
PATCH  /api/admin/therapist-shifts/{shift_id}

GET    /api/admin/customer-restrictions
POST   /api/admin/customer-restrictions
GET    /api/admin/customer-restrictions/{restriction_id}
PATCH  /api/admin/customer-restrictions/{restriction_id}

GET    /api/admin/bookings
GET    /api/admin/bookings/{booking_id}
```

## Therapist

```http
GET /api/therapists/me/schedule
```
