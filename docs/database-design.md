# Database Design
# Booking System ER Diagram

```mermaid
erDiagram
    SHOPS ||--o{ COURSES : "has"
    SHOPS ||--o{ THERAPISTS : "has"
    SHOPS ||--o{ THERAPIST_SHIFTS : "has"
    SHOPS ||--o{ BOOKINGS : "has"

    THERAPISTS ||--o{ THERAPIST_SHIFTS : "works"
    THERAPISTS ||--o{ RESERVATIONS : "assigned to"
    THERAPISTS |o--o{ BOOKINGS : "requested optional"

    CUSTOMERS ||--o{ BOOKINGS : "makes"

    BOOKINGS ||--o{ RESERVATIONS : "contains"

    RESERVATIONS ||--o{ RESERVATION_COURSES : "includes"

    COURSES ||--o{ RESERVATION_COURSES : "used in"

    SHOPS {
        uuid shop_id PK
        varchar shop_code UK
        varchar pos_shop_code UK
        varchar name
        varchar address
        varchar phone
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    COURSES {
        uuid course_id PK
        uuid shop_id FK
        varchar pos_course_code UK(shop_id)
        varchar name
        integer duration_minutes
        decimal price
        enum course_type
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    THERAPISTS {
        uuid therapist_id PK
        uuid shop_id FK
        varchar pos_therapist_code UK(shop_id)
        varchar name
        enum gender
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    THERAPIST_SHIFTS {
        uuid shift_id PK
        uuid therapist_id FK
        uuid shop_id FK
        date work_date
        time start_time
        time end_time
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    CUSTOMERS {
        uuid customer_id PK
        varchar phone UK
        varchar name
        varchar pos_customer_code
        boolean is_member
        varchar member_rank
        integer visit_count
        timestamp last_synced_at
        timestamp created_at
        timestamp updated_at
    }

    BOOKINGS {
        uuid booking_id PK
        uuid shop_id FK
        uuid customer_id FK
        varchar pos_booking_code UK
        date booking_date
        time start_time
        time end_time
        integer number_of_people
        integer total_duration_minutes
        enum status
        enum therapist_request_type
        uuid requested_therapist_id FK
        enum requested_gender
        uuid idempotency_key UK
        varchar cancel_reason
        timestamp cancelled_at
        timestamp created_at
        timestamp updated_at
    }

    RESERVATIONS {
        uuid reservation_id PK
        uuid booking_id FK
        integer person_index
        uuid therapist_id FK
        time start_time
        time end_time
        enum status
        timestamp created_at
        timestamp updated_at
    }

    RESERVATION_COURSES {
        uuid reservation_course_id PK
        uuid reservation_id FK
        uuid course_id FK
        enum course_role
        integer duration_snapshot
        decimal price_snapshot
        varchar course_name_snapshot
        timestamp created_at
    }
```

Database này được thiết kế để quản lý toàn bộ luồng đặt lịch massage từ lúc khách chọn cửa hàng, chọn dịch vụ, chọn giờ, nhập số điện thoại cho đến khi tạo booking chính thức qua POS. Mỗi shop sẽ có danh sách dịch vụ, therapist và ca làm riêng. Khách hàng được nhận dạng bằng số điện thoại, sau đó hệ thống tạo booking; nếu booking nhóm thì một booking sẽ gồm nhiều reservation, mỗi reservation đại diện cho một người và được gán therapist cụ thể. Các dịch vụ khách chọn được lưu qua bảng `reservation_courses` để thể hiện một reservation có course chính và có thể có nhiều add-on. 

# Note

* `number_of_people` chỉ từ 1 đến 3.
* Booking nhóm không được chỉ định therapist, áp dụng từ 2 người trở lên.
* `therapist_request_type` gồm: `none`, `specific`, `gender`.
* `(shop_id, pos_course_code)` unique — mỗi shop có mã course riêng.
* `(shop_id, pos_therapist_code)` unique — mỗi shop có mã therapist riêng.
* Add-on phải đi kèm main course, không được đặt riêng.
* Mỗi reservation nên có đúng 1 main course.
* Một reservation có thể có nhiều add-on.
* Duration phải là bội số của 15 phút.
* Booking phải được đặt trước tối thiểu 15 phút.
* Therapist không được bị gán trùng giờ.
* Số điện thoại thuộc NG list thì không cho tạo booking.
* Slot không lưu thành bảng riêng vì slot là kết quả tính toán từ shop, ngày, dịch vụ, duration, therapist shift, reservation hiện có và POS.

# Note

Các bảng đã có `created_at`, `updated_at` đầy đủ. Riêng `reservation_courses` chỉ có `created_at` vì đây là bảng ghi snapshot, không cần cập nhật sau.
