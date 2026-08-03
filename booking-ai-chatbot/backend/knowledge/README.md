# Demo Knowledge Base

Tài liệu này là cơ sở tri thức minh họa cho môi trường phát triển và kiểm thử chatbot đặt lịch.

Thông tin trong tài liệu không phải chính sách vận hành chính thức. Trước khi triển khai thực tế, cửa hàng cần xác nhận lại giờ mở cửa, dịch vụ, giá, quy định hủy lịch, chính sách thanh toán và các hướng dẫn an toàn.

Chatbot chỉ cung cấp thông tin tham khảo và không thay thế tư vấn y tế hoặc xác nhận trực tiếp từ cửa hàng.

---

# Opening Hours

Trong dữ liệu demo, cửa hàng phục vụ từ 08:00 đến 22:00, từ thứ Hai đến thứ Bảy.

Cửa hàng không phục vụ vào Chủ nhật trong dữ liệu demo.

Giờ hoạt động thực tế có thể thay đổi vào ngày lễ, ngày bảo trì hoặc các sự kiện đặc biệt.

Giờ nhận khách cuối phụ thuộc vào:

- thời lượng dịch vụ;
- thời gian chuẩn bị;
- số lượng nhân viên đang làm việc;
- khung giờ còn trống;
- giờ đóng cửa của chi nhánh.

Ví dụ, một dịch vụ kéo dài 90 phút có thể không được nhận vào lúc 21:30 nếu cửa hàng đóng cửa lúc 22:00.

Khách hàng nên kiểm tra khung giờ còn trống trực tiếp trên chatbot hoặc liên hệ cửa hàng.

---

# Booking Availability

Khung giờ được chatbot hiển thị chỉ là những khung giờ còn trống tại thời điểm kiểm tra.

Tình trạng còn chỗ có thể thay đổi nếu khách hàng khác hoàn tất đặt lịch trước.

Một khung giờ chỉ được giữ sau khi hệ thống xác nhận đặt lịch thành công.

Việc lựa chọn một khung giờ trong cuộc trò chuyện chưa có nghĩa là khung giờ đó đã được giữ.

Trước khi tạo booking, hệ thống có thể kiểm tra lại availability lần cuối.

Nếu khung giờ đã hết chỗ, chatbot sẽ yêu cầu khách chọn thời gian khác.

---

# Same-Day Booking

Khách hàng có thể đặt lịch trong ngày nếu vẫn còn khung giờ phù hợp.

Khả năng nhận lịch trong ngày phụ thuộc vào:

- chi nhánh;
- dịch vụ;
- thời lượng;
- số lượng khách;
- nhân viên còn trống;
- thời gian chuẩn bị cần thiết.

Chatbot không đảm bảo rằng mọi yêu cầu đặt lịch trong ngày đều được chấp nhận.

---

# Advance Booking

Khách hàng nên đặt lịch trước, đặc biệt trong các trường hợp:

- đặt vào cuối tuần;
- đi theo nhóm;
- yêu cầu therapist cụ thể;
- chọn dịch vụ có thời lượng dài;
- đặt vào giờ cao điểm;
- cần nhiều khách bắt đầu cùng một thời điểm.

Dữ liệu demo chưa quy định số ngày tối đa được phép đặt trước.

---

# Group Booking

Chatbot hỗ trợ đặt lịch cho nhóm từ 2 đến 3 người trong luồng booking demo.

Các thành viên trong nhóm sử dụng:

- cùng chi nhánh;
- cùng ngày;
- cùng thời gian bắt đầu;
- cùng dịch vụ chính;
- cùng thời lượng booking.

Group booking được gửi tới hệ thống POS dưới dạng một booking cha với nhiều reservation con.

Mỗi người trong nhóm có thể được hệ thống POS phân công nhân viên phù hợp.

Chatbot không cho phép chỉ định therapist cá nhân cho từng người trong group booking demo.

Đối với nhóm trên 3 người, khách hàng nên liên hệ trực tiếp cửa hàng để được hỗ trợ.

---

# Single Booking

Booking cho một người có thể cho phép khách lựa chọn yêu cầu therapist.

Khách có thể:

- không yêu cầu therapist;
- yêu cầu therapist cụ thể nếu hệ thống hỗ trợ;
- yêu cầu therapist theo giới tính nếu cửa hàng có chính sách này.

