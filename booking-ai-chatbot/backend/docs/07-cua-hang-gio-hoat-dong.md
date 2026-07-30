# Cửa hàng, giờ hoạt động và lịch nhân viên

## Nguồn dữ liệu cần ưu tiên

Tên cửa hàng, địa chỉ, số điện thoại, dịch vụ đang bán, ca làm việc của kỹ thuật viên và slot còn trống là dữ liệu động. Khi khách hỏi về một cửa hàng hoặc một ngày cụ thể, Kori phải ưu tiên Booking API và dữ liệu slot hiện tại.

Tài liệu này mô tả chính sách vận hành chung và dữ liệu demo. Không dùng tài liệu để khẳng định một kỹ thuật viên chắc chắn đi làm hoặc một giờ chắc chắn còn chỗ.

## Giờ hoạt động trong môi trường demo

- Các cửa hàng Komorebi trong dữ liệu demo phục vụ từ **08:00 đến 22:00**, từ **thứ Hai đến thứ Bảy**.
- Dữ liệu demo không tạo ca kỹ thuật viên vào **Chủ nhật**, vì vậy hệ thống thường không hiển thị slot đặt lịch vào Chủ nhật.
- Giờ nhận khách cuối không mặc định là 22:00. Booking cuối phải kết thúc trước giờ hết ca và còn phụ thuộc thời lượng dịch vụ, add-on cùng khoảng nghỉ cần thiết.
- Ngày lễ, bảo trì, sự kiện nội bộ hoặc thay đổi đột xuất có thể làm giờ phục vụ khác lịch chung.

Đây là lịch mẫu phục vụ phát triển và kiểm thử. Khi triển khai thật, giờ mở cửa phải được quản trị theo từng cửa hàng và lấy từ API.

## Cửa hàng mở cửa lúc mấy giờ?

Trong dữ liệu demo, cửa hàng bắt đầu phục vụ lúc **08:00**. Nếu khách hỏi một ngày hoặc cửa hàng cụ thể, Kori cần kiểm tra slot của ngày đó. Có ca làm việc không đồng nghĩa mọi phút trong ca đều còn chỗ.

## Mấy giờ đóng cửa?

Trong dữ liệu demo, ca kết thúc lúc **22:00**. Khách không thể mặc định bắt đầu một liệu trình vào 22:00. Ví dụ, dịch vụ 60 phút cần bắt đầu đủ sớm để hoàn thành trước khi ca kết thúc và đáp ứng khoảng nghỉ vận hành.

## Kỹ thuật viên làm việc vào giờ nào?

Ca mẫu của kỹ thuật viên là **08:00–22:00, thứ Hai đến thứ Bảy**. Lịch thực tế có thể khác nhau theo người và theo ngày. Khi khách hỏi “hôm nay kỹ thuật viên nào đi làm?” hoặc “chị A làm ca mấy giờ?”, Kori phải dùng API lịch/availability; không suy đoán từ lịch chung.

## Nhân viên có nghỉ trưa không?

Hệ thống hiện không lưu một khung nghỉ trưa cố định áp dụng cho mọi kỹ thuật viên. Nhân viên nghỉ luân phiên theo lịch vận hành để cửa hàng vẫn phục vụ khách. Vì vậy Kori không được tự khẳng định tất cả nhân viên nghỉ từ 12:00 đến 13:00.

Nếu một khung giờ không xuất hiện, nguyên nhân có thể là nhân viên đang nghỉ, đã có booking, không đủ thời lượng hoặc không đủ số kỹ thuật viên cho nhóm.

## Khoảng nghỉ giữa hai khách

Mỗi cửa hàng cấu hình khoảng nghỉ giữa hai booking là **5, 10 hoặc 15 phút** trong dữ liệu demo. Thời gian này dùng để chuẩn bị phòng, vệ sinh dụng cụ, thay khăn và giúp kỹ thuật viên hồi phục. Đây không phải thời lượng massage và không tính thêm vào thời lượng khách đã mua.

Kori không cần công bố cấu hình nội bộ của từng cửa hàng nếu API public chưa cung cấp, nhưng có thể giải thích rằng khoảng nghỉ là một nguyên nhân khiến hai slot không thể đặt sát nhau.

## Chủ nhật và ngày lễ

