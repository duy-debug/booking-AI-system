# Cơ sở tri thức mẫu cho chatbot đặt lịch massage

Tài liệu này mô tả các chính sách, quy định và hướng dẫn vận hành mẫu dành cho chatbot hỗ trợ khách hàng tại cơ sở massage, spa và chăm sóc sức khỏe. Nội dung được xây dựng để phục vụ việc kiểm thử hệ thống chatbot, tìm kiếm thông tin bằng cơ sở tri thức và luồng đặt lịch tự động. Các mức phí, thời hạn, điều kiện phục vụ và quy định cụ thể trong tài liệu này chỉ mang tính minh họa. Trước khi sử dụng trong môi trường thực tế, cửa hàng cần kiểm tra, điều chỉnh và xác nhận lại toàn bộ nội dung.

# Giờ hoạt động của cửa hàng

Trong dữ liệu mẫu, cửa hàng hoạt động từ 08 giờ 00 đến 22 giờ 00 từ thứ Hai đến thứ Bảy và nghỉ vào Chủ nhật. Giờ hoạt động thực tế có thể khác nhau giữa các chi nhánh và có thể thay đổi vào ngày lễ, thời gian bảo trì hoặc các trường hợp vận hành đặc biệt. Khi khách hỏi về giờ mở cửa, chatbot nên ưu tiên dữ liệu mới nhất của chi nhánh được lưu trong hệ thống thay vì sử dụng một khung giờ mặc định cho tất cả cửa hàng.

# Thời gian nhận khách cuối cùng

Thời gian nhận khách cuối cùng trong ngày phụ thuộc vào giờ đóng cửa và thời lượng của dịch vụ mà khách lựa chọn. Ví dụ, nếu cửa hàng đóng cửa lúc 22 giờ 00 và dịch vụ kéo dài 90 phút thì hệ thống có thể không cho phép khách bắt đầu dịch vụ vào lúc 21 giờ 30. Chatbot không được tự tính và tạo ra một khung giờ nếu hệ thống đặt lịch không cung cấp khung giờ đó, mà chỉ được hiển thị những thời gian còn trống được hệ thống xác nhận.

# Thay đổi giờ hoạt động

Giờ hoạt động có thể được điều chỉnh tạm thời do ngày lễ, sự kiện nội bộ, thiếu nhân viên, bảo trì cơ sở vật chất, mất điện, thời tiết hoặc các tình huống bất khả kháng khác. Trong trường hợp có sự khác nhau giữa tài liệu hướng dẫn và dữ liệu hoạt động hiện tại của chi nhánh, chatbot phải ưu tiên thông tin mới nhất từ hệ thống quản lý cửa hàng hoặc hướng dẫn khách liên hệ trực tiếp qua số 1900 8095 để xác nhận.

# Đặt lịch trước

Khách được khuyến khích đặt lịch trước, đặc biệt vào cuối tuần, ngày lễ, khung giờ buổi chiều tối, các dịch vụ có thời lượng dài hoặc khi khách muốn lựa chọn một kỹ thuật viên cụ thể. Đặt lịch trước giúp cửa hàng có thêm thời gian sắp xếp nhân sự và phòng dịch vụ nhưng không đồng nghĩa với việc một khung giờ được giữ cho khách cho đến khi hệ thống đặt lịch xác nhận booking thành công.

# Đặt lịch trong ngày

Khách có thể đặt lịch trong cùng ngày nếu hệ thống vẫn còn khung giờ phù hợp với dịch vụ, chi nhánh, số lượng khách và yêu cầu về kỹ thuật viên. Một số dịch vụ có thể cần thời gian chuẩn bị nên khả năng đặt sát giờ không được đảm bảo. Chatbot chỉ được xác nhận còn chỗ sau khi kiểm tra dữ liệu khả dụng thực tế từ hệ thống quản lý lịch.

# Đặt lịch sát giờ sử dụng dịch vụ

Đối với yêu cầu đặt lịch quá gần thời điểm hiện tại, cửa hàng có thể không đủ thời gian chuẩn bị phòng, sản phẩm hoặc kỹ thuật viên. Vì vậy, ngay cả khi cửa hàng đang trong giờ hoạt động, khách vẫn có thể không đặt được dịch vụ ngay lập tức. Chatbot nên kiểm tra các khung giờ thực tế còn khả dụng và đề xuất thời gian gần nhất thay vì cam kết rằng khách có thể đến ngay.

# Giá trị của khung giờ còn trống

Khung giờ được chatbot hiển thị chỉ phản ánh tình trạng còn trống tại thời điểm hệ thống kiểm tra. Trong khoảng thời gian khách đang lựa chọn hoặc trao đổi thêm thông tin, một khách hàng khác có thể hoàn tất đặt lịch trước và chiếm khung giờ đó. Vì vậy, khung giờ chỉ được xem là thuộc về khách sau khi hệ thống quản lý lịch xác nhận booking được tạo thành công.

# Kiểm tra lại khung giờ trước khi xác nhận

Ngay trước khi gửi yêu cầu tạo booking chính thức, hệ thống nên kiểm tra lại khả năng phục vụ của khung giờ đã chọn nếu đã có một khoảng thời gian đáng kể kể từ lần kiểm tra trước. Việc này giúp hạn chế trường hợp chatbot hiển thị một khung giờ cũ nhưng kỹ thuật viên hoặc phòng dịch vụ đã được khách khác đặt trong thời gian chờ.

# Khung giờ đã hết chỗ

Nếu khung giờ khách mong muốn không còn trống, chatbot không được tự thay đổi sang giờ khác và coi như khách đã đồng ý. Hệ thống nên thông báo rằng thời gian đó hiện không còn khả dụng và có thể đưa ra một số lựa chọn gần nhất để khách chủ động quyết định. Booking chỉ được tiếp tục với khung giờ mới sau khi khách lựa chọn hoặc xác nhận rõ ràng.

# Đặt lịch cho một khách

Đối với booking một người, khách có thể lựa chọn chi nhánh, dịch vụ, ngày và giờ phù hợp. Tùy khả năng của hệ thống, khách cũng có thể yêu cầu một kỹ thuật viên cụ thể hoặc ưu tiên kỹ thuật viên nam hay nữ. Nếu khách không có yêu cầu về kỹ thuật viên, cửa hàng có thể tự sắp xếp nhân viên phù hợp dựa trên lịch làm việc và loại dịch vụ.

# Đặt lịch cho nhóm khách

Trong phạm vi hệ thống mẫu, chatbot có thể hỗ trợ booking cho nhóm từ hai đến ba người nếu tất cả khách cùng sử dụng một chi nhánh, ngày và khung giờ phù hợp. Khả năng phục vụ đồng thời còn phụ thuộc số lượng kỹ thuật viên, số phòng và dịch vụ được lựa chọn. Với nhóm đông hơn phạm vi hệ thống hỗ trợ, chatbot nên hướng dẫn khách liên hệ trực tiếp cửa hàng qua số 1900 8095 để được sắp xếp.

# Đặt lịch cho hai người

Booking hai người cùng thời gian không đồng nghĩa với việc cửa hàng chắc chắn có phòng đôi hoặc hai giường nằm cạnh nhau. Hệ thống chỉ xác nhận khả năng phục vụ hai khách trong cùng khung giờ nếu có đủ nhân sự và tài nguyên. Nếu khách yêu cầu phòng đôi hoặc muốn hai người được phục vụ trong cùng một phòng, yêu cầu đó cần được xác nhận riêng với cửa hàng.

# Thay đổi số lượng khách

Nếu khách thay đổi từ một người sang hai hoặc ba người, khung giờ trước đó có thể không còn phù hợp vì hệ thống phải tìm đủ số lượng kỹ thuật viên và phòng cho nhóm mới. Khi số lượng khách thay đổi, chatbot phải kiểm tra lại khả năng phục vụ và không được tiếp tục sử dụng khung giờ cũ mà chưa xác minh.