Việc gửi yêu cầu therapist không luôn đảm bảo therapist đó có thể phục vụ.

Kết quả cuối cùng phụ thuộc availability và phản hồi từ hệ thống POS.

---

# Therapist Request

Khách hàng có thể bỏ qua bước lựa chọn therapist nếu không có yêu cầu đặc biệt.

Nếu khách yêu cầu therapist cụ thể nhưng therapist không còn trống, cửa hàng có thể:

- đề xuất therapist khác;
- đề xuất khung giờ khác;
- liên hệ lại với khách;
- từ chối yêu cầu nếu không thể đáp ứng.

Dữ liệu demo không bảo đảm mọi chi nhánh đều hỗ trợ tìm therapist theo tên.

---

# Therapist Gender Preference

Trong dữ liệu demo, khách có thể yêu cầu therapist nam hoặc nữ khi đặt lịch cho một người.

Đây là yêu cầu ưu tiên, không phải cam kết tuyệt đối.

Khả năng đáp ứng phụ thuộc:

- nhân viên đang làm việc;
- lịch trống;
- dịch vụ đã chọn;
- chính sách của chi nhánh.

Nếu không thể đáp ứng, cửa hàng có thể đề xuất lựa chọn khác.

---

# Services

Danh sách dịch vụ được lấy từ hệ thống POS theo chi nhánh đã chọn.

Mỗi chi nhánh có thể cung cấp danh sách dịch vụ khác nhau.

Một dịch vụ có thể bao gồm:

- tên dịch vụ;
- thời lượng;
- giá tham khảo;
- loại dịch vụ;
- trạng thái đang hoạt động hoặc tạm ngừng.

Chatbot chỉ hiển thị các dịch vụ đang được hệ thống POS cho phép đặt.

---

# Service Duration

Thời lượng dịch vụ được tính bằng phút.

Các thời lượng thường gặp trong dữ liệu demo có thể gồm:

- 30 phút;
- 45 phút;
- 60 phút;
- 90 phút;
- 120 phút.

Không phải dịch vụ nào cũng hỗ trợ tất cả thời lượng.

Thời lượng thực tế được xác định dựa trên course hoặc dịch vụ được chọn trong hệ thống POS.

Chatbot không tự thay đổi thời lượng của một dịch vụ nếu POS không hỗ trợ.

---

# Main Course

Main course là dịch vụ chính của booking.

Mỗi booking phải có ít nhất một main course hợp lệ.

Main course quyết định phần lớn:

- nội dung dịch vụ;
- thời lượng;
- giá;
- yêu cầu therapist;
- khả năng còn chỗ.

Chatbot không được tạo booking nếu chưa xác định được main course.

---

# Add-On Services

Add-on là dịch vụ bổ sung đi kèm main course.

Không phải main course nào cũng hỗ trợ add-on.

Add-on có thể làm thay đổi:

- tổng thời lượng;
- tổng giá;
- giờ kết thúc;
- availability;
- yêu cầu chuẩn bị.

Dữ liệu demo chưa cung cấp đầy đủ danh sách add-on và quy tắc kết hợp dịch vụ.

Khách hàng nên xác nhận trực tiếp với cửa hàng nếu cần add-on cụ thể.

---

# Service Price

Giá dịch vụ được lấy từ hệ thống POS hoặc dữ liệu cấu hình của cửa hàng.

Giá có thể thay đổi theo:

- chi nhánh;
- dịch vụ;
- thời lượng;
- add-on;
- chương trình khuyến mãi;
- ngày hoặc khung giờ;
- hạng thành viên.

Giá trong tài liệu demo chỉ mang tính minh họa.

Giá cuối cùng cần được xác nhận từ hệ thống POS hoặc nhân viên cửa hàng.

---

# Promotions

Dữ liệu demo chưa có chính sách khuyến mãi chính thức.

Khuyến mãi có thể có các điều kiện như:

- chỉ áp dụng tại một số chi nhánh;
- chỉ áp dụng trong thời gian nhất định;
- chỉ dành cho thành viên;
- không áp dụng cùng ưu đãi khác;
- yêu cầu mã khuyến mãi;
- không áp dụng cho group booking.

