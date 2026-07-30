# Thông tin vận hành cửa hàng khách thường hỏi

Tài liệu này bổ sung các câu hỏi vận hành phổ biến. Với dữ liệu thay đổi theo thời gian, Kori phải kiểm tra API hoặc nói rõ chưa có thông tin xác nhận.

## Liên hệ cửa hàng bằng cách nào?

Số điện thoại và địa chỉ phải lấy từ cửa hàng đang hoạt động trong Booking API. Chatbot chưa có chức năng tự gọi điện, gửi SMS hoặc gửi email thay khách.

## Tôi có thể đến mà không đặt trước không?

Khách có thể hỏi cửa hàng về việc tiếp nhận trực tiếp, nhưng khả năng phục vụ phụ thuộc slot và nhân viên tại thời điểm đến. Đặt trước giúp giữ giờ; Kori không được cam kết khách walk-in chắc chắn được phục vụ.

## Tôi có thể chờ tại cửa hàng không?

Khu vực chờ và số người đi cùng phụ thuộc từng cửa hàng. Nếu API chưa có dữ liệu tiện ích, cần liên hệ cửa hàng để xác nhận.

## Có phòng riêng hoặc phòng cho cặp đôi không?

Chưa có trường dữ liệu phòng trong hệ thống. Không suy đoán dựa trên tên dịch vụ. Kori cần nói chưa có thông tin xác nhận theo từng cửa hàng.

## Có phòng tắm, khăn và quần áo thay không?

Tiện ích và vật dụng có thể khác theo dịch vụ/cửa hàng. Khách nên hỏi cửa hàng trước khi đến. Kori không được khẳng định có phòng tắm hoặc đồ thay nếu chưa có nguồn.

## Có chỗ gửi xe không?

Hệ thống hiện chưa quản lý bãi xe, mức phí hoặc giới hạn chiều cao. Cần xác nhận với đúng cửa hàng.

## Có hỗ trợ người dùng xe lăn không?

Khả năng tiếp cận phụ thuộc lối vào, thang máy và phòng dịch vụ. Khách nên liên hệ trước để cửa hàng chuẩn bị. Không được tự khẳng định mọi chi nhánh đều tiếp cận được.

## Có phục vụ trẻ em hoặc người chưa đủ tuổi không?

Có thể cần người giám hộ và phụ thuộc dịch vụ, độ tuổi cùng quy định cửa hàng. Kori không tự phê duyệt; cần xác nhận trực tiếp.

## Tôi có thể mang trẻ nhỏ hoặc thú cưng theo không?

Chưa có chính sách chung được cấu hình trong hệ thống. Khách cần hỏi cửa hàng trước để tránh ảnh hưởng không gian thư giãn và an toàn.

## Có yêu cầu im lặng không?

Khách nên giữ âm lượng phù hợp. Nếu muốn trò chuyện ít, phòng yên tĩnh hoặc có nhu cầu cảm giác đặc biệt, nên báo trước. Khả năng đáp ứng phụ thuộc cửa hàng.

## Tôi có được chọn kỹ thuật viên không?

Booking một người có thể chọn kỹ thuật viên cụ thể hoặc giới tính nếu workflow hiển thị lựa chọn và người đó còn rảnh. Booking nhóm được hệ thống tự phân công để tìm đủ nhân viên đồng thời. Không hứa một kỹ thuật viên khi availability chưa xác nhận.

## Kỹ thuật viên có nghỉ giữa hai khách không?

Có khoảng chuẩn bị giữa hai booking theo cấu hình cửa hàng, thường 5, 10 hoặc 15 phút trong dữ liệu demo. Ngoài ra nhân viên có thể nghỉ luân phiên. Chatbot chỉ nên giải thích nguyên tắc, không công bố lịch nghỉ cá nhân khi không có API public phù hợp.

## Có thể yêu cầu kỹ thuật viên nam hoặc nữ không?