# Lựa chọn dịch vụ

Danh sách dịch vụ mà khách có thể đặt phải được lấy từ dữ liệu đang hoạt động của chi nhánh đã chọn. Một dịch vụ có thể có tại chi nhánh này nhưng không có tại chi nhánh khác hoặc có thể tạm thời ngừng cung cấp. Chatbot không được tạo ra tên dịch vụ mới hoặc xác nhận rằng cửa hàng có dịch vụ nếu hệ thống quản lý hiện tại không có dữ liệu tương ứng.

# Dịch vụ chính của booking

Mỗi booking phải có ít nhất một dịch vụ chính. Dịch vụ chính quyết định các yếu tố quan trọng như thời lượng, giá cơ bản, kỹ thuật viên có thể thực hiện và những khung giờ có thể đặt. Nếu khách thay đổi dịch vụ chính trong quá trình đặt lịch, hệ thống cần kiểm tra lại các thông tin phụ thuộc như thời lượng, giá, kỹ thuật viên và khung giờ.

# Thời lượng dịch vụ

Mỗi dịch vụ có một hoặc nhiều thời lượng được cửa hàng quy định sẵn, chẳng hạn 60 phút, 90 phút hoặc 120 phút. Chatbot chỉ được cho phép khách lựa chọn những thời lượng mà hệ thống quản lý dịch vụ hỗ trợ. Nếu khách yêu cầu thời lượng không tồn tại, ví dụ 75 phút trong khi hệ thống chỉ có 60 và 90 phút, chatbot nên đưa ra những lựa chọn hợp lệ thay vì tự tạo thời lượng mới.

# Dịch vụ bổ sung

Dịch vụ bổ sung là những lựa chọn có thể được kết hợp với dịch vụ chính để mở rộng trải nghiệm của khách. Không phải mọi dịch vụ bổ sung đều có thể kết hợp với tất cả dịch vụ chính và việc bổ sung có thể làm thay đổi tổng thời gian cũng như tổng chi phí. Chatbot chỉ được xác nhận dịch vụ bổ sung khi hệ thống quản lý cho phép kết hợp đó.

# Thay đổi dịch vụ trong quá trình đặt lịch

Khách có thể đổi dịch vụ trước khi booking được xác nhận cuối cùng. Tuy nhiên, khi dịch vụ thay đổi, các thông tin đã lựa chọn trước đó như thời lượng, kỹ thuật viên, giá hoặc khung giờ có thể không còn phù hợp. Hệ thống cần xóa hoặc kiểm tra lại những dữ liệu phụ thuộc này trước khi tiếp tục luồng đặt lịch.

# Giá dịch vụ

Giá dịch vụ phụ thuộc vào chi nhánh, loại dịch vụ, thời lượng, dịch vụ bổ sung và các chương trình hiện hành. Chatbot không được tự suy đoán hoặc tính giá dựa trên thông tin không có trong hệ thống. Nếu hệ thống quản lý trả về mức giá hiện tại thì mức giá đó được ưu tiên hơn thông tin giá được lưu trong tài liệu hướng dẫn cũ.

# Giá cuối cùng của booking

Mức giá cuối cùng chỉ nên được xem là chính xác khi hệ thống đã xác định đầy đủ dịch vụ chính, thời lượng, dịch vụ bổ sung, chi nhánh và các yếu tố ảnh hưởng đến giá. Nếu chưa đủ dữ liệu, chatbot có thể cung cấp giá tham khảo nếu knowledge có thông tin nhưng cần nói rõ rằng giá cuối cùng sẽ được xác nhận trước khi hoàn tất booking.

# Thay đổi giá dịch vụ

Cửa hàng có quyền điều chỉnh giá theo từng thời điểm, chi nhánh hoặc chương trình kinh doanh. Vì vậy, các mức giá được lưu trong tài liệu tĩnh có thể trở nên lỗi thời. Khi có sự khác biệt giữa tài liệu knowledge và dữ liệu giao dịch hiện tại trong hệ thống quản lý, chatbot phải sử dụng giá từ hệ thống quản lý.

# Khuyến mãi

Các chương trình khuyến mãi có thể có điều kiện riêng về thời gian áp dụng, chi nhánh, dịch vụ, số lượng khách hoặc nhóm khách hàng. Chatbot không được tự động áp dụng mức giảm giá hoặc hứa khách chắc chắn được hưởng ưu đãi khi chưa có dữ liệu chính thức. Nếu chương trình chưa được tích hợp với hệ thống, chatbot nên hướng dẫn khách xác nhận trực tiếp với cửa hàng.

# Kết hợp nhiều chương trình ưu đãi

Một khách hàng có thể có nhiều mã giảm giá, voucher hoặc quyền lợi thành viên nhưng việc cộng dồn các chương trình phụ thuộc chính sách của cửa hàng. Chatbot không được tự tính tổng mức giảm hoặc khẳng định nhiều ưu đãi có thể sử dụng cùng lúc nếu hệ thống không cung cấp quy tắc rõ ràng.

# Yêu cầu kỹ thuật viên cụ thể

Khách có thể yêu cầu một kỹ thuật viên cụ thể nếu cửa hàng cho phép. Yêu cầu này chỉ được xác nhận khi hệ thống kiểm tra lịch làm việc và cho thấy kỹ thuật viên đó thực sự có thể thực hiện dịch vụ vào khung giờ đã chọn. Nếu kỹ thuật viên không còn trống, chatbot có thể đề xuất một thời gian khác hoặc để khách chọn kỹ thuật viên khác.

# Ưu tiên kỹ thuật viên nam hoặc nữ

Khách có thể đưa ra mong muốn được phục vụ bởi kỹ thuật viên nam hoặc nữ. Đây là một ưu tiên cần được hệ thống kiểm tra theo lịch nhân sự và loại dịch vụ, không phải một cam kết tự động. Nếu không có nhân viên phù hợp trong khung giờ mong muốn, chatbot nên thông báo rõ và đưa ra lựa chọn thời gian hoặc phương án khác.

# Không yêu cầu kỹ thuật viên

Nếu khách không có yêu cầu cụ thể về kỹ thuật viên, cửa hàng có thể tự phân công một nhân viên đủ khả năng thực hiện dịch vụ. Việc phân công cuối cùng có thể thay đổi vì lịch nghỉ, điều chỉnh ca làm hoặc các tình huống vận hành nhưng cửa hàng nên cố gắng đảm bảo loại dịch vụ và thời lượng booking không bị ảnh hưởng.

# Thay đổi kỹ thuật viên

Trong một số trường hợp, kỹ thuật viên đã dự kiến phục vụ có thể nghỉ đột xuất, thay đổi ca hoặc không thể tiếp tục thực hiện booking. Cửa hàng có thể bố trí một kỹ thuật viên khác có khả năng thực hiện dịch vụ tương đương. Nếu khách chỉ muốn sử dụng dịch vụ với một kỹ thuật viên nhất định, khách nên thông báo để cửa hàng hỗ trợ đổi thời gian nếu cần.

# Thời gian khách nên có mặt

Khách được khuyến khích có mặt trước giờ hẹn khoảng 10 đến 15 phút để hoàn tất bước xác nhận thông tin, thay trang phục nếu cần và trao đổi với kỹ thuật viên về tình trạng sức khỏe hoặc mong muốn đối với dịch vụ. Việc đến sớm đặc biệt hữu ích với khách lần đầu sử dụng dịch vụ tại cửa hàng.

# Khách đến trễ

Nếu khách đến muộn, cửa hàng có thể phải rút ngắn thời lượng dịch vụ để không ảnh hưởng đến lịch của khách tiếp theo. Trong trường hợp khách đến quá trễ và không còn đủ thời gian thực hiện dịch vụ một cách phù hợp, cửa hàng có thể yêu cầu đổi lịch hoặc từ chối tiếp nhận. Khách nên liên hệ cửa hàng sớm qua số 1900 8095 nếu biết mình sẽ đến muộn.