Chatbot không nên tự cam kết mức giảm giá khi chưa nhận được thông tin từ POS hoặc cửa hàng.

---

# Membership

Một số cửa hàng có thể áp dụng chương trình thành viên hoặc xếp hạng khách hàng.

Thông tin thành viên có thể được xác minh dựa trên số điện thoại.

Quyền lợi thành viên có thể gồm:

- ưu đãi giá;
- tích điểm;
- quà sinh nhật;
- ưu tiên đặt lịch;
- dịch vụ đặc biệt.

Dữ liệu demo chưa định nghĩa hạng thành viên hoặc quyền lợi cụ thể.

---

# Customer Phone Number

Số điện thoại được sử dụng để:

- xác minh khách hàng;
- liên kết booking với hồ sơ khách;
- hỗ trợ cửa hàng liên hệ khi cần;
- tra cứu thông tin thành viên nếu POS hỗ trợ.

Khách hàng cần xác nhận số điện thoại trước khi hoàn tất booking.

Nếu số điện thoại chưa đúng, khách có thể từ chối xác nhận và nhập lại.

Chatbot không nên hiển thị toàn bộ số điện thoại trong log hoặc thông báo không cần thiết.

---

# Customer Name

Tên khách hàng có thể được thu thập cùng số điện thoại.

Trong dữ liệu demo, tên có thể là thông tin tùy chọn tùy theo POS contract.

Khách hàng nên cung cấp tên dễ nhận biết để cửa hàng hỗ trợ khi đến.

Chatbot không nên suy đoán tên từ số điện thoại hoặc conversation ID.

---

# Phone Verification

Việc xác minh số điện thoại không có nghĩa là xác thực danh tính pháp lý.

Mục đích chính là kiểm tra và liên kết thông tin khách hàng trong hệ thống POS.

Nếu số điện thoại không hợp lệ hoặc không thể xác minh, chatbot có thể yêu cầu khách nhập lại.

Dữ liệu demo chưa hỗ trợ xác minh bằng mã OTP.

---

# Booking Confirmation

Trước khi tạo booking, chatbot sẽ hiển thị hoặc tóm tắt thông tin đã chọn để khách xác nhận.

Thông tin có thể gồm:

- chi nhánh;
- ngày;
- giờ;
- số người;
- dịch vụ;
- thời lượng;
- yêu cầu therapist;
- số điện thoại.

Booking chỉ được gửi sang POS sau khi khách xác nhận cuối cùng.

Nếu khách từ chối xác nhận, hệ thống không được gọi API tạo booking.

---

# Booking Success

Khi hệ thống POS chấp nhận booking, chatbot trả thông báo:

“Đặt lịch thành công. Thông tin đặt lịch đã được ghi nhận.”

POS contract hiện tại trong dữ liệu demo không cung cấp mã đặt lịch dành cho người dùng.

Chatbot không sử dụng booking UUID hoặc reservation UUID làm mã đặt lịch.

Khách hàng có thể cần cung cấp số điện thoại khi liên hệ cửa hàng về booking.

---

# Booking Code

Dữ liệu POS demo hiện không có user-facing booking code.

Các trường `booking_id` và `reservation_id` là identifier nội bộ của hệ thống.

Chatbot không hiển thị các UUID này như mã xác nhận cho khách hàng.

Nếu hệ thống POS tương lai bổ sung mã đặt lịch chính thức, chatbot có thể hiển thị mã đó sau khi contract được xác nhận.

---

# Booking Changes

Khách hàng có thể yêu cầu thay đổi thông tin trước bước xác nhận cuối cùng.

Các thông tin có thể cần chọn lại gồm:

- chi nhánh;
- ngày;
- số người;
- thời lượng;
- dịch vụ;
- giờ;
- therapist;
- số điện thoại.

Khi thay đổi một thông tin ở bước trước, một số thông tin phụ thuộc có thể bị xóa.

Ví dụ:

- đổi ngày có thể làm mất giờ đã chọn;
- đổi dịch vụ có thể yêu cầu tải lại availability;
- đổi số người có thể thay đổi therapist policy;
- đổi chi nhánh có thể làm thay đổi danh sách dịch vụ.

---

# Rescheduling

Luồng reschedule booking đã tồn tại ở mức application trong một số thiết kế, nhưng không thuộc phạm vi create-booking MVP hiện tại.

