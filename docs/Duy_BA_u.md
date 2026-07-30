# Draft nghiệp vụ — Hệ thống đặt lịch massage

## 1. Business Entities & Attributes

### 1.1. Shop — Cửa hàng

Thuộc tính:
- `shop_id` (thêm để định danh kỹ thuật; nếu không có id thì khó liên kết shop với course, therapist, slot và booking trong hệ thống)
- `shop_code` — mã riêng của cửa hàng
- `name` — tên cửa hàng
- `address` — địa chỉ
- `phone` — số điện thoại

Ghi chú: Không thêm `status`, `opening_hours` vì mô tả chỉ nói cửa hàng có thể nghỉ hoặc không có nhân viên theo ngày, nhưng chưa mô tả thuộc tính trạng thái/giờ mở cửa cố định.

### 1.2. Course — Dịch vụ

Thuộc tính:
- `course_id` (thêm để định danh kỹ thuật; nếu không có id thì khó tham chiếu course trong booking và combo dịch vụ)
- `shop_id` — cửa hàng cung cấp dịch vụ
- `name` — tên dịch vụ
- `duration_minutes` — thời lượng dịch vụ, bội số 15 phút
- `price` — giá tiền
- `course_type` — loại dịch vụ: `main_course` hoặc `add_on`

Ghi chú: Không thêm `status` vì nghiệp vụ chỉ nói danh sách dịch vụ có thể thay đổi theo ngày, không nói mỗi course có trạng thái cố định.

### 1.3. Therapist — Nhân viên trị liệu

Thuộc tính:
- `therapist_id` (thêm để định danh kỹ thuật; nếu không có id thì khó kiểm tra trùng lịch và gán therapist cho reservation)
- `shop_id` — cửa hàng mà therapist thuộc về
- `name` — tên therapist
- `gender` — giới tính nam/nữ

Ghi chú: Không lưu trực tiếp `working_shift` trong Therapist vì lịch làm việc thay đổi theo ngày/ca. Lịch làm việc được tách thành entity `Shift`.

### 1.4. Shift — Ca làm việc của therapist

Thuộc tính:
- `shift    _id` (thêm để định danh kỹ thuật cho từng ca làm việc)
- `therapist_id` — therapist thuộc ca làm việc
- `shop_id` — cửa hàng nơi therapist làm việc
- `work_date` — ngày làm việc
- `start_time` — giờ bắt đầu ca
- `end_time` — giờ kết thúc ca

Ghi chú: Entity này dùng để kiểm tra therapist có làm việc tại slot khách chọn hay không.

### 1.5. Customer — Khách hàng

Thuộc tính:
- `customer_id` (thêm để định danh kỹ thuật; tuy nhiên trong nghiệp vụ khách được nhận dạng chính bằng số điện thoại, nên trường này có thể không bắt buộc nếu hệ thống dùng `phone` làm khóa chính)
- `phone` — số điện thoại khách hàng
- `is_member` — khách là thành viên hay khách mới
- `rank` — hạng thành viên
- `visit_count` — số lần ghé thăm

Ghi chú: Không đưa `ng_flag` vào Customer vì NG List được hiểu là danh sách/rule kiểm tra số điện thoại bị cấm, chưa chốt là thực thể chính.

### 1.6. NG List — Danh sách kiểm tra số điện thoại bị cấm

NG List không chốt cứng là thực thể chính trong bản nghiệp vụ hiện tại. Có thể xem NG List là danh sách/rule kiểm tra trước khi tạo booking.

Nếu hệ thống cần quản lý NG List độc lập, có thể tách thành thực thể riêng với thuộc tính tối thiểu:
- `phone` — số điện thoại bị cấm tạo booking

Ghi chú: Không thêm `ng_list_id`, lý do bị cấm hoặc ngày tạo vì mô tả nghiệp vụ không đề cập.

### 1.7. Slot — Khung giờ khả dụng

Thuộc tính:
- `shop_id` — cửa hàng
- `date` — ngày đặt
- `start_time` — giờ bắt đầu khả dụng
- `course_id` hoặc danh sách dịch vụ được chọn — dùng để tính slot theo thời lượng
- `number_of_people` — số người đặt
- `therapist_request` — therapist được chỉ định nếu có

Ghi chú: Slot phụ thuộc vào nhiều điều kiện và có thể thay đổi theo thời gian thực, nên không nhất thiết là bảng lưu cố định. Có thể xem Slot là kết quả trả về từ API tìm slot khả dụng.

### 1.8. Booking — Đặt chỗ

Thuộc tính:
- `booking_id` (thêm để định danh kỹ thuật; nếu không có id thì khó liên kết booking với nhiều reservation trong booking nhóm)
- `shop_id` — cửa hàng được đặt
- `booking_date` — ngày đặt
- `start_time` — giờ bắt đầu
- `number_of_people` — số người
- `customer_phone` — số điện thoại khách hàng
- `pos_booking_code` — mã đặt chỗ do POS cấp sau khi tạo thành công
- `therapist_request` — yêu cầu therapist nếu có, chỉ áp dụng booking 1 người; có thể là tên cụ thể hoặc giới tính