# Thời gian cho phép đến trễ

Thời gian cho phép khách đến trễ phụ thuộc chính sách của từng cửa hàng và tình trạng lịch trong ngày. Chatbot không nên tự đưa ra một mốc như 10 hoặc 15 phút nếu cửa hàng chưa chính thức xác nhận. Trong trường hợp chưa có quy định rõ ràng, chatbot nên thông báo rằng khách cần liên hệ chi nhánh qua số 1900 8095 để được hỗ trợ.

# Rút ngắn dịch vụ khi khách đến muộn

Nếu khách đến muộn nhưng cửa hàng vẫn có thể tiếp nhận, thời gian dịch vụ có thể được rút ngắn để bảo đảm booking tiếp theo bắt đầu đúng giờ. Việc rút ngắn thời lượng do khách đến muộn không nhất thiết đồng nghĩa với việc giá dịch vụ được giảm. Điều kiện cụ thể về giá trong trường hợp này cần được cửa hàng xác nhận.

# Khách không đến theo lịch

Nếu khách không đến và không thông báo trước, booking có thể được ghi nhận là khách vắng mặt. Tùy chính sách của cửa hàng, trường hợp này có thể ảnh hưởng đến khoản đặt cọc, voucher hoặc quyền lợi đặt lịch trong tương lai. Chatbot không được tự áp dụng phí hoặc hình thức xử lý nếu chính sách chính thức chưa được cấu hình.

# Chính sách hủy lịch

Khách nên thông báo hủy lịch càng sớm càng tốt để cửa hàng có thể sắp xếp khung giờ cho khách khác. Thời hạn hủy miễn phí hoặc phí hủy muộn phải do cửa hàng quy định. Trong dữ liệu demo hiện tại chưa xác định một mức phí cụ thể, vì vậy chatbot không được tự thông báo rằng khách sẽ mất một tỷ lệ tiền hoặc một khoản cố định.

# Hủy lịch sát giờ

Việc hủy lịch quá gần thời điểm sử dụng dịch vụ có thể khiến cửa hàng không thể bố trí khách khác vào khung giờ đã giữ. Do đó, một số cửa hàng có thể áp dụng phí hủy trễ hoặc không hoàn lại khoản đặt cọc. Chatbot chỉ được thông báo mức phí nếu thông tin đó đã được cửa hàng xác nhận và lưu trong chính sách chính thức.

# Đổi lịch

Khách có thể muốn thay đổi ngày hoặc giờ của booking đã tạo. Tuy nhiên, trong phiên bản MVP hiện tại, chatbot chỉ hỗ trợ tạo booking mới và chưa trực tiếp thực hiện chức năng đổi lịch đã tồn tại. Trong trường hợp này, chatbot cần hướng dẫn khách liên hệ cửa hàng qua số 1900 8095 thay vì tự thông báo rằng booking đã được thay đổi.

# Hủy booking đã tạo

Chức năng hủy một booking đã được tạo chưa thuộc phạm vi của phiên bản MVP nếu hệ thống chưa có API hủy booking. Chatbot không được nói những câu như “lịch của bạn đã được hủy thành công” khi chưa nhận được xác nhận từ hệ thống quản lý. Khách cần được hướng dẫn liên hệ trực tiếp cửa hàng qua số 1900 8095 để thực hiện việc hủy.

# Thay đổi thông tin trước khi xác nhận booking

Trước khi booking được tạo chính thức, khách có thể thay đổi các thông tin như chi nhánh, dịch vụ, thời lượng, ngày, giờ, số người hoặc kỹ thuật viên. Chatbot cần cập nhật dữ liệu mới nhất và kiểm tra lại các trường phụ thuộc. Ví dụ, nếu khách đổi chi nhánh thì dịch vụ, kỹ thuật viên và khung giờ đã chọn ở chi nhánh trước có thể không còn hợp lệ.

# Xác nhận cuối cùng trước khi tạo booking

Trước khi gửi yêu cầu tạo booking đến hệ thống quản lý, chatbot nên trình bày lại các thông tin quan trọng để khách kiểm tra, bao gồm chi nhánh, dịch vụ, thời lượng, ngày, giờ, số lượng khách và các yêu cầu đặc biệt nếu có. Booking chỉ được tạo sau khi khách thể hiện ý định xác nhận rõ ràng và hệ thống đã có đầy đủ dữ liệu bắt buộc.

# Booking chưa được xác nhận

Thông tin đang được thu thập trong hội thoại chỉ được xem là một bản nháp cho đến khi hệ thống quản lý xác nhận tạo booking thành công. Việc khách chọn dịch vụ, thời gian hoặc nói rằng muốn đặt lịch chưa đồng nghĩa với việc khung giờ đã được giữ. Chatbot cần tránh sử dụng những từ như “đã đặt thành công” trước khi có phản hồi xác nhận từ hệ thống.

# Booking thành công

Booking chỉ được xem là thành công khi hệ thống quản lý lịch hoặc POS trả về kết quả xác nhận tạo booking thành công. Sau đó chatbot có thể thông báo cho khách về ngày, giờ, dịch vụ, chi nhánh và mã booking dành cho khách nếu hệ thống cung cấp. Các mã kỹ thuật nội bộ không được dùng thay cho mã booking dành cho người dùng.

# Mã booking

Khi hệ thống trả về một mã booking dành cho khách hàng, chatbot có thể hiển thị mã này để khách sử dụng khi liên hệ hoặc check-in. Các mã nội bộ như mã bản ghi cơ sở dữ liệu, mã reservation nội bộ hoặc UUID không nên được hiển thị nếu chúng không được thiết kế để khách sử dụng.

# Booking thất bại

Nếu hệ thống quản lý từ chối yêu cầu tạo booking hoặc xảy ra lỗi trong quá trình tạo, chatbot phải nói rõ rằng lịch chưa được đặt thành công. Nếu lỗi liên quan đến dữ liệu như khung giờ vừa hết chỗ, hệ thống nên cho phép khách lựa chọn lại. Nếu là lỗi kỹ thuật, chatbot có thể hướng dẫn khách thử lại hoặc liên hệ cửa hàng qua số 1900 8095 nhưng không được giả định booking đã được tạo.

# Tránh tạo booking trùng

Trong trường hợp mạng chậm, người dùng bấm nhiều lần hoặc frontend gửi lại request, backend cần có cơ chế hạn chế tạo nhiều booking cho cùng một yêu cầu. Nếu hệ thống quản lý hỗ trợ khóa chống trùng hoặc mã idempotency, backend nên sử dụng để giảm nguy cơ khách bị tạo hai lịch giống nhau.

# Thanh toán

Phiên bản create-booking mẫu chỉ hỗ trợ tạo lịch và không trực tiếp xử lý thanh toán. Chatbot không được yêu cầu khách nhập số thẻ ngân hàng, mã bảo mật thẻ, mật khẩu ngân hàng hoặc mã xác thực giao dịch. Nếu cửa hàng yêu cầu thanh toán trước, chức năng này cần được triển khai thông qua một hệ thống thanh toán an toàn riêng.

# Phương thức thanh toán

Cửa hàng có thể hỗ trợ tiền mặt, thẻ ngân hàng, chuyển khoản, mã QR hoặc ví điện tử tùy từng chi nhánh. Nếu knowledge hoặc POS chưa xác nhận phương thức nào được hỗ trợ, chatbot không nên tự khẳng định. Khách cần được hướng dẫn xác nhận với chi nhánh qua số 1900 8095 khi thông tin thanh toán chưa rõ ràng.

# Đặt cọc

Một số cơ sở massage có thể yêu cầu khách đặt cọc đối với dịch vụ dài, nhóm đông hoặc khung giờ cao điểm. Tuy nhiên, dữ liệu demo hiện tại chưa có chính sách đặt cọc chính thức. Chatbot không được tự yêu cầu khách chuyển tiền hoặc cung cấp tài khoản ngân hàng khi chưa có dữ liệu được cửa hàng phê duyệt.