- Dữ liệu demo nghỉ Chủ nhật.
- Lịch ngày lễ chưa có bảng cấu hình riêng trong API.
- Nếu khách hỏi ngày lễ có mở cửa không, Kori phải nói chưa thể xác nhận chỉ từ tài liệu và đề nghị kiểm tra slot hoặc liên hệ cửa hàng.
- Không được lấy lịch của năm trước để khẳng định lịch năm nay.

## Ngày lễ cửa hàng có mở cửa không?

Chưa có lịch ngày lễ chính thức trong Booking API. Kori không được tự khẳng định cửa hàng mở hoặc đóng vào một ngày lễ cụ thể. Cần kiểm tra slot của đúng ngày; nếu vẫn chưa đủ thông tin, đề nghị khách liên hệ cửa hàng.

## Giờ nhận khách cuối

Giờ nhận khách cuối được tính theo:

1. Giờ kết thúc ca của kỹ thuật viên.
2. Tổng thời lượng dịch vụ chính và add-on.
3. Khoảng nghỉ bắt buộc của cửa hàng.
4. Booking đã tồn tại.
5. Số người và số kỹ thuật viên cần phục vụ đồng thời.

Do đó không có một giờ nhận khách cuối duy nhất cho mọi dịch vụ. Kori nên yêu cầu khách chọn cửa hàng, dịch vụ và ngày để hệ thống trả slot chính xác.

## Đến sớm, đến muộn và không đến

- Khách nên đến sớm **10–15 phút**, đặc biệt trong lần đầu.
- Nếu đến muộn, cửa hàng có thể phải rút ngắn thời lượng để không ảnh hưởng khách tiếp theo.
- Kori không được hứa kéo dài giờ kết thúc hoặc hoàn tiền do khách đến muộn.
- Nếu không thể đến, khách nên đổi hoặc hủy sớm theo workflow thay vì bỏ lịch.
- Chính sách phí hủy/no-show chưa có trong Booking API; cần liên hệ cửa hàng nếu khách hỏi mức phí cụ thể.

## Đặt lịch trước bao lâu?

Khách nên đặt sớm, nhất là buổi tối, cuối tuần hoặc booking nhóm. Hệ thống chỉ xác nhận được giờ có thể đặt sau khi kiểm tra slot thời gian thực. Không có slot hiển thị nghĩa là hệ thống chưa tìm thấy tổ hợp phù hợp, không nhất thiết cửa hàng đã đóng cửa.

## Booking nhiều người

Booking nhóm cần đủ kỹ thuật viên rảnh đồng thời trong toàn bộ thời lượng. Hệ thống hiện hỗ trợ từ **1 đến 3 người** cho một booking. Nhóm từ 4 người trở lên cần chia thành nhiều booking hoặc liên hệ cửa hàng để được hỗ trợ riêng.

## Tra cứu địa chỉ và số điện thoại

Kori phải lấy tên, địa chỉ và số điện thoại hiện hành từ Booking API. Nếu khách chỉ nói khu vực, Kori nên hiển thị danh sách cửa hàng phù hợp để khách chọn, không tự chọn thay.

## Tiện ích tại cửa hàng

Các thông tin sau chưa có trường dữ liệu chuẩn trong Shop API và phải được xác nhận theo từng cửa hàng:

- Bãi đỗ ô tô hoặc xe máy.
- Thang máy, lối đi xe lăn.
- Phòng riêng, phòng đôi hoặc phòng cho nhóm.
- Phòng tắm, tủ khóa, khu thay đồ.
- Wi-Fi, ổ cắm, khu vực chờ.
- Phục vụ bằng ngôn ngữ khác.
- Cho phép trẻ em/người đi cùng chờ.
- Cho phép mang thú cưng.

Khi không có dữ liệu, Kori phải nói “hiện chưa có thông tin xác nhận” và cung cấp số điện thoại cửa hàng nếu API trả về.

## Múi giờ

Ngày và giờ phải được hiểu theo múi giờ cấu hình của cửa hàng. Không tự quy đổi theo múi giờ thiết bị nếu API đã cung cấp múi giờ kinh doanh. Nếu môi trường chưa có múi giờ theo từng shop, trợ lý phải dùng múi giờ triển khai và nói rõ khi khách ở quốc gia khác.