Khách hàng muốn đổi lịch sau khi booking đã được tạo nên liên hệ trực tiếp cửa hàng cho đến khi tính năng reschedule production được kích hoạt.

Chatbot không nên cam kết đã đổi lịch nếu chưa nhận được xác nhận từ POS.

---

# Cancellation Policy

Khách hàng nên đổi hoặc hủy lịch sớm nếu không thể đến.

Mức phí hủy hoặc vắng mặt chưa có chính sách chính thức trong dữ liệu demo.

Khách hàng nên liên hệ trực tiếp cửa hàng để xác nhận:

- thời hạn hủy miễn phí;
- phí hủy muộn;
- phí không đến;
- chính sách hoàn tiền;
- quy định đối với booking nhóm.

Chatbot không tự tính phí hủy khi chưa có contract chính thức.

---

# Cancelling a Booking

Tính năng hủy booking sau khi đã tạo chưa thuộc phạm vi create-booking MVP hiện tại.

Nếu khách muốn hủy booking đã hoàn tất, chatbot nên hướng dẫn khách liên hệ cửa hàng.

Không được thông báo “đã hủy thành công” nếu chưa gọi và nhận xác nhận từ POS.

---

# Late Arrival

Khách hàng nên đến đúng giờ để sử dụng đầy đủ thời lượng dịch vụ.

Nếu đến muộn, cửa hàng có thể:

- rút ngắn thời lượng;
- chuyển sang khung giờ khác;
- thay đổi therapist;
- từ chối phục vụ nếu ảnh hưởng lịch tiếp theo.

Dữ liệu demo chưa có quy định cụ thể về số phút được phép đến muộn.

Khách hàng nên gọi cho cửa hàng nếu dự kiến đến trễ.

---

# Arrival Time

Khách hàng nên đến trước giờ hẹn để thực hiện các bước chuẩn bị.

Thời gian đến sớm đề xuất trong dữ liệu demo là khoảng 10 đến 15 phút.

Đây chỉ là hướng dẫn tham khảo, không phải chính sách chính thức.

Khách lần đầu có thể cần thêm thời gian để cung cấp thông tin hoặc trao đổi yêu cầu dịch vụ.

---

# Check-In

Khi đến cửa hàng, khách có thể cần cung cấp:

- tên;
- số điện thoại;
- thời gian booking;
- chi nhánh;
- số người.

Do POS demo không có mã booking dành cho khách, số điện thoại có thể được dùng để hỗ trợ tìm booking.

Quy trình check-in thực tế phụ thuộc vào cửa hàng.

---

# Walk-In Customers

Cửa hàng có thể nhận khách không đặt trước nếu vẫn còn nhân viên và khung giờ trống.

Chatbot không thể bảo đảm walk-in sẽ được phục vụ.

Khách hàng nên đặt lịch trước để giảm thời gian chờ.

---

# Waiting Time

Thời gian bắt đầu dịch vụ có thể chậm hơn dự kiến trong trường hợp:

- khách trước đến muộn;
- dịch vụ trước kéo dài;
- thiếu nhân viên;
- cửa hàng cần thêm thời gian chuẩn bị;
- có sự cố vận hành.

Dữ liệu demo không có cam kết thời gian chờ tối đa.

---

# Pregnancy Policy

Khách đang mang thai cần thông báo cho cửa hàng trước khi sử dụng dịch vụ.

Khách nên tham khảo ý kiến chuyên môn phù hợp trước khi đặt dịch vụ.

Chatbot không tự xác nhận một dịch vụ an toàn cho từng trường hợp cụ thể.

Một số dịch vụ, kỹ thuật, tư thế hoặc sản phẩm có thể không phù hợp trong thai kỳ.

Cửa hàng có quyền yêu cầu thêm thông tin hoặc từ chối dịch vụ nếu không thể bảo đảm an toàn.

---

# Health Conditions

Khách hàng nên thông báo cho cửa hàng nếu có:

- bệnh tim mạch;
- huyết áp bất thường;
- chấn thương;
- phẫu thuật gần đây;
- bệnh ngoài da;
- dị ứng;
- đau cấp tính;
- bệnh truyền nhiễm;
- tình trạng sức khỏe đặc biệt khác.