Có thể nếu workflow hỗ trợ và còn nhân sự phù hợp. Đây là yêu cầu ưu tiên phụ thuộc availability, không phải cam kết trước khi booking được xác nhận.

## Có thể đổi kỹ thuật viên khi đến nơi không?

Cửa hàng chỉ có thể đổi nếu còn người phù hợp và không ảnh hưởng lịch. Kori không được đảm bảo việc đổi tại chỗ.

## Có thể thay đổi dịch vụ sau khi đặt không?

Update API hiện tập trung vào ngày và giờ. Nếu cần đổi dịch vụ, số người hoặc thông tin ngoài contract, khách nên liên hệ cửa hàng hoặc hủy/tạo booking mới theo hướng dẫn được xác nhận.

## Cửa hàng có bán thẻ quà tặng hoặc gói thành viên không?

Hệ thống chưa có catalog thẻ quà tặng hay quyền lợi thành viên công khai. Không tự tạo giá hoặc quyền lợi; cần hỏi cửa hàng.

## Có khuyến mãi không?

Chỉ thông báo chương trình có nguồn hiện hành. Nếu API/knowledge base không có chương trình với thời hạn rõ ràng, Kori phải nói chưa có thông tin khuyến mãi được xác nhận.

## Thanh toán bằng gì?

Phương thức thanh toán chưa được cấu hình theo cửa hàng trong API. Khách cần xác nhận nếu muốn dùng tiền mặt, thẻ, chuyển khoản hoặc ví điện tử cụ thể.

## Giá có bao gồm thuế và phụ phí không?

Giá dịch vụ hiện hành lấy từ Booking API. Thuế, phụ phí ngày lễ, phí hủy hoặc phụ phí phương thức thanh toán chưa có contract công khai; không tự khẳng định.

## Có xuất hóa đơn không?

Khách nên báo trước và cung cấp thông tin theo yêu cầu của cửa hàng. Chatbot không tự phát hành hóa đơn.

## Có giữ đồ giá trị không?

Khách nên hạn chế mang đồ giá trị và tự bảo quản. Tủ khóa/biên nhận tài sản phụ thuộc từng cửa hàng; cần xác nhận trước.

## Tôi bị dị ứng mùi hoặc dầu massage thì sao?

Khách phải thông báo trước khi bắt đầu. Không tự kết luận thành phần an toàn. Cửa hàng cần xác nhận sản phẩm và lựa chọn thay thế phù hợp.

## Tôi đang mang thai hoặc có bệnh nền thì sao?

Kori không chẩn đoán y khoa. Khách nên hỏi chuyên gia y tế và báo đầy đủ cho cửa hàng. Việc có phục vụ hay không phụ thuộc tình trạng, dịch vụ và đánh giá an toàn.

## Sau liệu trình tôi thấy khó chịu thì sao?

Nếu triệu chứng nghiêm trọng, bất thường hoặc kéo dài, cần tìm trợ giúp y tế. Với phản hồi dịch vụ, liên hệ cửa hàng và cung cấp mã booking; chatbot không thay thế xử lý khẩn cấp.

## Tôi muốn khiếu nại hoặc góp ý

Khách nên cung cấp mã booking, cửa hàng, thời gian và mô tả ngắn qua kênh chính thức. Không gửi thông tin tài chính, hồ sơ y tế chi tiết hoặc giấy tờ không cần thiết trong chat.

## Đồ thất lạc xử lý thế nào?

Liên hệ cửa hàng đã đến càng sớm càng tốt, cung cấp ngày giờ và mô tả đồ vật. Chatbot không thể xác nhận một món đồ đang được giữ nếu chưa có API quản lý đồ thất lạc.

## Cửa hàng đóng đột xuất thì sao?

Nếu slot hoặc cửa hàng không còn khả dụng, Kori phải thông báo đúng trạng thái và đề nghị chọn cửa hàng/giờ khác. Không được tự chuyển booking đã xác nhận sang nơi khác mà chưa có sự đồng ý của khách.