Ghi chú: Không thêm `created_at`, `updated_at` vì mô tả nghiệp vụ không đề cập. Nếu triển khai hệ thống thật thì có thể thêm để audit, nhưng trong bản nghiệp vụ này chưa cần.

### 1.9. Reservation — Lượt phục vụ trong booking

Thuộc tính:
- `reservation_id` (thêm để định danh kỹ thuật; cần vì booking nhóm gồm nhiều reservation liên kết nhau)
- `booking_id` — booking cha
- `person_index` — số thứ tự người trong nhóm (thêm để phân biệt từng người trong booking nhóm; nếu không có thì khó biết reservation nào thuộc người nào)
- `start_time` — giờ bắt đầu của reservation
- `course_list` — danh sách dịch vụ của người đó, gồm course chính và add-on nếu có
- `therapist_id` — therapist được gán nếu có

Ghi chú: `person_index` không được mô tả trực tiếp, nhưng cần để biểu diễn “mỗi người một slot riêng”. Nếu hệ thống không cần quản lý từng người riêng thì có thể bỏ, nhưng khi booking nhóm cần nhiều reservation thì nên giữ.

### 1.10. Reservation_Course
- `reservation_id` — reservation sử dụng dịch vụ
- `course_id` — course được chọn trong reservation
- `course_role` — vai trò của course trong reservation, ví dụ `main_course` hoặc `add_on`
---

## 2. Business Rules

### 2.1. Rule về cửa hàng
- Mỗi shop hoạt động độc lập.
- Danh sách dịch vụ, lịch làm việc và đội therapist là riêng theo từng shop.

### 2.2. Rule về dịch vụ
- Course có hai loại: course chính và add-on.
- Add-on chỉ được đặt kèm course chính, không được đặt riêng.
- Thời lượng course phải là bội số của 15 phút.
- Danh sách dịch vụ có thể thay đổi theo ngày.
- Một số combo course chính + add-on có thể không hợp lệ theo POS.

### 2.3. Rule về therapist
- Mỗi therapist thuộc một shop.
- Lịch làm việc của therapist được quản lý bằng các shift entry theo ngày và khung giờ.
- Tại một thời điểm, một therapist chỉ phục vụ một khách.
- Khách có thể chỉ định therapist theo tên hoặc theo giới tính.
- Hệ thống phải kiểm tra therapist có làm ca tại slot đã chọn không.
- Booking nhóm từ 2 người trở lên không được chỉ định therapist.

### 2.4. Rule về khách hàng
- Khách hàng được nhận dạng qua số điện thoại.
- Hệ thống dùng số điện thoại để tra khách là thành viên hay khách mới, rank và số lần ghé thăm.
- Nếu số điện thoại nằm trong NG list thì không được tạo booking.

### 2.5. Rule về slot
- Slot phụ thuộc vào shop, ngày, dịch vụ, thời lượng, số người và therapist nếu có chỉ định.
- Cùng một shop và cùng một ngày, dịch vụ 60 phút và 90 phút có thể có danh sách slot khác nhau.
- Slot có thể hết trong thời gian thực.
- Sau khi khách xác nhận, hệ thống vẫn phải xử lý trường hợp slot bị người khác đặt mất.

### 2.6. Rule về booking
- Booking phải có shop, ngày giờ bắt đầu, số người, danh sách dịch vụ, số điện thoại khách hàng và mã đặt chỗ từ POS sau khi tạo thành công.
- Booking 1 người có thể chỉ định therapist.
- Booking nhóm từ 2 người trở lên thực chất là nhiều reservation liên kết nhau.
- Với booking nhóm, mỗi người có một slot riêng nhưng cùng giờ và cùng dịch vụ.
- Sau khi tạo thành công, booking có thể được sửa hoặc hủy qua AI.

---

## 3. Relationship Entity

| Relationship | Cardinality |
|---|---|
| Shop — Course | 1 - N |
| Shop — Therapist | 1 - N |
| Shop — Therapist Shift Entry | 1 - N |
| Shop — Booking | 1 - N |
| Therapist — Therapist Shift Entry | 1 - N |
| Customer — Booking | 1 - N |
| Booking — Reservation | 1 - N |
| Reservation — Course | N - N ,thông qua Reservation Course|
| Reservation — Therapist | N - 1 |

---

## 4. Lifecycle / State

### 4.1. Luồng đặt booking