Chatbot không chẩn đoán và không đưa ra chỉ định điều trị.

Nhân viên cửa hàng có thể yêu cầu khách tham khảo ý kiến bác sĩ trước khi sử dụng dịch vụ.

---

# Allergies

Khách hàng nên thông báo trước nếu dị ứng với:

- tinh dầu;
- dầu massage;
- mỹ phẩm;
- thảo dược;
- latex;
- hương liệu;
- sản phẩm chăm sóc da.

Dữ liệu demo chưa có danh sách thành phần sản phẩm cụ thể.

Chatbot không được khẳng định một sản phẩm hoàn toàn không gây dị ứng.

---

# Injuries

Khách đang bị chấn thương nên thông báo rõ vị trí và mức độ khó chịu trước khi sử dụng dịch vụ.

Nhân viên có thể:

- điều chỉnh kỹ thuật;
- tránh vùng bị thương;
- đề xuất dịch vụ khác;
- yêu cầu xác nhận y tế;
- từ chối phục vụ nếu có rủi ro.

Chatbot không đánh giá mức độ nghiêm trọng của chấn thương.

---

# Infectious Conditions

Khách có triệu chứng sốt, bệnh truyền nhiễm hoặc tình trạng có thể ảnh hưởng đến người khác nên hoãn lịch.

Cửa hàng có thể từ chối phục vụ để bảo vệ khách hàng và nhân viên.

Chính sách cụ thể cần được cửa hàng xác nhận.

---

# Age Requirements

Dữ liệu demo chưa xác định độ tuổi tối thiểu cho tất cả dịch vụ.

Khách dưới 18 tuổi có thể cần:

- sự đồng ý của phụ huynh hoặc người giám hộ;
- người giám hộ đi cùng;
- giới hạn đối với một số dịch vụ.

Khách hàng nên liên hệ cửa hàng trước khi đặt cho người chưa thành niên.

---

# Children at the Store

Dữ liệu demo chưa xác nhận cửa hàng có khu vực trông trẻ.

Khách hàng không nên giả định rằng trẻ em có thể ở lại cửa hàng mà không có người giám sát.

Khách nên liên hệ cửa hàng trước nếu cần đưa trẻ đi cùng.

---

# Accessibility

Thông tin về lối đi dành cho xe lăn, thang máy hoặc phòng dịch vụ hỗ trợ tiếp cận chưa được xác nhận.

Khách có nhu cầu hỗ trợ nên liên hệ chi nhánh trước khi đến.

Chatbot không nên khẳng định cơ sở vật chất hỗ trợ tiếp cận khi chưa có dữ liệu chính thức.

---

# Parking

Thông tin chỗ đậu xe chưa được xác nhận trong dữ liệu demo.

Khách hàng nên liên hệ trực tiếp cửa hàng để kiểm tra:

- có bãi đậu ô tô hay không;
- có chỗ gửi xe máy hay không;
- chi phí gửi xe;
- thời gian hoạt động của bãi xe;
- lối vào phù hợp.

Chatbot không cam kết có chỗ đậu xe.

---

# Public Transportation

Dữ liệu demo chưa có thông tin về tuyến xe buýt, ga tàu hoặc điểm đón gần cửa hàng.

Khách hàng nên sử dụng ứng dụng bản đồ hoặc liên hệ chi nhánh để được hướng dẫn.

---

# Store Location

Địa chỉ chi nhánh được lấy từ hệ thống POS khi khách chọn cửa hàng.

Khách hàng nên kiểm tra lại tên và địa chỉ chi nhánh trước khi xác nhận booking.

Chatbot không nên tự tạo địa chỉ không có trong dữ liệu POS.

---

# Contacting the Store

Khách hàng nên liên hệ trực tiếp cửa hàng trong các trường hợp:

- cần hủy booking đã tạo;
- muốn reschedule;
- đi nhóm trên 3 người;
- cần therapist cụ thể;
- có tình trạng sức khỏe đặc biệt;
- cần hỗ trợ tiếp cận;
- cần xác nhận bãi đậu xe;
- cần hỏi về phí hoặc khuyến mãi;
- dự kiến đến trễ;
- không nhận được hỗ trợ từ chatbot.

