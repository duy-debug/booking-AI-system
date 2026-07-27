# Xử lý sự cố thường gặp

## Booking bị trùng hoặc slot vừa hết

Khả dụng có thể thay đổi giữa lúc hiển thị và lúc xác nhận. Khi backend trả xung đột, khách cần chọn slot khác. Không tự gửi lại thao tác tạo nhiều lần vì có thể gây nhầm lẫn.

## Cuộc trò chuyện hết hạn

Trạng thái workflow được lưu có thời hạn. Nếu khách quay lại sau thời gian dài và lựa chọn cũ không còn hợp lệ, hãy bắt đầu lại workflow. Mã conversation không thay thế mã booking.

## Nhập sai số điện thoại

Trước khi xác nhận tạo booking, khách nên sửa trong biểu mẫu hoặc bắt đầu lại bước nhập thông tin. Sau khi booking đã tạo, việc chỉnh thông tin chỉ thực hiện nếu update contract hỗ trợ; nếu không, liên hệ cửa hàng.

## Không thấy booking

Kiểm tra:

- Mã booking có đầy đủ và đúng ký tự hay không.
- Số điện thoại có đúng số đã dùng khi đặt hay không.
- Booking có thuộc môi trường hoặc cửa hàng đang tra cứu hay không.

Không thử vét cạn mã booking và không bỏ qua bước xác minh.

## Dịch vụ hoặc cửa hàng biến mất

Một mục có thể đã chuyển sang không hoạt động. Booking hiện có vẫn cần được xử lý theo dữ liệu backend, nhưng mục không hoạt động không được dùng để tạo booking mới.

## Không kết nối được kho kiến thức

Lỗi knowledge base ảnh hưởng câu hỏi FAQ, không đồng nghĩa Booking API đã hỏng. Khách vẫn có thể thử các workflow booking nếu readiness của dependency liên quan cho phép.

## Không kết nối được Booking API

Không thể xác nhận shop, course, slot hoặc mutation. Trợ lý cần thông báo tạm thời gián đoạn và đề nghị thử lại, không tạo dữ liệu mẫu để thay thế.

## Yêu cầu bị giới hạn

Khi gửi quá nhiều request trong một khoảng ngắn, hệ thống có thể rate limit. Khách nên chờ rồi thử lại. Correlation ID trong response có thể dùng để đội kỹ thuật truy vết sự cố mà không cần khách cung cấp dữ liệu nhạy cảm.