# Hoàn tiền đặt cọc

Điều kiện hoàn lại tiền đặt cọc có thể phụ thuộc vào thời điểm khách hủy lịch, phương thức thanh toán và chính sách của cửa hàng. Nếu chưa có quy định chính thức, chatbot không được cam kết rằng khách chắc chắn được hoàn tiền hoặc chắc chắn mất tiền cọc mà phải hướng dẫn khách liên hệ cửa hàng qua số 1900 8095.

# Chính sách hoàn tiền

Việc hoàn tiền đối với một dịch vụ, booking hoặc khoản thanh toán phải được xử lý theo quy định chính thức của cửa hàng. Chatbot không có quyền tự quyết định khách có đủ điều kiện hoàn tiền hay không và không được hứa về thời gian hoặc số tiền hoàn lại nếu hệ thống chưa cung cấp kết quả xác nhận.

# Voucher và phiếu quà tặng

Voucher hoặc phiếu quà tặng có thể có điều kiện riêng về thời gian sử dụng, dịch vụ, chi nhánh và giá trị. Chatbot chỉ được xác nhận voucher hợp lệ khi hệ thống có chức năng kiểm tra hoặc knowledge có dữ liệu chính thức. Nếu không thể xác minh, khách nên được hướng dẫn mang voucher đến cửa hàng hoặc liên hệ trước qua số 1900 8095.

# Khách hàng thành viên

Thông tin khách hàng thành viên có thể được kiểm tra bằng số điện thoại nếu hệ thống quản lý cửa hàng hỗ trợ. Quyền lợi của từng hạng thành viên như giảm giá, tích điểm hoặc ưu tiên booking phải lấy từ dữ liệu chính thức. Chatbot không được suy đoán quyền lợi dựa trên việc khách tự nói mình là thành viên.

# Số điện thoại khách hàng

Số điện thoại được sử dụng để tìm kiếm hồ sơ khách, liên kết booking và hỗ trợ cửa hàng liên hệ khi cần. Hệ thống chỉ nên thu thập số điện thoại trong phạm vi cần thiết cho nghiệp vụ đặt lịch. Khi ghi log kỹ thuật, số điện thoại không nên được ghi đầy đủ mà cần được che bớt để giảm nguy cơ lộ dữ liệu cá nhân.

# Tên khách hàng

Nếu hệ thống quản lý chưa có hồ sơ tương ứng với số điện thoại, chatbot có thể yêu cầu khách cung cấp tên để tạo booking. Chatbot không được tự suy luận tên của khách từ số điện thoại, địa chỉ email hoặc các thông tin không đáng tin cậy khác.

# Xác minh số điện thoại

Trong luồng demo, việc xác minh số điện thoại có nghĩa là khách xác nhận rằng số điện thoại được sử dụng cho booking là chính xác. Đây không phải là quá trình xác minh danh tính pháp lý. Chatbot không được yêu cầu khách cung cấp mật khẩu, mã OTP hoặc giấy tờ cá nhân nếu hệ thống hiện tại không có quy trình xác thực chính thức.

# Thông tin sức khỏe trước dịch vụ

Trước khi sử dụng dịch vụ, khách nên chủ động thông báo cho cửa hàng qua số 1900 8095 hoặc trao đổi trực tiếp với kỹ thuật viên về các vấn đề sức khỏe có thể ảnh hưởng đến quá trình massage như chấn thương, phẫu thuật gần đây, bệnh tim mạch, vấn đề huyết áp, tình trạng da, dị ứng hoặc các tình trạng đặc biệt khác. Chatbot chỉ có nhiệm vụ nhắc khách cung cấp thông tin cần thiết và không được tự đánh giá liệu khách có đủ điều kiện y tế để sử dụng dịch vụ hay không.

# Khách đang mang thai

Khách đang mang thai nên thông báo rõ tình trạng cho cửa hàng qua số 1900 8095 trước khi lựa chọn dịch vụ vì không phải loại massage hoặc kỹ thuật nào cũng phù hợp cho mọi giai đoạn thai kỳ. Chatbot không được tự xác nhận một dịch vụ là an toàn dựa trên số tuần mang thai hoặc triệu chứng mà khách mô tả. Trong trường hợp có nghi ngại về sức khỏe, khách nên trao đổi với chuyên gia y tế phù hợp và cửa hàng trước khi sử dụng dịch vụ.

# Khách vừa phẫu thuật

Khách vừa thực hiện phẫu thuật, thủ thuật y tế hoặc đang trong quá trình hồi phục nên thông báo cho cửa hàng qua số 1900 8095 trước khi sử dụng dịch vụ massage. Tùy vị trí phẫu thuật và tình trạng hồi phục, cửa hàng có thể yêu cầu khách hoãn dịch vụ hoặc tránh tác động lên một số khu vực. Chatbot không được tự đưa ra thời gian bao nhiêu ngày sau phẫu thuật thì khách có thể massage.

# Khách có chấn thương

Khách đang có chấn thương cơ, xương, khớp, bong gân hoặc đau tại một vị trí cụ thể cần thông báo cho kỹ thuật viên trước khi bắt đầu. Kỹ thuật viên có thể điều chỉnh lực hoặc tránh khu vực đó tùy tình trạng. Nếu khách có chấn thương nghiêm trọng hoặc chưa được đánh giá, chatbot nên khuyến nghị khách tìm hỗ trợ chuyên môn thích hợp thay vì đưa ra hướng điều trị.

# Dị ứng

Khách có tiền sử dị ứng với tinh dầu, mỹ phẩm, thảo dược, latex, hương liệu hoặc thành phần chăm sóc da cần thông báo cho cửa hàng qua số 1900 8095 trước dịch vụ. Khách nên cung cấp tên chất hoặc sản phẩm gây dị ứng nếu biết. Cửa hàng sẽ quyết định liệu có thể sử dụng sản phẩm thay thế hay cần thay đổi dịch vụ.

# Nhạy cảm với mùi hương

Nếu khách nhạy cảm với tinh dầu, nước hoa hoặc mùi hương mạnh, khách nên thông báo trước để cửa hàng kiểm tra khả năng sử dụng sản phẩm không mùi hoặc giảm mùi. Chatbot không được đảm bảo chắc chắn cơ sở có sản phẩm không hương liệu nếu kho sản phẩm và quy định chi nhánh chưa được xác nhận.

# Bệnh truyền nhiễm

Khách đang sốt, có triệu chứng bệnh truyền nhiễm hoặc đang trong tình trạng có khả năng ảnh hưởng đến sức khỏe của nhân viên và khách khác nên cân nhắc hoãn lịch. Cửa hàng có quyền từ chối phục vụ nếu đánh giá tình trạng có nguy cơ đối với an toàn chung. Chatbot không có chức năng chẩn đoán bệnh và chỉ nên cung cấp hướng dẫn an toàn chung.

# Vết thương hở và tình trạng da

Khách có vết thương hở, nhiễm trùng da, vùng da đang chảy máu hoặc tình trạng da nghiêm trọng cần thông báo cho cửa hàng qua số 1900 8095 trước khi sử dụng dịch vụ. Kỹ thuật viên có thể tránh khu vực đó hoặc từ chối thực hiện dịch vụ nếu có nguy cơ làm tình trạng trở nên xấu hơn hoặc gây ảnh hưởng đến vệ sinh.

# Uống rượu bia trước dịch vụ

Khách nên tránh sử dụng quá nhiều rượu bia trước khi massage. Nếu khách có dấu hiệu say xỉn, mất khả năng phối hợp hoặc không thể giao tiếp rõ ràng, cửa hàng có quyền từ chối hoặc hoãn dịch vụ vì lý do an toàn. Chatbot không nên hướng dẫn khách sử dụng rượu bia trước hoặc trong quá trình sử dụng dịch vụ.