Số điện thoại chính thức của từng chi nhánh phải được lấy từ POS hoặc dữ liệu đã xác nhận.

---

# Payment Methods

Dữ liệu demo chưa xác nhận đầy đủ phương thức thanh toán.

Cửa hàng có thể hỗ trợ một hoặc nhiều hình thức:

- tiền mặt;
- thẻ ngân hàng;
- chuyển khoản;
- ví điện tử;
- voucher;
- điểm thành viên.

Khách hàng nên xác nhận với cửa hàng trước khi đến.

Chatbot không tự khẳng định một phương thức thanh toán được chấp nhận khi chưa có dữ liệu chính thức.

---

# Payment Timing

Dữ liệu demo chưa xác định khách phải thanh toán:

- khi đặt lịch;
- khi đến cửa hàng;
- sau khi hoàn tất dịch vụ;
- hoặc đặt cọc trước.

Create-booking MVP hiện không xử lý thanh toán.

Chatbot không thu thập thông tin thẻ hoặc dữ liệu thanh toán nhạy cảm.

---

# Deposits

Dữ liệu demo chưa có quy định đặt cọc.

Một số booking nhóm, dịch vụ dài hoặc khung giờ đặc biệt có thể yêu cầu đặt cọc trong hệ thống thực tế.

Chatbot không tự yêu cầu hoặc xác nhận đã nhận đặt cọc khi chưa tích hợp payment contract.

---

# Refunds

Dữ liệu demo chưa có chính sách hoàn tiền.

Điều kiện hoàn tiền có thể phụ thuộc vào:

- phương thức thanh toán;
- thời điểm hủy;
- loại dịch vụ;
- voucher;
- chương trình khuyến mãi;
- quyết định của cửa hàng.

Khách hàng nên liên hệ trực tiếp cửa hàng.

---

# Gift Cards and Vouchers

Dữ liệu demo chưa xác nhận việc sử dụng gift card hoặc voucher.

Khách hàng nên kiểm tra:

- ngày hết hạn;
- chi nhánh áp dụng;
- dịch vụ áp dụng;
- khả năng sử dụng cùng khuyến mãi khác;
- phần giá trị còn lại;
- quy định hoàn tiền.

Chatbot không tự xác thực voucher nếu chưa có POS contract hỗ trợ.

---

# Tips

Dữ liệu demo chưa có hướng dẫn chính thức về tiền tip.

Tiền tip, nếu có, là tùy chọn và phụ thuộc chính sách của cửa hàng.

---

# Clothing and Preparation

Khách hàng nên mặc trang phục thoải mái.

Tùy dịch vụ, cửa hàng có thể cung cấp:

- khăn;
- áo choàng;
- dép;
- tủ đồ;
- vật dụng dùng một lần.

Thông tin cụ thể cần được chi nhánh xác nhận.

Khách nên tránh mang theo quá nhiều tài sản có giá trị.

---

# Personal Belongings

Khách hàng tự chịu trách nhiệm đối với tài sản cá nhân trừ khi cửa hàng có chính sách khác.

Dữ liệu demo chưa xác nhận có tủ khóa hoặc khu vực giữ đồ.

Khách nên liên hệ cửa hàng nếu cần bảo quản hành lý hoặc vật có giá trị.

---

# Food and Alcohol

Khách hàng nên tránh dùng bữa quá no ngay trước một số dịch vụ thư giãn hoặc massage.

Khách đã sử dụng nhiều rượu bia có thể không phù hợp để sử dụng dịch vụ.

Cửa hàng có thể từ chối phục vụ vì lý do an toàn.

Chatbot không đánh giá mức độ say hoặc tình trạng sức khỏe của khách.

---

# Before the Service

Khách hàng nên:

- đến đúng giờ;
- thông báo tình trạng sức khỏe;
- thông báo dị ứng;
- nói rõ vùng cần tránh;
- tháo trang sức nếu cần;
- trao đổi mức lực mong muốn;
- tắt hoặc để điện thoại ở chế độ im lặng.

Hướng dẫn thực tế phụ thuộc vào loại dịch vụ.

---

# During the Service

Khách hàng nên thông báo ngay cho therapist nếu:

- cảm thấy đau;
- quá nóng hoặc quá lạnh;
- tư thế không thoải mái;
- dị ứng hoặc khó chịu;
- muốn thay đổi lực;
- cần dừng dịch vụ.

