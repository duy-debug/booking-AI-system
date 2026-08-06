# Demo Knowledge Base

Tài liệu knowledge minh họa cho chatbot đặt lịch. Nội dung chỉ mang tính tham khảo; chính sách thực tế phải được cửa hàng xác nhận.

# Opening Hours

Trong dữ liệu demo, cửa hàng phục vụ từ 08:00 đến 22:00, thứ Hai đến thứ Bảy và nghỉ Chủ nhật. Giờ thực tế có thể thay đổi vào ngày lễ.

# Booking Availability

Slot hiển thị chỉ còn trống tại thời điểm kiểm tra và chỉ được giữ khi POS xác nhận booking thành công.

# Same-Day Booking

Có thể đặt trong ngày nếu còn slot phù hợp; khả năng phục vụ phụ thuộc chi nhánh, dịch vụ, số khách và nhân viên.

# Advance Booking

Nên đặt trước cho cuối tuần, nhóm, dịch vụ dài, giờ cao điểm hoặc yêu cầu therapist cụ thể.

# Group Booking

Luồng demo hỗ trợ 2–3 người cùng chi nhánh, ngày, giờ, dịch vụ và thời lượng. Không chỉ định therapist riêng cho từng người.

# Single Booking

Booking một người có thể bỏ qua therapist, yêu cầu therapist cụ thể hoặc ưu tiên giới tính nếu POS hỗ trợ.

# Therapist Request

Yêu cầu therapist phụ thuộc availability và không phải cam kết tuyệt đối.

# Therapist Gender Preference

Khách có thể ưu tiên therapist nam hoặc nữ; khả năng đáp ứng phụ thuộc lịch làm việc và dịch vụ.

# Services

Danh sách dịch vụ đang hoạt động được lấy từ POS theo chi nhánh đã chọn.

# Service Duration

Thời lượng do dịch vụ trong POS quy định; chatbot không tự thay đổi thời lượng không được hỗ trợ.

# Main Course

Main course là dịch vụ chính bắt buộc của booking và quyết định thời lượng, giá cùng availability.

# Add-On Services

Add-on là dịch vụ bổ sung. Khả năng kết hợp, tổng thời lượng và giá phải theo POS.

# Service Price

Giá có thể thay đổi theo chi nhánh, dịch vụ, thời lượng, add-on và ưu đãi; giá cuối cùng lấy từ POS.

# Promotions

Dữ liệu demo chưa có chính sách khuyến mãi chính thức; chatbot không tự cam kết mức giảm.

# Membership

Thông tin thành viên có thể được POS xác minh bằng số điện thoại; quyền lợi cụ thể chưa được định nghĩa.

# Customer Phone Number

Số điện thoại dùng để xác minh, liên kết booking và hỗ trợ liên hệ; không được ghi nguyên số vào log.

# Customer Name

Tên được hỏi khi POS chưa có hồ sơ khách; chatbot không suy đoán tên từ số điện thoại.

# Phone Verification

Khách phải xác nhận số điện thoại trước booking. Luồng demo không xác minh danh tính pháp lý hay OTP.

# Booking Confirmation

Chatbot tóm tắt dữ liệu để khách xác nhận; chỉ gọi POS create sau xác nhận cuối.

# Booking Success

Khi POS chấp nhận, chatbot thông báo đặt lịch thành công và hiển thị mã chính thức nếu contract trả về.

# Booking Code

Chỉ hiển thị user-facing booking code từ POS; không dùng booking UUID hoặc reservation UUID làm mã khách hàng.

# Booking Changes

Trước xác nhận cuối, khách có thể đổi dữ liệu; các trường phụ thuộc như slot phải được xóa và tải lại khi cần.

# Rescheduling

Reschedule booking đã tạo nằm ngoài create-booking MVP; khách cần liên hệ cửa hàng.

# Cancellation Policy

Chưa có mức phí hủy chính thức. Khách nên liên hệ cửa hàng về thời hạn, phí hủy muộn, no-show và hoàn tiền.

# Cancelling a Booking

Hủy booking đã tạo chưa thuộc MVP; chatbot không được báo hủy thành công khi POS chưa xác nhận.

# Late Arrival

Đến muộn có thể bị rút ngắn, đổi slot hoặc từ chối; khách nên gọi cửa hàng nếu dự kiến trễ.

# Arrival Time

Khách nên đến sớm khoảng 10 đến 15 phút để chuẩn bị; đây là hướng dẫn tham khảo.

# Check-In

Khi check-in, khách có thể cung cấp tên, số điện thoại, thời gian, chi nhánh và số người.

# Walk-In Customers

Cửa hàng có thể nhận walk-in nếu còn chỗ nhưng chatbot không bảo đảm khả năng phục vụ.

# Waiting Time

Giờ bắt đầu có thể chậm do khách trước, dịch vụ kéo dài, thiếu nhân viên hoặc sự cố vận hành.

# Pregnancy Policy

Khách mang thai cần báo cửa hàng và tham khảo ý kiến chuyên môn. Chatbot không xác nhận dịch vụ an toàn cho từng trường hợp.

# Health Conditions

Khách cần báo tình trạng sức khỏe đặc biệt; chatbot không chẩn đoán hoặc đưa chỉ định điều trị.

# Allergies

Khách cần báo dị ứng với tinh dầu, mỹ phẩm, thảo dược, latex hoặc hương liệu trước dịch vụ.

# Injuries

Khách bị chấn thương cần báo vị trí và mức khó chịu; cửa hàng có thể điều chỉnh hoặc từ chối vì an toàn.