# Ăn uống trước dịch vụ

Khách nên tránh ăn quá no ngay trước khi massage vì tư thế nằm và các thao tác trên cơ thể có thể gây khó chịu. Tuy nhiên, đây chỉ là hướng dẫn chung và không phải quy định y tế. Nếu khách có chế độ ăn uống hoặc tình trạng sức khỏe đặc biệt, khách nên làm theo hướng dẫn từ chuyên gia chăm sóc sức khỏe của mình.

# Trang phục khi đến cửa hàng

Khách nên mặc trang phục thoải mái và thuận tiện cho quá trình chuẩn bị. Tùy loại dịch vụ, cửa hàng có thể cung cấp quần áo, khăn hoặc vật dụng thay thế. Chatbot không nên đảm bảo chắc chắn có phòng thay đồ, tủ khóa hoặc trang phục riêng nếu thông tin đó chưa được chi nhánh xác nhận.

# Tài sản cá nhân

Khách nên hạn chế mang theo nhiều tiền mặt, trang sức hoặc tài sản có giá trị khi đến sử dụng dịch vụ. Khả năng cung cấp tủ khóa hoặc khu vực giữ đồ phụ thuộc từng chi nhánh. Nếu khách mang theo hành lý lớn hoặc vật có giá trị cao, khách nên liên hệ trước với cửa hàng qua số 1900 8095 để hỏi về khả năng lưu giữ.

# Trao đổi trước khi bắt đầu dịch vụ

Trước khi massage, khách nên trao đổi với kỹ thuật viên về mức lực mong muốn, khu vực muốn tập trung, vùng cần tránh, tiền sử chấn thương, dị ứng hoặc bất kỳ tình trạng nào có thể ảnh hưởng đến trải nghiệm. Các thông tin này giúp kỹ thuật viên điều chỉnh dịch vụ phù hợp hơn trong phạm vi chuyên môn được phép.

# Mức lực massage

Khách có thể trao đổi với kỹ thuật viên về mức lực nhẹ, vừa hoặc mạnh tùy loại dịch vụ. Tuy nhiên, mong muốn sử dụng lực mạnh không có nghĩa kỹ thuật viên bắt buộc phải thực hiện nếu đánh giá rằng thao tác đó không phù hợp hoặc không an toàn. Trong quá trình dịch vụ, khách có thể yêu cầu điều chỉnh mức lực bất kỳ lúc nào.

# Khu vực khách không muốn massage

Khách có quyền yêu cầu kỹ thuật viên không tác động lên một hoặc nhiều vùng cơ thể. Yêu cầu này cần được tôn trọng miễn là vẫn có thể thực hiện dịch vụ một cách phù hợp. Nếu việc loại bỏ một khu vực khiến dịch vụ không thể thực hiện đúng tính chất ban đầu, kỹ thuật viên hoặc cửa hàng có thể đề xuất một dịch vụ khác.

# Đau hoặc khó chịu trong quá trình massage

Khách nên báo ngay cho kỹ thuật viên nếu cảm thấy đau quá mức, khó chịu, chóng mặt, buồn nôn hoặc có bất kỳ phản ứng bất thường nào trong quá trình sử dụng dịch vụ. Khách có quyền yêu cầu giảm lực, thay đổi thao tác, tạm dừng hoặc kết thúc dịch vụ mà không cần tiếp tục chịu đựng cảm giác không thoải mái.

# Quyền dừng dịch vụ

Khách có quyền yêu cầu dừng dịch vụ vào bất kỳ thời điểm nào nếu cảm thấy không an toàn hoặc không thoải mái. Tương tự, kỹ thuật viên cũng có quyền tạm dừng hoặc kết thúc dịch vụ nếu nhận thấy tình huống không an toàn, khách có hành vi không phù hợp hoặc yêu cầu vượt ngoài phạm vi chuyên môn.

# Hành vi không phù hợp

Mọi hành vi quấy rối, đe dọa, xúc phạm, bạo lực hoặc yêu cầu mang tính tình dục đối với kỹ thuật viên và nhân viên đều không được chấp nhận. Cửa hàng có quyền ngừng dịch vụ ngay lập tức, yêu cầu khách rời khỏi cơ sở hoặc thực hiện các biện pháp bảo vệ nhân viên nếu xảy ra hành vi nghiêm trọng.

# Phạm vi dịch vụ massage

Dịch vụ massage được cung cấp với mục đích thư giãn, chăm sóc cơ thể hoặc hỗ trợ cảm giác thoải mái theo phạm vi dịch vụ của cửa hàng. Chatbot không được mô tả massage như một phương pháp chữa khỏi bệnh hoặc thay thế cho điều trị y tế. Những vấn đề sức khỏe cần chẩn đoán hoặc điều trị phải được xử lý bởi chuyên gia y tế phù hợp.

# Sau khi sử dụng dịch vụ

Sau khi hoàn thành massage, khách nên đứng dậy từ từ và nghỉ trong thời gian ngắn nếu cảm thấy cơ thể cần thích nghi. Khách có thể uống nước theo nhu cầu cá nhân. Nếu xuất hiện các triệu chứng bất thường, đau dữ dội, khó thở, chóng mặt kéo dài hoặc vấn đề sức khỏe đáng lo ngại, khách cần tìm hỗ trợ chuyên môn thích hợp thay vì chỉ hỏi chatbot.

# Vệ sinh phòng dịch vụ

Cửa hàng có trách nhiệm xây dựng quy trình vệ sinh đối với phòng, giường, khăn, dụng cụ và bề mặt sử dụng trong quá trình phục vụ. Tiêu chuẩn chi tiết phụ thuộc quy định vận hành của từng cơ sở. Chatbot không nên tự đưa ra các tuyên bố như “khử khuẩn tuyệt đối” hoặc “100 phần trăm vô trùng” nếu cửa hàng chưa cung cấp tiêu chuẩn chính thức.

# Khách dưới 18 tuổi

Khách chưa đủ 18 tuổi có thể cần sự đồng ý hoặc sự có mặt của cha mẹ hoặc người giám hộ tùy loại dịch vụ và chính sách cửa hàng. Vì dữ liệu mẫu chưa quy định độ tuổi tối thiểu cho từng dịch vụ, chatbot không nên tự xác nhận rằng người chưa thành niên chắc chắn được phép sử dụng dịch vụ.

# Trẻ em đi cùng khách

Không phải mọi chi nhánh đều có khu vực phù hợp để trẻ em chờ hoặc có nhân viên hỗ trợ trông trẻ. Nếu khách dự định đưa trẻ nhỏ đi cùng, khách nên liên hệ cửa hàng trước qua số 1900 8095 để xác nhận. Chatbot không được mặc định rằng nhân viên cửa hàng có trách nhiệm giám sát trẻ trong khi khách đang sử dụng dịch vụ.

# Khả năng tiếp cận cho người khuyết tật

Khả năng sử dụng xe lăn, thang máy, phòng ở tầng trệt hoặc các hỗ trợ tiếp cận khác phụ thuộc cơ sở vật chất của từng chi nhánh. Khi chưa có dữ liệu chính thức, chatbot nên hướng dẫn khách liên hệ chi nhánh qua số 1900 8095 để xác nhận trước khi đến, đặc biệt nếu khách cần hỗ trợ cụ thể.

# Bãi đậu xe

Thông tin về bãi đậu ô tô, khu vực để xe máy, chi phí gửi xe hoặc giới hạn thời gian đậu xe phụ thuộc từng chi nhánh và khu vực xung quanh. Nếu hệ thống chưa lưu thông tin chính thức, chatbot không được tự khẳng định rằng cửa hàng có bãi xe miễn phí hoặc có chỗ đậu xe.

# Địa chỉ cửa hàng

