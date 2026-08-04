# Bộ câu hỏi kiểm thử chatbot booking

> Thay `[TÊN CỬA HÀNG]`, `[TÊN LIỆU TRÌNH]`, `[GIỜ]` bằng dữ liệu thật từ POS.

## 1. Chào hỏi

```text
xin chào
chào bạn
hello
hi Kori
alo
```

**Kỳ vọng:**

- Nhận diện `greeting`.
- Không gọi Gemini.
- Không thay đổi state booking.
- Trả lời chào tự nhiên.

---

## 2. Bắt đầu đặt lịch

```text
tôi muốn đặt lịch
tôi muốn đặt booking
book lịch giúp tôi
tôi muốn đặt chỗ
đặt hẹn cho tôi
tôi muốn đi massage
```

**Kỳ vọng:**

- Nhận diện `start_booking`.
- Gọi POS lấy danh sách cửa hàng.
- Chuyển sang `selecting_shop`.

---

## 3. Xem danh sách cửa hàng

```text
tôi muốn xem cửa hàng
có những cửa hàng nào
liệt kê cửa hàng cho tôi
Komorebi có những chi nhánh nào
cho tôi xem danh sách cơ sở
```

**Kỳ vọng:**

- Nhận diện `list_shops`.
- Gọi POS lấy dữ liệu thật.
- Không coi toàn bộ câu là tên cửa hàng.
- Không tự chọn cửa hàng.

---

## 4. Tìm và chọn cửa hàng

```text
có cửa hàng nào ở Huế không
tìm cửa hàng ở Quận 1
Komorebi Huế
tôi chọn Komorebi Quận 1
cửa ABC
```

**Kỳ vọng:**

- Câu hỏi theo khu vực: `search_shops`.
- Tên cửa hàng cụ thể: `select_shop`.
- `cửa ABC`: báo không tìm thấy và giữ nguyên state.

---

## 5. Chọn ngày

```text
hôm nay
ngày mai
ngày kia
thứ bảy tuần này
ngày 10 tháng 8
tôi muốn đặt vào ngày mai
```

**Kỳ vọng:**

- Chuẩn hóa đúng ngày.
- Không tự suy đoán sai múi giờ.
- Chuyển sang bước chọn số người.

### Ngày không hợp lệ

```text
hôm qua
ngày 32 tháng 8
một ngày nào đó
```

**Kỳ vọng:**

- Không cập nhật context sai.
- Yêu cầu người dùng nhập lại ngày rõ ràng.

---

## 6. Chọn số người

```text
1 người
hai người
đặt cho 3 người
mình đi cùng một người nữa
4 người
0 người
```

**Kỳ vọng:**

- Chấp nhận từ 1–3 người.
- `4 người`: báo tối đa 3 người.
- Giữ state `selecting_people`.
- Không trả lỗi kỹ thuật chung.
- Hiển thị quick replies `1 người`, `2 người`, `3 người`.

---

## 7. Chọn thời lượng

```text
60
60 phút
tôi muốn làm 90 phút
một tiếng
1 tiếng rưỡi
45 phút
```

**Kỳ vọng:**

- Ở bước thời lượng, trích xuất đúng số phút.
- Không gọi Gemini với dữ liệu số rõ ràng.

### Thời lượng không hợp lệ

```text
5 phút
500 phút
tôi chưa biết
```

**Kỳ vọng:**

- Không cập nhật context sai.
- Gợi ý các thời lượng hợp lệ.

---

## 8. Xem danh sách liệu trình và add-on

```text
có những liệu trình nào
liệt kê liệu trình chính cho tôi
cho tôi xem menu dịch vụ
có add-on nào
liệt kê liệu trình chính và add on
bạn cho tôi xem các lộ trình được không
```

**Kỳ vọng:**

- Nhận diện `list_services` hoặc `list_addons`.
- Gọi POS lấy catalog thật.
- Phân nhóm liệu trình chính và add-on.
- Giữ state `selecting_service`.
- Không gửi nguyên câu vào tìm kiếm tên liệu trình.

---

## 9. Chọn liệu trình

```text
Massage đá nóng 60 phút
tôi chọn massage đá nóng
cho tôi liệu trình thư giãn vai gáy
tôi chọn [TÊN LIỆU TRÌNH]
```

**Kỳ vọng:**

- Chọn đúng liệu trình.
- Lọc theo thời lượng đã chọn.
- Không nhầm bản 60 phút với 90 phút.

### Liệu trình không tồn tại