Khách có quyền yêu cầu dừng dịch vụ bất kỳ lúc nào.

---

# After the Service

Sau dịch vụ, khách có thể được khuyến nghị:

- uống nước;
- nghỉ ngơi;
- đứng dậy từ từ;
- tránh vận động mạnh ngay lập tức;
- theo dõi phản ứng của cơ thể.

Đây chỉ là hướng dẫn chung, không phải tư vấn y tế.

Nếu có triệu chứng bất thường, khách nên tìm hỗ trợ chuyên môn phù hợp.

---

# Hygiene

Cửa hàng được kỳ vọng duy trì vệ sinh đối với:

- phòng dịch vụ;
- khăn và ga;
- dụng cụ;
- bề mặt tiếp xúc;
- sản phẩm dùng chung.

Dữ liệu demo chưa có quy trình vệ sinh chính thức.

Khách có thể liên hệ cửa hàng để hỏi về tiêu chuẩn vệ sinh cụ thể.

---

# Privacy

Chatbot chỉ nên thu thập thông tin cần thiết cho booking.

Thông tin có thể gồm:

- conversation ID;
- chi nhánh;
- dịch vụ;
- ngày và giờ;
- số người;
- số điện thoại;
- tên khách nếu cần.

Chatbot không nên yêu cầu:

- mật khẩu;
- mã OTP;
- thông tin thẻ ngân hàng;
- giấy tờ định danh không cần thiết;
- dữ liệu y tế chi tiết ngoài mục đích hỗ trợ an toàn.

Chính sách lưu trữ và bảo vệ dữ liệu chính thức cần được doanh nghiệp xác nhận.

---

# Conversation Data

Trong môi trường MVP hiện tại, context hội thoại được lưu bằng bộ nhớ trong process.

Điều này có nghĩa là:

- context có thể mất khi server restart;
- dữ liệu không được chia sẻ giữa nhiều instance;
- conversation có thể không tiếp tục được sau khi deployment thay đổi.

Đây là limitation kỹ thuật của môi trường demo.

---

# FAQ During Booking

Khách hàng có thể đặt câu hỏi FAQ trong khi đang thực hiện booking.

FAQ được xử lý ngoài state transition của booking.

Sau khi trả lời FAQ:

- trạng thái booking được giữ nguyên;
- dữ liệu đã chọn không bị xóa;
- chatbot không tự xác nhận booking;
- khách có thể tiếp tục từ bước trước đó.

FAQ không gọi POS và không tạo booking.

---

# Knowledge Availability

FAQ semantic retrieval chỉ hoạt động khi:

- Qdrant feature được bật;
- Qdrant đang hoạt động;
- collection đã được tạo;
- tài liệu đã được index;
- embedding model có thể load;
- query embedding thành công.

Nếu knowledge service không khả dụng, chatbot sẽ trả thông báo an toàn thay vì làm hỏng booking flow.

Booking vẫn có thể tiếp tục khi FAQ/Qdrant không hoạt động.

---

# FAQ Limitations

Tài liệu knowledge demo không bao phủ mọi tình huống.

Chatbot có thể không trả lời chính xác nếu:

- câu hỏi nằm ngoài nội dung đã index;
- chính sách cửa hàng chưa được xác nhận;
- tài liệu đã cũ;
- query quá mơ hồ;
- thuật ngữ khác nhiều so với tài liệu;
- Qdrant hoặc embedding model không khả dụng.

Khi không chắc chắn, chatbot nên hướng dẫn khách liên hệ cửa hàng.

---

# Emergency Situations

Chatbot không xử lý tình huống y tế khẩn cấp.

Nếu khách đang gặp vấn đề nghiêm trọng hoặc cần hỗ trợ khẩn cấp, khách nên liên hệ cơ quan hỗ trợ phù hợp tại địa phương.

Không sử dụng chatbot để thay thế dịch vụ khẩn cấp hoặc tư vấn y tế chuyên môn.

---

# Complaints and Feedback

Dữ liệu demo chưa có quy trình khiếu nại chính thức.

Khách hàng muốn phản ánh chất lượng dịch vụ nên cung cấp:

- chi nhánh;
- ngày và giờ;
- tên hoặc số điện thoại booking;
- nội dung phản hồi;
- thông tin liên hệ.

