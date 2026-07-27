# Thanh toán, giá và hóa đơn

## Giá dịch vụ

Giá hiện hành của từng dịch vụ phải lấy từ Booking API. Tài liệu knowledge base không phải nguồn xác nhận giá vì giá có thể được quản trị viên cập nhật. Khi khách hỏi giá, trợ lý nên hiển thị lựa chọn dịch vụ từ đúng cửa hàng.

Tổng giá dự kiến phụ thuộc dịch vụ chính, addon và số người. Nếu hệ thống chỉ trả giá từng dịch vụ, trợ lý không được tự thêm thuế, phí hoặc giảm giá chưa được xác nhận.

## Thanh toán

Phương thức thanh toán thực tế phụ thuộc từng cửa hàng và cấu hình vận hành. Nếu API không cung cấp thông tin, trợ lý cần nói rõ chưa có dữ liệu và khuyên khách liên hệ cửa hàng, không tự khẳng định chấp nhận một loại thẻ hay ví điện tử cụ thể.

## Khuyến mãi và thành viên

Chương trình thành viên, voucher, mã giảm giá và điều kiện áp dụng có thể thay đổi. Chỉ xác nhận ưu đãi khi có nguồn dữ liệu hiện hành. Không cộng dồn ưu đãi nếu hệ thống không nêu rõ.

## Hóa đơn và biên nhận

Khách cần hóa đơn nên thông báo với cửa hàng và cung cấp thông tin theo quy định áp dụng. Chatbot có thể hướng dẫn nhưng không tự tạo chứng từ tài chính khi chưa có API hỗ trợ.

## Hoàn tiền

Không hứa hoàn tiền hoặc thời hạn hoàn tiền nếu chưa có chính sách được phê duyệt và dữ liệu giao dịch. Hủy booking và hoàn tiền là hai vấn đề khác nhau: booking chuyển sang trạng thái `cancelled` không tự động chứng minh một khoản tiền đã được hoàn.
