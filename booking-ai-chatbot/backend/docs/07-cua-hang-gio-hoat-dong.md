# Cửa hàng và giờ hoạt động

## Tra cứu cửa hàng

Danh sách chi nhánh đang hoạt động, tên, địa chỉ và số điện thoại là dữ liệu động từ Booking API. Trợ lý phải dùng công cụ tra cứu cửa hàng thay vì dựa vào một danh sách tĩnh trong tài liệu.

Khách có thể hỏi theo thành phố, khu vực, tên chi nhánh hoặc nhu cầu dịch vụ. Nếu có nhiều kết quả, trợ lý nên đưa danh sách lựa chọn rõ ràng để khách chọn đúng `shop_id`.

## Giờ hoạt động

Giờ hoạt động có thể khác theo cửa hàng, ngày trong tuần, ngày lễ hoặc lịch bảo trì. Slot booking là nguồn đáng tin cậy để biết giờ có thể đặt, nhưng không nhất thiết đại diện cho toàn bộ giờ mở cửa. Nếu cần giờ mở cửa chính xác mà API chưa cung cấp, khách nên gọi số điện thoại của chi nhánh.

## Dịch vụ theo cửa hàng

Không phải dịch vụ nào cũng có tại mọi chi nhánh. Sau khi khách chọn cửa hàng, trợ lý chỉ hiển thị course đang hoạt động thuộc cửa hàng đó. Không chuyển `course_id` của cửa hàng này sang booking tại cửa hàng khác.

## Khả năng tiếp cận và tiện ích

Thông tin về bãi đỗ xe, thang máy, lối đi xe lăn, phòng tắm, tủ đồ, phòng riêng, phục vụ theo ngôn ngữ hoặc tiện ích khác cần được xác nhận theo từng chi nhánh. Nếu knowledge base hay API chưa có dữ liệu, trợ lý phải nói chưa thể xác nhận và cung cấp số liên hệ khi có.

## Múi giờ

Hệ thống Komorebi Tokyo vận hành lịch theo múi giờ kinh doanh `Asia/Tokyo`, trừ khi cấu hình triển khai nêu khác. Ngày và giờ booking cần được hiểu theo múi giờ của cửa hàng.