Địa chỉ của mỗi chi nhánh phải được lấy từ nguồn dữ liệu chính thức như POS hoặc cơ sở dữ liệu chi nhánh. Chatbot không được tự tạo địa chỉ dựa trên tên cửa hàng hoặc thông tin không được xác nhận. Nếu có nhiều chi nhánh có tên gần giống nhau, chatbot nên giúp khách xác định đúng chi nhánh trước khi cung cấp địa chỉ.

# Lựa chọn chi nhánh

Chi nhánh là một thông tin quan trọng vì danh sách dịch vụ, giá, kỹ thuật viên và khung giờ có thể khác nhau giữa các địa điểm. Khi khách thay đổi chi nhánh trong quá trình đặt lịch, hệ thống phải kiểm tra lại các lựa chọn phụ thuộc thay vì giữ nguyên toàn bộ thông tin từ chi nhánh cũ.

# Thông tin liên hệ cửa hàng

Số điện thoại liên hệ cố định của cửa hàng là 1900 8095. Địa chỉ email hoặc kênh liên hệ khác của cửa hàng phải được lấy từ dữ liệu được xác nhận. Chatbot không được tự tạo một số điện thoại hoặc email dựa trên tên thương hiệu. Nếu chưa có thông tin liên hệ chính xác ngoài hotline này, chatbot nên nói rõ rằng dữ liệu hiện tại chưa đủ thay vì cung cấp thông tin suy đoán.

# Trường hợp cần liên hệ trực tiếp cửa hàng

Khách nên liên hệ trực tiếp cửa hàng qua số 1900 8095 khi cần hủy hoặc thay đổi booking đã tạo, đặt lịch cho nhóm lớn, yêu cầu hỗ trợ đặc biệt, xác nhận khả năng tiếp cận, hỏi về bãi đậu xe, giải quyết vấn đề thanh toán, khiếu nại dịch vụ, tìm đồ thất lạc hoặc xác minh những chính sách mà chatbot chưa có dữ liệu chính thức.

# Khiếu nại dịch vụ

Nếu khách không hài lòng với dịch vụ, kỹ thuật viên hoặc trải nghiệm tại cửa hàng, chatbot có thể tiếp nhận nội dung phản hồi nếu hệ thống hỗ trợ nhưng không được tự đưa ra quyết định về hoàn tiền hoặc bồi thường. Các trường hợp khiếu nại nên được chuyển đến cửa hàng hoặc bộ phận quản lý có thẩm quyền xử lý.

# Bồi thường cho khách hàng

Chatbot không có quyền tự hứa cung cấp dịch vụ miễn phí, voucher, hoàn tiền hoặc bất kỳ hình thức bồi thường nào cho khách. Những quyền lợi này chỉ có hiệu lực sau khi được cửa hàng hoặc bộ phận phụ trách xác nhận theo chính sách chính thức.

# Đồ thất lạc

Nếu khách để quên điện thoại, ví, trang sức hoặc vật dụng khác tại cửa hàng, chatbot nên hướng dẫn khách liên hệ chi nhánh qua số 1900 8095 càng sớm càng tốt và cung cấp các thông tin như ngày sử dụng dịch vụ, thời gian, tên booking hoặc mã booking. Chatbot không được xác nhận rằng vật dụng đã được tìm thấy nếu chưa có thông tin từ cửa hàng.

# Quyền từ chối phục vụ

Cửa hàng có quyền từ chối hoặc chấm dứt dịch vụ trong các trường hợp có nguy cơ ảnh hưởng đến an toàn, sức khỏe, vệ sinh hoặc môi trường làm việc, bao gồm khách có dấu hiệu bệnh truyền nhiễm, say xỉn nghiêm trọng, hành vi bạo lực, quấy rối hoặc yêu cầu vượt ngoài phạm vi dịch vụ hợp pháp và chuyên nghiệp.

# Bảo mật thông tin khách hàng

Chatbot chỉ nên thu thập những thông tin cần thiết để hỗ trợ khách và thực hiện booking, chẳng hạn tên, số điện thoại, dịch vụ, chi nhánh, ngày giờ và yêu cầu liên quan. Hệ thống không nên yêu cầu mật khẩu, mã OTP, thông tin thẻ thanh toán hoặc giấy tờ cá nhân không cần thiết cho nghiệp vụ đặt lịch.

# Bảo mật thông tin sức khỏe

Những thông tin về tình trạng sức khỏe, dị ứng hoặc chấn thương mà khách tự nguyện cung cấp cần được sử dụng trong phạm vi cần thiết để hỗ trợ yêu cầu hiện tại. Các dữ liệu nhạy cảm không nên xuất hiện đầy đủ trong log kỹ thuật nếu không thực sự cần thiết cho việc vận hành hoặc xử lý sự cố.

# Dữ liệu hội thoại

Trong phiên bản MVP, context của cuộc hội thoại có thể chỉ được lưu trong bộ nhớ của tiến trình backend. Vì vậy, context có thể bị mất khi server khởi động lại và có thể không được chia sẻ giữa nhiều instance backend nếu chưa có hệ thống lưu session tập trung.

# Tải lại trang trong khi đặt lịch

Nếu người dùng tải lại trang trong khi booking chưa được hoàn tất và hệ thống chưa triển khai lưu context bền vững, chatbot có thể không còn nhớ những thông tin như chi nhánh, dịch vụ hoặc thời gian đã chọn. Trong trường hợp đó, người dùng có thể phải cung cấp lại dữ liệu từ đầu.

# Cuộc hội thoại mới

Một conversation mới không nên tự động sử dụng dữ liệu booking chưa hoàn thành của một conversation cũ, trừ khi hệ thống có cơ chế khôi phục session rõ ràng. Điều này giúp tránh việc một yêu cầu mới vô tình sử dụng dữ liệu của một booking đã bỏ dở.

# Duy trì trạng thái trong cùng cuộc hội thoại

Trong cùng một conversation, chatbot nên ghi nhớ những thông tin booking hợp lệ mà khách đã cung cấp và không hỏi lại một cách không cần thiết. Ví dụ, nếu khách đã chọn chi nhánh và sau đó hỏi giờ mở cửa, sau khi trả lời câu hỏi chatbot vẫn nên tiếp tục booking từ bước còn thiếu thay vì bắt đầu lại.

# Câu hỏi thông tin trong khi đặt lịch

Nếu khách đang ở giữa luồng booking và hỏi một câu như “dịch vụ này kéo dài bao lâu?”, “có chỗ đậu xe không?” hoặc “có dùng dầu không?”, hệ thống nên xử lý đây là câu hỏi thông tin. Việc trả lời câu hỏi không nên tự động xóa dữ liệu booking, chuyển state hoặc gửi yêu cầu tạo booking đến POS.

# Tiếp tục booking sau khi trả lời câu hỏi

Sau khi trả lời một câu hỏi thông tin trong lúc khách đang đặt lịch, chatbot nên tiếp tục từ bước booking đang còn thiếu. Ví dụ, nếu trước đó hệ thống đang chờ khách chọn thời gian thì sau khi trả lời FAQ, chatbot có thể nhắc lại rằng khách vẫn cần chọn một khung giờ phù hợp.

# Cơ sở tri thức cho câu hỏi thường gặp

Các câu hỏi về chính sách, chuẩn bị trước dịch vụ, thanh toán, hủy lịch, đến trễ hoặc sức khỏe có thể được tìm kiếm từ cơ sở tri thức bằng hệ thống tìm kiếm ngữ nghĩa. Để chức năng này hoạt động, cơ sở dữ liệu vector, collection, tài liệu đã lập chỉ mục và mô hình embedding cần hoạt động bình thường.

# Không tìm thấy thông tin trong cơ sở tri thức

Nếu hệ thống không tìm thấy tài liệu đủ liên quan đến câu hỏi của khách, chatbot không nên tự sáng tạo một chính sách để lấp chỗ trống. Câu trả lời phù hợp là nói rằng hiện chưa có đủ thông tin chính thức và hướng dẫn khách liên hệ cửa hàng qua số 1900 8095 nếu vấn đề đó quan trọng.