```text
tôi chọn liệu trình ABC XYZ
có dịch vụ bay lên mặt trăng không
```

**Kỳ vọng:**

- Không tự bịa dịch vụ.
- Báo không tìm thấy.
- Tiếp tục yêu cầu chọn liệu trình.

---

## 10. Xem và chọn khung giờ

```text
có những giờ nào trống
cho tôi xem lịch trống
còn slot nào hôm đó
khung giờ sớm nhất là mấy giờ
tôi chọn 08:00
đặt lúc 14 giờ
buổi chiều còn giờ nào
```

**Kỳ vọng:**

- Câu hỏi danh sách: gọi availability API.
- Câu chọn giờ: `select_time`.
- Chỉ trả các slot thật từ POS.

### Giờ không hợp lệ

```text
25:00
3 giờ sáng nếu cửa hàng không mở
tôi chọn 09:17
```

**Kỳ vọng:**

- Không nhận slot không tồn tại.
- Yêu cầu chọn lại từ danh sách hợp lệ.

---

## 11. Therapist

```text
có những kỹ thuật viên nào
hôm đó có therapist nào
tôi muốn kỹ thuật viên nữ
tôi chọn chị [TÊN THERAPIST]
không cần chỉ định
ai cũng được
```

**Kỳ vọng:**

- Phân biệt xem danh sách và chọn therapist.
- Không bịa therapist.
- Booking nhóm 2–3 người không yêu cầu therapist cá nhân nếu nghiệp vụ cấm.

---

## 12. Số điện thoại

```text
0901234567
090-123-4567
số của tôi là 0912345678
```

**Kỳ vọng:**

- Chuẩn hóa số điện thoại.
- Không hiển thị số đầy đủ trong log.
- Chuyển sang bước xác nhận số điện thoại.
- Nếu POS nhận diện khách hàng cũ, không hỏi lại tên.
- Nếu số điện thoại chưa có khách hàng, yêu cầu nhập tên trước khi xác nhận số.

### Số không hợp lệ

```text
123
abcdefgh
09012
```

**Kỳ vọng:**

- Không cập nhật context.
- Yêu cầu nhập lại số hợp lệ.

---

### Tên khách hàng mới

```text
Nguyễn Văn An
tên tôi là Nguyễn Văn An
```

**Kỳ vọng:**

- Chỉ hỏi tên khi số điện thoại chưa tồn tại trong POS.
- Không hỏi lại tên đối với khách hàng cũ.
- Sau khi nhận tên hợp lệ, chuyển sang xác nhận số điện thoại.

---

## 13. Xác nhận và từ chối

```text
đúng rồi
vâng
ok
đồng ý
xác nhận
không
chưa đúng
tôi không đồng ý
```

**Kỳ vọng:**

- Hiểu confirm/deny theo state hiện tại.
- Không dùng một câu “vâng” cho sai loại xác nhận.
- Final confirm chỉ tạo booking một lần.

---

## 14. Thay đổi thông tin giữa luồng

```text
tôi muốn đổi cửa hàng
đổi sang ngày mai
tôi muốn đổi thành 2 người
đổi thời lượng sang 90 phút
tôi muốn chọn liệu trình khác
đổi giờ sang 14:00
tôi muốn nhập lại số điện thoại
```

**Kỳ vọng:**

- Nhận diện `change_info`.
- Quay về đúng bước cần sửa.
- Không xóa những dữ liệu không liên quan.
- Kiểm tra availability lại khi ngày, giờ hoặc liệu trình thay đổi.

---

## 15. Nhiều thông tin trong một câu

```text
tôi muốn đặt ngày mai cho 2 người
đặt Komorebi Huế ngày mai lúc 14 giờ
tôi muốn massage đá nóng 60 phút vào chiều mai
đặt cho 2 người, 90 phút tại Komorebi Huế
```

**Kỳ vọng:**

- Nhận diện intent chính và các entity phụ.
- Không làm mất thông tin.
- Server vẫn điều khiển thứ tự flow.
- Không tự nhảy qua bước chưa được kiểm tra.

---

## 16. FAQ khi chưa booking

```text
cửa hàng mở cửa lúc mấy giờ
có chỗ đậu xe không
chính sách hủy lịch như thế nào
có dịch vụ cho phụ nữ mang thai không
giá liệu trình là bao nhiêu
```

**Kỳ vọng:**

- Trả lời từ knowledge/POS.
- Không tự bắt đầu booking.
- Không bịa thông tin khi Qdrant không có dữ liệu.

