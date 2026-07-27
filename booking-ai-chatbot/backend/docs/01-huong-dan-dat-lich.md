# Hướng dẫn đặt lịch

## Thông tin cần có

Để tạo booking, khách lần lượt chọn cửa hàng, dịch vụ chính, dịch vụ bổ sung nếu có, số người, ngày, giờ còn trống và cung cấp thông tin liên hệ. Hệ thống có thể yêu cầu họ tên và số điện thoại để nhận diện booking.

Danh sách cửa hàng, dịch vụ, giá và slot trống là dữ liệu động. Trợ lý phải lấy trực tiếp từ Booking API tại thời điểm khách thao tác, không suy đoán từ tài liệu kiến thức.

## Quy trình tiêu chuẩn

1. Chọn cửa hàng đang hoạt động.
2. Chọn một dịch vụ chính.
3. Chọn không, một hoặc nhiều dịch vụ bổ sung theo các lựa chọn hệ thống cung cấp.
4. Chọn số lượng khách.
5. Chọn ngày hợp lệ, không nằm trong quá khứ.
6. Chọn khung giờ còn đủ năng lực phục vụ cho toàn bộ nhóm.
7. Nhập thông tin khách hàng được yêu cầu.
8. Kiểm tra bản tóm tắt gồm cửa hàng, dịch vụ, ngày giờ, số người và thông tin liên hệ.
9. Xác nhận lần cuối để hệ thống tạo booking.

Booking chưa được tạo chỉ vì khách đã nhập đủ thông tin. Nó chỉ được gửi sang hệ thống đặt lịch sau thao tác xác nhận cuối cùng.

## Chọn thời gian

Khung giờ hiển thị phụ thuộc vào thời lượng dịch vụ, dịch vụ bổ sung, số người, lịch làm việc của therapist, khoảng nghỉ giữa khách và các booking đã tồn tại. Vì vậy một giờ có thể còn trống cho một người nhưng không đủ cho nhóm nhiều người.

Khách không thể đặt vào thời điểm đã qua. Nếu giờ khách chọn vừa hết chỗ trong lúc thao tác, hệ thống sẽ báo xung đột và khách cần chọn slot mới.

## Đặt cho nhóm

Với booking nhiều người, hệ thống kiểm tra đủ therapist phục vụ song song. Thời lượng booking nhóm được tính theo lộ trình phục vụ của nhóm, không đơn giản nhân thời lượng một người với số người. Mỗi người có reservation riêng nằm trong cùng booking.

## Khi đặt không thành công

Các nguyên nhân thường gặp gồm slot vừa được người khác giữ, cửa hàng hoặc dịch vụ ngừng hoạt động, không đủ therapist, thời gian quá sát hiện tại, số điện thoại bị hạn chế sử dụng, hoặc Booking API tạm thời không khả dụng. Trợ lý cần báo đúng lỗi và cho khách chọn lại, không tự thông báo rằng booking đã thành công.