```text
┌──────────────────────────────────────────────┐
│ PHASE 1: THU THẬP THÔNG TIN BOOKING          │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────┐
│ Xác định cửa hàng    │
└──────────────────────┘
        │
        ▼
┌──────────────────────┐
│ Chọn ngày            │
└──────────────────────┘
        │
        ▼
┌──────────────────────┐
│ Chọn số người        │
└──────────────────────┘
        │
        ▼
┌──────────────────────┐
│ Chọn thời lượng      │
└──────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ Chọn course chính + add-on   │
└──────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ Load slot khả dụng           │
└──────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ Khách chọn giờ bắt đầu       │
└──────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│ Booking 1 người?                             │
└──────────────────────────────────────────────┘
        │
        ├── Có ─► Chọn hoặc bỏ qua therapist
        │
        └── Không ─► Không cho chỉ định therapist
        │
        ▼

┌──────────────────────────────────────────────┐
│ PHASE 2: KIỂM TRA KHÁCH HÀNG                 │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ Khách cung cấp số điện thoại │
└──────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│ Tra member / rank / visit count / NG list    │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│ Số điện thoại có nằm trong NG list không?    │
└──────────────────────────────────────────────┘
        │
        ├── Có ─► Từ chối tạo booking
        │             Đề nghị liên hệ cửa hàng trực tiếp
        │
        └── Không ─► Tiếp tục xác nhận booking
        │
        ▼

┌──────────────────────────────────────────────┐
│ PHASE 3: XÁC NHẬN VÀ TẠO BOOKING             │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│ Xác nhận toàn bộ thông tin                   │
│ - Shop                                       │
│ - Ngày, giờ                                  │
│ - Số người                                   │
│ - Course chính + add-on                      │
│ - Therapist nếu có                           │
│ - Số điện thoại                              │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ Khách xác nhận?              │
└──────────────────────────────┘
        │
        ├── Không ─► Chỉnh sửa thông tin
        │            Load lại slot nếu cần
        │
        └── Có ─► Gọi API tạo booking vào POS
        │
        ▼

┌──────────────────────────────────────────────┐
│ PHASE 4: XỬ LÝ KẾT QUẢ TỪ POS                │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ POS trả kết quả              │
└──────────────────────────────┘
        │
        ├── Success
        │      ▼
        │   Nhận mã đặt chỗ từ POS
        │      ▼
        │   Thông báo mã đặt chỗ cho khách
        │      ▼
        │   Booking Created
        │
        ├── Conflict
        │      ▼
        │   Slot vừa chọn đã bị đặt mất
        │      ▼
        │   Gợi ý giờ gần nhất còn trống
        │      ▼
        │   Khách chọn lại giờ
        │
        └── Failed
               ▼
            Lỗi POS hoặc lỗi nghiệp vụ
               ▼
            Thông báo lỗi phù hợp cho khách
```

### 4.2. Trạng thái booking

```text
┌──────────────┐
│    Draft     │
└──────────────┘
       │
       │ Khách xác nhận thông tin
       ▼
┌─────────────────────────┐
│ Confirmed_By_Customer   │
└─────────────────────────┘
       │
       ├── POS tạo thành công
       │       │
       │       ▼
       │   ┌────────────────┐
       │   │ Created_In_POS │
       │   └────────────────┘
       │       │
       │       ├── Sửa booking
       │       │       │
       │       │       ▼
       │       │   ┌──────────┐
       │       │   │ Modified │
       │       │   └──────────┘
       │       │       │
       │       │       ▼
       │       │   ┌────────────────┐
       │       │   │ Created_In_POS │
       │       │   └────────────────┘
       │       │
       │       └── Hủy booking
       │               │
       │               ▼
       │           ┌───────────┐
       │           │ Cancelled │
       │           └───────────┘
       │
       ├── Slot bị người khác đặt mất
       │       │
       │       ▼
       │   ┌──────────┐
       │   │ Conflict │
       │   └──────────┘
       │       │
       │       ▼
       │   Quay lại Draft để chọn slot khác
       │
       └── Lỗi POS hoặc lỗi nghiệp vụ
               │
               ▼
           ┌────────┐
           │ Failed │
           └────────┘
```


---

## 5. Permissions

### 5.1. Khách hàng
- Cung cấp thông tin đặt lịch qua cuộc gọi.
- Chọn shop, ngày, số người, thời lượng, dịch vụ, slot và therapist nếu hợp lệ.
- Xác nhận thông tin booking.
- Yêu cầu sửa hoặc hủy booking sau khi tạo thành công.

### 5.2. AI tiếp nhận
- Hỏi và thu thập thông tin đặt lịch theo đúng luồng.
- Tra cứu shop, course, slot, therapist và khách hàng thông qua hệ thống/POS.
- Kiểm tra rule nghiệp vụ trước khi tạo booking.
- Gọi API tạo booking vào POS sau khi khách xác nhận.
- Thông báo mã đặt chỗ hoặc thông báo lỗi phù hợp.
- Hỗ trợ sửa/hủy booking theo yêu cầu khách hàng.

### 5.3. Therapist
- Không trực tiếp tạo booking trong mô tả nghiệp vụ.
- Được hệ thống kiểm tra lịch làm việc và tình trạng trống lịch khi khách yêu cầu chỉ định.

### 5.4. Quản lý / Admin
- Quản lý hoặc theo dõi dữ liệu nghiệp vụ liên quan đến shop, course, therapist, lịch làm việc và booking.

Ghi chú: Mô tả nghiệp vụ chỉ nêu có nhóm Quản lý/Admin nhưng chưa mô tả chi tiết quyền thao tác.