---

## 17. FAQ xen giữa booking

Trong lúc chatbot đang hỏi ngày hoặc liệu trình, nhập:

```text
cửa hàng có chỗ đậu xe không
tôi cần đến trước bao nhiêu phút
chính sách hủy lịch thế nào
```

**Kỳ vọng:**

- Trả lời FAQ.
- Không làm mất booking context.
- Sau khi trả lời, tiếp tục câu hỏi của state trước đó.

---

## 18. Câu cần Gemini xử lý

```text
tôi đang đau vai gáy nhưng chưa biết chọn liệu trình nào
tôi muốn thư giãn toàn thân thì nên chọn dịch vụ gì
tôi không biết diễn đạt, nhưng người tôi đang rất mỏi
bạn tư vấn liệu trình phù hợp cho người ngồi máy tính nhiều
```

**Kỳ vọng trong log:**

```text
provider=gemini
resolver=llm
LLMUsage started
LLMUsage completed
```

Có thể kèm:

```text
input_tokens=...
output_tokens=...
total_tokens=...
```

Không được còn:

```text
provider=gemini
llm_not_configured
```

---

## 19. Câu không liên quan

```text
hôm nay thời tiết thế nào
kể cho tôi một câu chuyện
giải bài toán này giúp tôi
ai là tổng thống Mỹ
```

**Kỳ vọng:**

- Nhận diện out-of-scope.
- Trả lời ngắn rằng chatbot hỗ trợ booking và thông tin dịch vụ.
- Không làm thay đổi booking context.

---

## 20. Hội thoại hoàn chỉnh một người

```text
xin chào
tôi muốn đặt booking
cho tôi xem danh sách cửa hàng
tôi chọn [TÊN CỬA HÀNG]
ngày mai
1 người
60 phút
cho tôi xem danh sách liệu trình
tôi chọn [TÊN LIỆU TRÌNH]
cho tôi xem giờ trống
tôi chọn [GIỜ]
không cần chỉ định therapist
0901234567
[TÊN KHÁCH HÀNG nếu là khách mới]
đúng rồi
xác nhận đặt lịch
```

**Kỳ vọng:**

- State cuối: `completed`.
- Status: `success`.
- `metadata.booking_created=true`.
- POS create đúng một lần.
- Không duplicate assistant message.
- Không hiển thị UUID nội bộ.
- Hiển thị mã booking do POS trả về khi tạo thành công.

---

## 21. Hội thoại booking nhóm

```text
tôi muốn đặt lịch
[TÊN CỬA HÀNG]
ngày mai
2 người
60 phút
[TÊN LIỆU TRÌNH]
[GIỜ]
0901234567
[TÊN KHÁCH HÀNG nếu là khách mới]
đúng rồi
xác nhận
```

**Kỳ vọng:**

- Chấp nhận 2–3 người.
- Không hỏi therapist cá nhân.
- Các booking cùng ngày, giờ và liệu trình.
- POS create không bị gọi lặp.

---

## 22. Kiểm tra retry và duplicate

Thực hiện:

```text
Nhấn nút gửi hai lần liên tiếp.
Nhấn quick reply hai lần.
Retry lượt xác nhận cuối.
Refresh trang giữa booking.
Bấm New Chat rồi bắt đầu lại.
```

**Kỳ vọng:**

- Double-click chỉ tạo một request.
- Retry cùng logical turn dùng lại idempotency key.
- Không tạo hai booking.
- New Chat tạo conversation ID mới.

---

# Checklist kết quả

```markdown
- [ ] Greeting hoạt động
- [ ] Booking synonyms hoạt động
- [ ] Liệt kê cửa hàng gọi POS
- [ ] Chọn cửa hàng hoạt động
- [ ] Ngày tương đối được hiểu đúng
- [ ] Chỉ chấp nhận 1–3 người
- [ ] Liệt kê liệu trình/add-on gọi POS
- [ ] Chọn đúng liệu trình theo duration
- [ ] Availability lấy từ POS
- [ ] Therapist đúng nghiệp vụ
- [ ] Phone validation hoạt động
- [ ] Change info hoạt động
- [ ] FAQ không làm mất booking state
- [ ] Gemini được gọi cho câu tự nhiên
- [ ] Deterministic intent không gọi Gemini
- [ ] Final booking chỉ tạo một lần
- [ ] Không HTTP 422
- [ ] Không traceback
- [ ] Không lộ phone/API key trong log
```
