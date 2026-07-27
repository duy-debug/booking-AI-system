# Riêng tư và bảo mật thông tin

## Dữ liệu cần thiết

Hệ thống chỉ nên yêu cầu dữ liệu cần cho quy trình booking, chẳng hạn họ tên, số điện thoại và thông tin lựa chọn dịch vụ. Không yêu cầu khách gửi mật khẩu, mã OTP, số thẻ đầy đủ, mã bảo mật thẻ hoặc khóa API trong hội thoại.

## Xác minh booking

Tra cứu, đổi và hủy booking phải có bước xác minh quyền sở hữu bằng thông tin mà backend quy định. Biết mã booking đơn thuần không có nghĩa là được phép xem hoặc sửa mọi dữ liệu.

## Hiển thị thông tin

Trợ lý chỉ sử dụng contract public và không tiết lộ trường nội bộ như mã POS, trạng thái đồng bộ nội bộ, dữ liệu quản trị hoặc thông tin khách khác. Khi hiển thị số điện thoại hay dữ liệu nhạy cảm, giao diện nên hạn chế mức chi tiết nếu không cần thiết.

## Lịch sử hội thoại

Conversation ID dùng để nối tiếp workflow, không phải bằng chứng danh tính. Trạng thái hội thoại có thời hạn và có thể hết hạn. Khi người dùng bấm tạo cuộc trò chuyện mới, frontend tạo conversation ID mới; lịch sử cũ không nên được gắn nhầm vào workflow mới.

## Nội dung không nên gửi

Khách không nên gửi thông tin tài chính nhạy cảm, tài liệu nhận dạng không được yêu cầu hoặc hồ sơ y tế chi tiết qua chatbot. Với vấn đề cần trao đổi riêng, khách nên dùng kênh liên hệ chính thức của cửa hàng.

## Sự cố bảo mật

Nếu khách vô tình gửi bí mật hoặc credential, trợ lý nên khuyên thu hồi hoặc thay đổi credential đó. Không lặp lại toàn bộ secret trong câu trả lời hay log.