# Kết quả tìm kiếm có độ tin cậy thấp

Nếu hệ thống tìm thấy tài liệu nhưng mức độ liên quan thấp hoặc câu hỏi có thể được hiểu theo nhiều cách, chatbot nên tránh khẳng định chắc chắn. Hệ thống có thể yêu cầu khách làm rõ hoặc trả lời dựa trên thông tin hiện có kèm thông báo rằng chính sách cần được xác nhận.

# Dữ liệu cơ sở tri thức bị mâu thuẫn

Nếu hai tài liệu trong cơ sở tri thức đưa ra quy định khác nhau về cùng một vấn đề, chatbot không nên tùy ý chọn một câu trả lời. Hệ thống nên ưu tiên tài liệu có phiên bản mới hơn hoặc có phạm vi áp dụng chính xác hơn, chẳng hạn chính sách riêng của chi nhánh được ưu tiên hơn quy định chung nếu metadata xác nhận điều đó.

# Ưu tiên dữ liệu hệ thống quản lý

Đối với những dữ liệu thay đổi theo thời gian thực như giá hiện tại, dịch vụ đang hoạt động, kỹ thuật viên, availability, trạng thái booking và mã booking, chatbot phải ưu tiên dữ liệu từ hệ thống quản lý hoặc POS. Cơ sở tri thức tĩnh chủ yếu dùng cho chính sách và hướng dẫn, không nên được dùng để thay thế dữ liệu giao dịch thời gian thực.

# Không tự tạo thông tin

Khi dữ liệu không tồn tại, chatbot không được tự tạo địa chỉ, mức giá, mã booking, tên kỹ thuật viên, khung giờ, chính sách hoàn tiền hoặc mức phí hủy. Việc trả lời “hiện chưa có thông tin chính thức” tốt hơn một câu trả lời nghe hợp lý nhưng không được nguồn dữ liệu xác nhận.

# Nhận diện ý định của khách

Hệ thống có thể sử dụng mô hình ngôn ngữ để nhận diện khách đang muốn đặt lịch, lựa chọn dịch vụ, lựa chọn chi nhánh, hỏi thông tin, xác nhận booking hoặc thay đổi dữ liệu. Tuy nhiên, kết quả nhận diện phải được backend kiểm tra cùng trạng thái hiện tại của cuộc hội thoại trước khi thực hiện những thao tác quan trọng.

# Trích xuất thông tin từ câu khách

Mô hình có thể trích xuất các thông tin như tên dịch vụ, ngày, thời gian, số lượng khách hoặc yêu cầu kỹ thuật viên từ câu nói tự nhiên của khách. Các thông tin này chỉ là dữ liệu được nhận diện từ ngôn ngữ và phải được đối chiếu với dữ liệu thực tế trước khi đưa vào booking.

# Đối chiếu dịch vụ

Nếu khách nói “tôi muốn massage aroma”, hệ thống có thể trích xuất tên dịch vụ là “Aroma Massage”, nhưng backend vẫn cần tìm trong danh sách dịch vụ của chi nhánh để lấy đúng mã dịch vụ. Mô hình ngôn ngữ không được tự sinh mã dịch vụ và dùng mã đó để gọi hệ thống quản lý.

# Tên dịch vụ gần giống nhau

Nếu một câu của khách có thể khớp với nhiều dịch vụ, chẳng hạn hai gói có tên gần giống nhau, chatbot nên đưa các lựa chọn để khách xác nhận thay vì tự chọn một dịch vụ. Việc tự chọn chỉ nên thực hiện khi hệ thống có mức tin cậy đủ cao và không tồn tại lựa chọn hợp lý khác.

# Ngày tháng bằng ngôn ngữ tự nhiên

Các câu như “ngày mai”, “thứ bảy này”, “cuối tuần” hoặc “tuần sau” phải được chuyển thành ngày cụ thể dựa trên ngày hiện tại và múi giờ của hệ thống. Trước khi tạo booking, ngày đã chuyển đổi cần được kiểm tra để bảo đảm không nằm trong quá khứ.

# Thời gian bằng ngôn ngữ tự nhiên

Các cụm như “khoảng 3 giờ”, “buổi chiều”, “sau giờ làm” chỉ thể hiện mong muốn của khách và không phải một khung giờ booking chính thức. Chatbot cần kiểm tra những slot thực tế còn trống và để khách lựa chọn thời gian cụ thể nếu cần.

# Bắt đầu booking khi chưa có context

Nếu conversation hiện tại chưa có booking context, một câu đơn lẻ như “Aroma Massage” không phải lúc nào cũng đủ để kết luận khách đang tiếp tục một flow đặt lịch. Hệ thống cần dựa vào nội dung câu hiện tại và intent để quyết định có nên bắt đầu booking hoặc hỏi thêm thông tin.

# Xử lý khi đã có context

Nếu booking context hiện tại đang ở bước chờ khách chọn dịch vụ, câu “Aroma Massage” có thể được hiểu trực tiếp là lựa chọn dịch vụ. Điều này có nghĩa cùng một câu của người dùng có thể được xử lý khác nhau tùy theo trạng thái hiện tại của conversation.

# Câu chào của khách

Những câu đơn giản như “xin chào”, “hello”, “chào bạn” nên được nhận diện là lời chào và chatbot nên phản hồi thân thiện. Hệ thống không nên trả lời rằng “không hiểu yêu cầu” chỉ vì câu chào không chứa intent booking.

# Trò chuyện ngắn trong quá trình booking

Khách có thể gửi các câu xã giao hoặc phản hồi ngắn trong khi đang đặt lịch. Những message này không nên làm mất booking context. Sau khi phản hồi phù hợp, chatbot có thể tiếp tục yêu cầu trường còn thiếu tiếp theo.

# Xác nhận dữ liệu đã có

Nếu khách đã cung cấp một thông tin hợp lệ, chatbot không nên liên tục hỏi lại trường đó. Chỉ nên yêu cầu lại khi khách đã thay đổi dữ liệu liên quan, thông tin trước đó không còn hợp lệ hoặc booking context thực sự đã bị mất.

# Khách sửa thông tin

Nếu khách nói “không, tôi muốn 90 phút chứ không phải 60 phút”, hệ thống phải xem thông tin mới nhất là lựa chọn hiện tại. Vì thay đổi thời lượng có thể ảnh hưởng availability và giá, backend cần kiểm tra lại những dữ liệu phụ thuộc trước khi tiếp tục.

# Theo dõi luồng bằng mã truy vết

Mỗi request của chatbot nên có một mã truy vết để developer có thể theo dõi quá trình từ frontend đến backend, mô hình ngôn ngữ, hệ thống tìm kiếm knowledge và POS. Mã truy vết chỉ dành cho vận hành kỹ thuật và không phải mã booking của khách.

# Nhật ký hệ thống

Log hệ thống nên ghi lại những bước quan trọng như request được nhận, intent được phát hiện, entity được trích xuất, entity được đối chiếu, trạng thái booking thay đổi, quá trình tìm kiếm knowledge, lời gọi POS và kết quả cuối cùng. Cách ghi log có cấu trúc giúp developer xác định chính xác lỗi xảy ra ở bước nào.

# Bảo vệ dữ liệu trong log

Log không được chứa mật khẩu, khóa API, token truy cập, mã OTP hoặc đầy đủ thông tin thẻ thanh toán. Những thông tin cá nhân như số điện thoại cũng nên được che bớt khi ghi log. Mục tiêu của log là hỗ trợ debug chứ không phải lưu lại toàn bộ dữ liệu riêng tư của khách.

# Log kết quả mô hình ngôn ngữ

Để hỗ trợ kiểm tra luồng, backend có thể ghi lại kết quả có cấu trúc từ mô hình như intent, độ tin cậy và entity được nhận diện. Sau đó log có thể ghi thêm kết quả đã được backend đối chiếu như loại entity, mã thực tế và tên thực tế. Điều này giúp phân biệt rõ lỗi đến từ mô hình hay lỗi xảy ra trong quá trình xử lý backend.

