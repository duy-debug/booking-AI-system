# Tra cứu, đổi lịch và hủy lịch

## Tra cứu booking

Khách có thể yêu cầu tra cứu bằng mã booking hoặc số điện thoại theo biểu mẫu hệ thống cung cấp. Thông tin xác minh phải khớp dữ liệu booking. Trợ lý không được hiển thị booking của người khác và không được bỏ qua bước xác minh quyền sở hữu.

Kết quả tra cứu có thể gồm mã booking, trạng thái, cửa hàng, ngày, giờ bắt đầu, giờ kết thúc, số người, dịch vụ và thông tin liên hệ phù hợp với contract công khai.

## Đổi lịch

Đổi lịch là thao tác thay đổi dữ liệu và luôn cần xác nhận cuối cùng. Quy trình chuẩn:

1. Xác định booking và xác minh quyền sở hữu.
2. Kiểm tra booking chưa bị hủy.
3. Khách nhập ngày hoặc giờ mới theo trường hệ thống cho phép.
4. Hệ thống kiểm tra slot mới theo thời lượng và số người hiện tại.
5. Hiển thị tóm tắt thay đổi.
6. Chỉ cập nhật sau khi khách xác nhận.

Nếu slot mới không còn khả dụng, booking cũ vẫn được giữ nguyên. Trợ lý không được nói rằng lịch đã đổi trước khi Booking API trả kết quả thành công.

## Hủy lịch

Hủy lịch cũng cần xác minh và xác nhận:

1. Xác định booking.
2. Xác minh thông tin khách.
3. Khách có thể cung cấp lý do hủy.
4. Hiển thị bản tóm tắt hủy.
5. Chỉ gửi yêu cầu hủy sau xác nhận cuối cùng.

Sau khi hủy thành công, trạng thái booking là `cancelled`. Booking đã hủy không thể tiếp tục đổi lịch bằng workflow thông thường. Nếu khách đổi ý, họ cần tạo booking mới tùy theo slot còn trống.

## An toàn thao tác

Các câu như “tôi đang cân nhắc hủy”, “nếu hủy thì sao” hoặc câu hỏi về chính sách không phải là xác nhận hủy. Trợ lý phải phân biệt yêu cầu tìm hiểu với lệnh thực hiện. Token xác nhận có thời hạn và gắn với đúng cuộc trò chuyện, đúng hành động đang chờ.
