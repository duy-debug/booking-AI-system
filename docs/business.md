
## Mô tả nghiệp vụ — Hệ thống đặt lịch massage りらくる

---

### Tổng quan

Hệ thống quản lý việc đặt lịch massage tại chuỗi cửa hàng りらくる. Khách hàng gọi điện → AI tiếp nhận → tạo booking vào hệ thống POS. Có ba nhóm đối tượng chính:  **Khách hàng** ,  **Therapist (nhân viên trị liệu)** , và  **Quản lý / Admin** .

---

### Cửa hàng (Shop)

Chuỗi có nhiều cửa hàng, mỗi cửa hàng có mã riêng, tên, địa chỉ, và số điện thoại. Mỗi cửa hàng hoạt động độc lập — danh sách dịch vụ, lịch làm việc, và đội therapist là riêng biệt theo từng cửa hàng.

---

### Dịch vụ / Course

Mỗi cửa hàng cung cấp một danh sách dịch vụ (course). Mỗi dịch vụ có tên, thời lượng (bội số 15 phút: 30, 45, 60, 90, 120...), và giá tiền. Dịch vụ chia làm hai loại:

* **Course chính** : ví dụ もみほぐし (massage toàn thân), ドライヘッドスパ (massage đầu khô)
* **Add-on (dịch vụ bổ sung)** : ví dụ 足つぼ (bấm huyệt chân), プレミアムマットレス (nệm cao cấp) — chỉ được đặt kèm course chính, không đứng một mình

Danh sách dịch vụ có thể thay đổi theo ngày (cửa hàng nghỉ, thiếu nhân viên → một số dịch vụ không khả dụng).

---

### Therapist (Nhân viên trị liệu)

Mỗi therapist thuộc một cửa hàng, có tên, giới tính (nam/nữ), và lịch làm việc theo ca. Tại mỗi thời điểm, một therapist chỉ có thể phục vụ một khách. Khách hàng có thể yêu cầu chỉ định therapist theo tên hoặc theo giới tính — hệ thống cần kiểm tra therapist đó có làm ca tại slot đã chọn không.

Ràng buộc: **Booking nhóm từ 2 người trở lên không được chỉ định therapist.**

---

### Khách hàng

Khách được nhận dạng qua số điện thoại. Hệ thống tra cứu số điện thoại để biết khách là thành viên hay khách mới, hạng thành viên (rank), số lần ghé thăm. Một số số điện thoại nằm trong danh sách cấm (NG list) — không được phép tạo booking.

---

### Slot thời gian

Mỗi cửa hàng, mỗi ngày có một tập hợp các khung giờ bắt đầu khả dụng. Slot phụ thuộc vào: cửa hàng, ngày, dịch vụ được chọn (vì thời lượng khác nhau chiếm dụng lịch khác nhau), số người đặt, và therapist (nếu chỉ định). Cùng một cửa hàng cùng ngày nhưng chọn dịch vụ 60 phút vs 90 phút sẽ có danh sách slot khác nhau.

Slot có thể hết trong thời gian thực — sau khi khách confirm xong vẫn có thể bị người khác đặt mất (race condition), cần xử lý conflict.

---

### Booking (Đặt chỗ)

Một booking bao gồm:

* Cửa hàng
* Ngày và giờ bắt đầu
* Số người
* Danh sách dịch vụ (course chính + add-on nếu có), mỗi người một bộ dịch vụ
* Therapist được chỉ định (nếu có (có thể chỉ định giới tính hoặc tên cụ thể của therapist), chỉ cho booking 1 người)
* Số điện thoại khách hàng
* Mã đặt chỗ (do POS cấp sau khi tạo thành công)

Một booking nhóm (2+ người) thực chất là nhiều reservation liên kết nhau, mỗi người một slot riêng nhưng cùng giờ và cùng dịch vụ.

Sau khi tạo thành công, booking **có thể hủy hay sửa qua hệ thống AI**.

---

### Luồng nghiệp vụ khi đặt chỗ (theo thứ tự)

1. Xác định cửa hàng
2. Chọn ngày
3. Chọn số người (1 hoặc nhóm)
4. Chọn thời lượng (phút)
5. Chọn loại dịch vụ (course chính, tùy chọn thêm add-on)
6. Hệ thống load danh sách slot khả dụng dựa trên các thông tin trên
7. Khách chọn giờ bắt đầu
8. Chọn hoặc bỏ qua chỉ định therapist (chỉ với booking 1 người)
9. Khách cung cấp số điện thoại → hệ thống tra hạng thành viên và kiểm tra NG list
10. Xác nhận toàn bộ thông tin
11. Gọi API tạo booking → nhận mã đặt chỗ
12. Thông báo mã đặt chỗ cho khách

---

### Các trường hợp đặc biệt cần xử lý

* **Ngày không có dịch vụ** : cửa hàng nghỉ hoặc không có nhân viên → hỏi khách chọn ngày khác
* **Ngày không có slot trống** : tất cả giờ đã đầy → hỏi khách chọn ngày khác
* **Giờ vừa chọn bị hết (conflict)** : sau khi khách confirm, slot bị người khác chiếm → gợi ý giờ gần nhất còn trống
* **Combo dịch vụ không hợp lệ** : một số tổ hợp course+addon POS không cho phép → phải hỏi khách chọn lại
* **Therapist không làm ca đó** : báo khách, hỏi muốn đổi giờ hoặc bỏ chỉ định
* **Số điện thoại trong NG list** : từ chối tạo booking, đề nghị liên hệ cửa hàng trực tiếp
* **Lỗi hệ thống POS (5xx)** : thông báo lỗi tạm thời, đề nghị gọi lại