# Log tìm kiếm cơ sở tri thức

Khi hệ thống tìm FAQ bằng cơ sở dữ liệu vector, log có thể lưu câu truy vấn, mã tài liệu được lấy về, điểm tương đồng và metadata cần thiết. Những thông tin này giúp developer đánh giá liệu chatbot trả lời sai vì retrieval lấy nhầm tài liệu hay vì mô hình diễn giải tài liệu không chính xác.

# Lỗi hệ thống quản lý lịch

Nếu POS hoặc hệ thống quản lý không phản hồi, chatbot không được nói rằng booking đã thành công. Hệ thống cần phân biệt các trường hợp như lỗi kết nối, timeout, lỗi dữ liệu đầu vào và lỗi nghiệp vụ để đưa ra hướng xử lý phù hợp.

# Timeout khi tạo booking

Nếu request tạo booking bị timeout, trạng thái cuối cùng có thể chưa rõ vì hệ thống bên ngoài có khả năng đã xử lý request nhưng response không quay lại kịp thời. Backend không nên ngay lập tức gửi lại cùng một request create nếu chưa có cơ chế chống trùng hoặc cách kiểm tra kết quả.

# Lỗi từ frontend

Một lỗi hiển thị trên giao diện không nhất thiết đồng nghĩa với backend hoặc POS đã thất bại. Khi kiểm tra sự cố cần dựa vào mã truy vết, request backend, response API và log của hành động tạo booking để xác định chính xác tầng nào xảy ra lỗi.

# Lỗi từ mô hình ngôn ngữ

Nếu mô hình trả về dữ liệu JSON không đúng cấu trúc hoặc một intent không thuộc danh sách được hỗ trợ, backend không nên sử dụng trực tiếp dữ liệu đó để điều khiển flow. Output từ mô hình cần được kiểm tra bằng schema và sử dụng fallback phù hợp khi validation thất bại.

# Mã định danh do mô hình tự tạo

Mô hình ngôn ngữ không được xem là nguồn đáng tin cậy để tạo ID của chi nhánh, dịch vụ, kỹ thuật viên, slot hoặc booking. Những ID được gửi đến POS phải đến từ cơ sở dữ liệu hoặc API chính thức sau khi backend đối chiếu entity.

# Phạm vi chatbot

Phiên bản MVP hiện tại chủ yếu hỗ trợ trả lời câu hỏi từ cơ sở tri thức và tạo booking mới. Các chức năng như tra cứu booking đã tạo, hủy lịch, đổi lịch, thanh toán, hoàn tiền hoặc xử lý khiếu nại đầy đủ có thể chưa được triển khai. Chatbot cần nói rõ giới hạn của mình thay vì giả vờ đã thực hiện được một chức năng chưa tồn tại.

# Tình huống y tế khẩn cấp

Chatbot đặt lịch massage không phải hệ thống hỗ trợ y tế khẩn cấp và không có khả năng chẩn đoán tình trạng sức khỏe. Nếu khách mô tả triệu chứng nghiêm trọng hoặc tình huống có thể cần chăm sóc y tế khẩn cấp, chatbot không nên cố gắng giải quyết bằng việc gợi ý một dịch vụ massage mà cần hướng khách tìm sự hỗ trợ y tế phù hợp.

# Không tư vấn điều trị

Chatbot không được kê thuốc, yêu cầu khách dừng thuốc, chẩn đoán nguyên nhân đau hoặc khẳng định massage có thể chữa một bệnh cụ thể. Với những câu hỏi sức khỏe vượt ngoài phạm vi thông tin chung về dịch vụ, chatbot nên giải thích giới hạn và khuyến nghị khách trao đổi với chuyên gia phù hợp.

# Quyền điều chỉnh chính sách

Cửa hàng có thể thay đổi giờ hoạt động, mức giá, danh sách dịch vụ, điều kiện hủy lịch, quy định đặt cọc và các chính sách vận hành khi cần. Vì vậy, tài liệu knowledge nên được cập nhật định kỳ và có ngày hiệu lực hoặc phiên bản để hệ thống có thể xác định nội dung nào đang được sử dụng.

# Chính sách riêng theo chi nhánh

Một số quy định có thể chỉ áp dụng cho một chi nhánh cụ thể, chẳng hạn giờ hoạt động, bãi đậu xe, giá, phương thức thanh toán hoặc dịch vụ đang cung cấp. Các đoạn knowledge dạng này nên được gắn metadata chi nhánh để hệ thống tìm kiếm không lấy chính sách của địa điểm này để trả lời câu hỏi về địa điểm khác.

# Cập nhật cơ sở tri thức

Khi cửa hàng thay đổi chính sách, tài liệu nguồn cần được cập nhật và đưa lại vào hệ thống tìm kiếm. Nếu knowledge sử dụng cơ sở dữ liệu vector, nội dung mới hoặc đã sửa cần được lập chỉ mục lại để chatbot có thể tìm thấy phiên bản hiện tại.

# Thay đổi mô hình embedding

Nếu hệ thống chuyển sang một mô hình embedding khác có kích thước vector hoặc đặc tính biểu diễn khác, dữ liệu vector cũ có thể không còn tương thích. Trong trường hợp đó, toàn bộ hoặc một phần tài liệu knowledge cần được tạo embedding và lập chỉ mục lại.

# Chất lượng tài liệu cho tìm kiếm ngữ nghĩa

Mỗi chính sách nên tập trung vào một chủ đề chính nhưng chứa đủ thông tin để trả lời nhiều cách hỏi khác nhau của khách. Không nên tạo hàng chục đoạn gần như giống nhau chỉ thay vài từ vì điều này có thể làm kết quả tìm kiếm bị nhiễu. Tiêu đề rõ ràng và nội dung đầy đủ giúp hệ thống embedding dễ phân biệt các chủ đề.

# Không trả lời chắc chắn khi thiếu dữ liệu

Một nguyên tắc quan trọng của chatbot là không biến thông tin chưa được xác nhận thành một quy định chính thức. Khi không tìm thấy giá, thời hạn hủy, phương thức thanh toán, bãi đậu xe, chính sách thai kỳ hoặc một thông tin quan trọng khác, chatbot nên nói rằng dữ liệu hiện tại chưa đủ và hướng dẫn khách liên hệ cửa hàng qua số 1900 8095.

# Minh bạch với người dùng

Chatbot nên phân biệt rõ giữa thông tin được hệ thống xác nhận, hướng dẫn mang tính tham khảo và thông tin chưa có trong cơ sở tri thức. Việc minh bạch giúp tránh trường hợp khách hiểu một câu trả lời do mô hình suy đoán thành cam kết chính thức của cửa hàng.

# Nguyên tắc không xác nhận sai

Chatbot chỉ được nói “đặt lịch thành công”, “đã thanh toán”, “đã hủy lịch”, “đã đổi lịch” hoặc những câu có ý nghĩa giao dịch tương tự khi hệ thống chịu trách nhiệm cho hành động đó đã xác nhận thành công. Nếu không có kết quả xác nhận, chatbot phải mô tả đúng trạng thái hiện tại thay vì đưa ra một kết luận thuận tiện.

# Nguyên tắc phục vụ cuối cùng

Chatbot có nhiệm vụ hỗ trợ khách tìm hiểu dịch vụ, thu thập thông tin đặt lịch, kiểm tra khả năng phục vụ và chuyển yêu cầu hợp lệ đến hệ thống quản lý. Quyết định cuối cùng liên quan đến khả năng tiếp nhận khách, yêu cầu sức khỏe đặc biệt, ngoại lệ chính sách, hoàn tiền, khiếu nại hoặc các trường hợp ngoài phạm vi hệ thống thuộc về cửa hàng và nhân sự có thẩm quyền.