# Infectious Conditions

Khách có sốt hoặc bệnh truyền nhiễm nên hoãn lịch; cửa hàng có thể từ chối để bảo vệ mọi người.

# Age Requirements

Chưa có tuổi tối thiểu chung; người dưới 18 tuổi có thể cần người giám hộ đồng ý hoặc đi cùng.

# Children at the Store

Chưa xác nhận khu vực trông trẻ; khách cần liên hệ trước nếu đưa trẻ đi cùng.

# Accessibility

Lối xe lăn, thang máy và hỗ trợ tiếp cận chưa được xác nhận; khách nên liên hệ chi nhánh.

# Parking

Thông tin bãi đậu xe, chỗ xe máy và chi phí chưa được xác nhận; khách cần hỏi trực tiếp cửa hàng.

# Public Transportation

Chưa có dữ liệu tuyến giao thông công cộng; khách nên dùng bản đồ hoặc liên hệ chi nhánh.

# Store Location

Địa chỉ chi nhánh lấy từ POS; chatbot không tự tạo địa chỉ.

# Contacting the Store

Nên liên hệ cửa hàng khi hủy/đổi lịch, nhóm trên 3 người, yêu cầu đặc biệt, đến trễ hoặc cần chính sách chính thức.

# Payment Methods

Phương thức thanh toán chưa được xác nhận đầy đủ; khách cần hỏi cửa hàng.

# Payment Timing

Create-booking MVP không xử lý thanh toán và không thu thập dữ liệu thẻ.

# Deposits

Dữ liệu demo chưa có quy định đặt cọc; chatbot không tự yêu cầu hoặc xác nhận tiền cọc.

# Refunds

Chưa có chính sách hoàn tiền chính thức; khách cần liên hệ cửa hàng.

# Gift Cards and Vouchers

Việc dùng voucher chưa được xác nhận và chatbot không tự xác thực nếu POS chưa hỗ trợ.

# Tips

Chưa có hướng dẫn chính thức về tiền tip; nếu có thì tùy chọn theo chính sách cửa hàng.

# Clothing and Preparation

Khách nên mặc thoải mái và hạn chế mang tài sản giá trị; vật dụng cung cấp phụ thuộc chi nhánh.

# Personal Belongings

Chưa xác nhận tủ khóa hoặc giữ đồ; khách nên liên hệ nếu mang hành lý hoặc đồ giá trị.

# Food and Alcohol

Nên tránh ăn quá no; cửa hàng có thể từ chối khách đã dùng nhiều rượu bia vì an toàn.

# Before the Service

Khách nên đến đúng giờ, báo sức khỏe, dị ứng, vùng cần tránh và mức lực mong muốn.

# During the Service

Khách nên báo ngay nếu đau, khó chịu hoặc muốn dừng; khách có quyền dừng dịch vụ.

# After the Service

Nên uống nước, nghỉ và đứng dậy từ từ; triệu chứng bất thường cần hỗ trợ chuyên môn.

# Hygiene

Tiêu chuẩn vệ sinh cụ thể của phòng, khăn, dụng cụ và bề mặt cần được cửa hàng xác nhận.

# Privacy

Chatbot chỉ thu thập dữ liệu cần cho booking; không yêu cầu mật khẩu, OTP, thẻ hoặc giấy tờ không cần thiết.

# Conversation Data

MVP lưu context trong bộ nhớ process nên có thể mất khi restart và không chia sẻ giữa nhiều instance.

# FAQ During Booking

FAQ không chuyển state, không xóa booking context và không gọi POS create.

# Knowledge Availability

FAQ retrieval cần Qdrant, collection, tài liệu đã index và embedding model hoạt động.

# FAQ Limitations

Khi tài liệu thiếu, cũ hoặc query mơ hồ, chatbot phải nói chưa đủ thông tin và hướng dẫn liên hệ cửa hàng.

# Emergency Situations

Chatbot không xử lý y tế khẩn cấp hoặc thay thế dịch vụ khẩn cấp.

# Complaints and Feedback

Quy trình khiếu nại chưa chính thức; chatbot không tự hứa hoàn tiền hay bồi thường.

# Lost and Found

Khách để quên đồ cần liên hệ chi nhánh sớm; chatbot không xác nhận vật đã được tìm thấy.

# Service Refusal

Cửa hàng có thể từ chối vì rủi ro an toàn, bệnh truyền nhiễm, hành vi không phù hợp hoặc yêu cầu ngoài phạm vi.

# Prohibited Conduct

Quấy rối, đe dọa, bạo lực hoặc yêu cầu không phù hợp có thể dẫn đến từ chối phục vụ.

# Holiday Schedule

Giờ ngày lễ có thể khác; khách nên kiểm tra availability hoặc liên hệ chi nhánh.

# Weather and Unexpected Closures

Thời tiết, mất điện, bảo trì hoặc thiếu nhân sự có thể làm thay đổi lịch hoạt động.

# Supported Languages

Chatbot ưu tiên tiếng Việt; hỗ trợ ngôn ngữ khác phụ thuộc model và knowledge được cấu hình.

# Chatbot Scope

MVP hỗ trợ create booking và FAQ; chưa hỗ trợ đầy đủ lookup, cancel, reschedule, payment, refund hay tư vấn y tế.

# When to Contact the Store

Hãy liên hệ cửa hàng khi chatbot không tìm thấy dịch vụ, không có slot, nhóm trên 3 người, cần thay đổi booking, hỏi giá, bãi xe, thanh toán, đến trễ hoặc cần hỗ trợ đặc biệt.