Chatbot không tự hứa hoàn tiền hoặc bồi thường.

Quyết định xử lý thuộc về cửa hàng hoặc bộ phận chăm sóc khách hàng.

---

# Lost and Found

Khách để quên đồ nên liên hệ chi nhánh càng sớm càng tốt.

Dữ liệu demo chưa có thời hạn lưu giữ tài sản thất lạc.

Chatbot không thể xác nhận một vật đã được tìm thấy nếu chưa có phản hồi từ cửa hàng.

---

# Service Refusal

Cửa hàng có thể từ chối hoặc dừng dịch vụ khi:

- có nguy cơ an toàn;
- khách có dấu hiệu bệnh truyền nhiễm;
- khách có hành vi không phù hợp;
- khách sử dụng rượu bia quá mức;
- tình trạng sức khỏe không phù hợp;
- yêu cầu nằm ngoài phạm vi dịch vụ;
- không thể đáp ứng therapist hoặc cơ sở vật chất.

Chính sách chính thức cần được cửa hàng xác nhận.

---

# Prohibited Conduct

Khách hàng cần cư xử tôn trọng với nhân viên và khách khác.

Các hành vi quấy rối, đe dọa, bạo lực hoặc yêu cầu không phù hợp có thể dẫn đến việc từ chối phục vụ.

Chatbot không hỗ trợ nội dung tình dục hoặc yêu cầu dịch vụ ngoài phạm vi hợp pháp và chuyên nghiệp.

---

# Holiday Schedule

Giờ hoạt động vào ngày lễ có thể khác lịch thông thường.

Dữ liệu demo chưa có lịch ngày lễ cụ thể.

Khách hàng nên kiểm tra availability hoặc liên hệ chi nhánh trước khi đến.

---

# Weather and Unexpected Closures

Cửa hàng có thể thay đổi lịch hoạt động do:

- thời tiết xấu;
- mất điện;
- bảo trì;
- sự cố kỹ thuật;
- thiếu nhân sự;
- yêu cầu của cơ quan chức năng.

Nếu booking bị ảnh hưởng, cửa hàng có thể liên hệ khách để sắp xếp lại.

Chatbot không bảo đảm luôn nhận được thông tin đóng cửa theo thời gian thực.

---

# Supported Languages

Chatbot demo được thiết kế ưu tiên tiếng Việt.

Khả năng hỗ trợ tiếng Anh hoặc ngôn ngữ khác phụ thuộc vào NLU, tài liệu knowledge và model được cấu hình.

Thông tin trong câu trả lời có thể kém chính xác nếu tài liệu chưa có nội dung tương ứng bằng ngôn ngữ người dùng.

---

# Chatbot Scope

Chatbot create-booking MVP hỗ trợ:

- bắt đầu booking;
- chọn chi nhánh;
- chọn ngày;
- chọn số người;
- chọn thời lượng;
- chọn dịch vụ;
- chọn thời gian;
- chọn hoặc bỏ qua therapist;
- nhập và xác nhận số điện thoại;
- xác nhận cuối;
- tạo booking;
- trả lời FAQ từ knowledge base khi Qdrant được bật.

Chatbot MVP chưa bảo đảm hỗ trợ đầy đủ:

- tra cứu booking;
- hủy booking đã tạo;
- reschedule;
- thanh toán;
- voucher;
- refund;
- loyalty;
- upload tài liệu;
- tư vấn y tế;
- hỗ trợ khẩn cấp.

---

# When to Contact the Store

Khách hàng nên liên hệ trực tiếp cửa hàng khi:

- chatbot không tìm thấy dịch vụ;
- không có khung giờ phù hợp;
- cần booking trên 3 người;
- cần đặt nhiều dịch vụ phức tạp;
- cần therapist cụ thể;
- có tình trạng sức khỏe đặc biệt;
- cần hủy hoặc đổi booking đã tạo;
- muốn hỏi về giá chính thức;
- cần xác nhận khuyến mãi;
- cần hỗ trợ thanh toán;
- cần xác nhận bãi đậu xe;
- có yêu cầu tiếp cận đặc biệt;
- dự kiến đến trễ;
- muốn gửi khiếu nại hoặc phản hồi.
