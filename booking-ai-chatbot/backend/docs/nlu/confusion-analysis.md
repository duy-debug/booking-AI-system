# Phân tích rủi ro nhầm intent

| Utterance | Intent A | Intent B | Nguyên nhân | Xử lý đề xuất |
|---|---|---|---|---|
| đặt ở Ba Đình | start_booking | select_shop | vừa khởi tạo vừa có shop | ưu tiên expected slot/state, giữ shop entity để áp dụng an toàn |
| cho xem Ba Đình | list_shops | select_shop | “xem” có thể hỏi danh sách hoặc chọn | candidate exact match + `SELECTING_SHOP`; nếu chưa có candidate thì hỏi lại |
| massage đá nóng giá bao nhiêu | select_service | faq | có tên service nhưng là câu hỏi giá | marker hỏi giá ưu tiên FAQ, không mutate |
| còn 7 giờ không | list_available_times | select_time | inquiry và selection gần nhau | dấu hỏi/còn không => list; selection chỉ khi slot mới nhất chứa giá trị |
| đổi sang ngày mai | select_date | change_info | cùng date entity | ngoài `SELECTING_DATE` dùng change_info; trong slot date dùng select_date |
| không đặt nữa | deny | cancel_flow | phủ định turn hay hủy flow | state confirmation => deny; state khác cần cancel_flow/clarification |
| đúng | confirm | confirmation nghiệp vụ | câu ngắn phụ thuộc state | state policy quyết định xác nhận phone hay booking |
| Ba Đình mở mấy giờ | select_shop | faq | shop entity không đồng nghĩa selection | FAQ marker không mutate shop |
| cái đó | unknown | out_of_scope | thiếu tham chiếu nhưng vẫn trong domain | unknown + clarification, không gán OOS |

Các intent chi tiết như `ask_price`, `ask_address`, `change_shop`, `confirm_booking` không được tạo thành label mới: runtime hiện gom chúng vào `faq`, `change_info`, `confirm` và phân giải bằng state. Lookup/cancel/reschedule booking chưa có intent contract tương ứng trong `Intent`; chỉ được ghi là nhu cầu deferred, không giả lập handler.
