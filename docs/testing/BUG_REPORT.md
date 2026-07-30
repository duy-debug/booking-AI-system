# Booking AI System — Bug Report

Ngày kiểm thử: 2026-07-28  
Môi trường: Windows 11, Python 3.11, Node.js/Next.js local, Chromium Playwright  
Nguyên tắc: mọi dịch vụ ngoài được mock hoặc dùng local; không tạo booking production.

## Tổng quan

| ID | Severity | Thành phần | Tóm tắt | Trạng thái |
|---|---|---|---|---|
| QA-001 | High | Chatbot STT | Guardrail chấp nhận transcript rác/ngắn/lặp/hallucination tiếng Anh | Open |
| QA-002 | Medium | Chatbot STT | Blacklist theo substring từ chối câu hợp lệ | Open |
| QA-003 | High | Chatbot STT | Tin MIME header, không xác thực nội dung audio | Open |
| QA-004 | High | Chatbot SSE | Endpoint stream bỏ qua rate limit | Open |
| QA-005 | High | Chatbot STT | Endpoint audio bỏ qua rate limit | Open |
| QA-006 | Medium | Frontend SSE | Bỏ qua SSE event không có trường `event` | Open |
| QA-007 | Medium | Frontend SSE | `done` lặp gọi callback nhiều lần | Open |
| QA-008 | High | Repository security | Secret Groq cũ còn trong Git history | Open |
| QA-009 | Medium | Booking backend | Public lookup error không có `code` như contract test | Open |
| QA-010 | Medium | Booking backend | Public booking mapper giả định luôn có quan hệ `shop` | Open |
| QA-011 | Medium | Booking backend | Contract/test vẫn gọi `_compute_free_intervals` đã biến mất | Needs triage |
| QA-012 | High | Test infrastructure | Backend suite phụ thuộc Supabase thật/local và state theo thứ tự | Open |
| QA-013 | Medium | Configuration | `DEBUG=release` làm backend không import được | Open |
| QA-014 | Low | Admin frontend tests | Hai assertion mâu thuẫn cho nhóm 2→3 | Needs product decision |
| QA-015 | Low | Admin timeline tests | Vị trí label test `+5` lệch implementation `+25` | Needs UX decision |

## QA-001 — STT guardrail chấp nhận transcript không đáng tin cậy

- Môi trường: chatbot backend, Groq client mock.
- Preconditions: upload audio hợp lệ theo MIME; mock trả transcript.
- Steps:
  1. Gọi `POST /api/audio/transcriptions`.
  2. Cho upstream lần lượt trả `Thank you for watching`, `Subtitles by OpenSubtitles`, `!!! ... ???`, `a`, hoặc `xin chào` lặp 80 lần.
- Expected: trả 4xx với mã transcript không đáng tin cậy; không đưa text vào chat.
- Actual: trả 200 cho cả năm trường hợp.
- Tác động: im lặng/nhiễu có thể biến thành câu giả và khiến người dùng gửi sai ý định.
- Bằng chứng: `tests/test_audio_qa_security.py` — 5 test fail.
- Đề xuất sửa Phase 2: chuẩn hóa Unicode, kiểm tra tỷ lệ ký tự chữ/số, độ dài tối thiểu, repetition ratio, blacklist đa ngôn ngữ có ranh giới; giữ người dùng xác nhận trước khi gửi.

## QA-002 — Blacklist STT gây false positive

- Steps: mock transcript `Cảm ơn các bạn đã xem thông tin, tôi muốn đặt lịch ngày mai.`
- Expected: 200 vì câu chứa ý định hợp lệ.
- Actual: 422 vì substring blacklist.
- Tác động: mất nội dung hợp lệ, UX voice không ổn định.
- Bằng chứng: `test_legitimate_sentence_containing_partial_blacklist_phrase_is_allowed`.
- Đề xuất: chấm điểm toàn transcript/so khớp câu gần như hoàn toàn thay vì `substring in text`.

## QA-003 — MIME spoofing audio

- Steps: upload bytes `<script>alert(1)</script>` với `Content-Type: audio/webm`.
- Expected: 415 `INVALID_AUDIO_CONTENT`, không gọi Groq.
- Actual: request đi tới adapter và test nhận 502 từ upstream mock.
- Tác động: abuse chi phí/băng thông và xử lý dữ liệu không phải audio.
- Bằng chứng: `test_spoofed_audio_mime_is_rejected_before_upstream_call`.
- Đề xuất: kiểm tra magic bytes/container bằng parser an toàn, giới hạn thời lượng và giải mã trước upstream.

## QA-004 — Rate-limit bypass qua SSE

- Steps: đặt limit test là một request, gọi `/api/v1/chat/stream` hai lần cùng client.
- Expected: lần hai 429.
- Actual: lần hai 200.
- Tác động: bypass kiểm soát DoS/chi phí LLM bằng endpoint được UI dùng chính.
- Bằng chứng: `tests/test_security_qa.py::test_stream_endpoint_is_rate_limited`.
- Đề xuất: áp middleware/policy theo route group, không duy trì allowlist path thủ công.

## QA-005 — Rate-limit bypass qua audio

- Steps: gọi `/api/audio/transcriptions` hai lần cùng client với limit test bằng một.
- Expected: lần hai 429 trước upstream.
- Actual: request tiếp tục tới upstream (502 trong mock).
- Tác động: có thể tiêu thụ STT quota không giới hạn.
- Đề xuất: bucket riêng theo IP/session cho audio, giới hạn đồng thời, bytes và thời lượng.

## QA-006 — SSE chuẩn `message` bị bỏ qua

- Steps: server trả `data: {"delta":"Xin chào"}` không có dòng `event:`.
- Expected: SSE mặc định là event `message`, frontend nhận delta.
- Actual: không callback token nào được gọi.
- Tác động: UI chỉ hiện trạng thái ba chấm nếu proxy/upstream phát SSE mặc định.
- Bằng chứng: `services/chat-api.test.ts` fail.
- Đề xuất: mặc định tên event là `message` và parse payload theo schema tương thích.

## QA-007 — Duplicate `done`

- Steps: stream chứa hai event `done`.
- Expected: hoàn tất đúng một lần hoặc reject protocol.
- Actual: `onDone` gọi hai lần.
- Tác động: state/UI action có thể bị áp dụng trùng.
- Đề xuất: terminal-state guard; bỏ qua/reject mọi event sau terminal event.

## QA-008 — Groq key cũ còn trong Git history

- Steps: chạy tìm kiếm lịch sử chỉ theo mẫu, không in secret.
- Expected: không có commit chứa `gsk_`.
- Actual: tìm thấy commit `632a78e...` (2026-07-15) và `c96c163...` (2026-07-17).
- Tác động: secret có thể được khôi phục từ clone/history dù source hiện tại sạch.
- Đề xuất: revoke key trước; tạo key mới; dùng `git filter-repo` theo quy trình có backup/phối hợp team rồi force-push có kiểm soát. Không thực hiện trong Phase 1.

## QA-009 — `AppError` lệch contract public lookup

- Steps: lookup booking với ID/phone không khớp trong unit test.
- Expected: 404 và `code=BOOKING_NOT_FOUND_OR_PHONE_MISMATCH`.
- Actual: status 404 nhưng `AppError` không có thuộc tính `code`.
- Tác động: client không thể xử lý lỗi ổn định theo contract.
- Bằng chứng: `test_booking_lookup_service.py`.

## QA-010 — Mapper public booking phụ thuộc quan hệ `shop`

- Steps: gọi `get_public_detail` với booking test double hợp lệ theo contract cũ nhưng không eager-load `shop`.
- Expected: DTO public được tạo hoặc dependency được khai báo rõ.
- Actual: `AttributeError: ... has no attribute 'shop'`.
- Tác động: nguy cơ 500 nếu repository query không load relation.
- Bằng chứng: `test_query_services.py`.
- Đề xuất: xác nhận repository luôn eager-load và thêm integration test; mapper cần lỗi domain rõ ràng.

## QA-011 — Slot service contract đã lệch

- Actual: test gọi `_compute_free_intervals`, implementation không còn method.
- Tác động: chưa kết luận product regression; có thể là test stale sau refactor.
- Đề xuất: đối chiếu thuật toán mới bằng behavioral test public API thay vì private method.

## QA-012 — Backend suite không hermetic

- Actual: 121 error kết nối Supabase `[WinError 10061]`; bốn test booking sau đó fail vì dùng `BOOKING_ID` từ test tạo trước.
- Tác động: CI không phân biệt regression với hạ tầng; test order/state gây false failure.
- Đề xuất: disposable PostgreSQL/Supabase container hoặc repository mocks; mỗi test tự tạo fixture và rollback; integration marker rõ ràng.

## QA-013 — Giá trị `DEBUG` không hợp lệ làm ứng dụng chết lúc import

- Steps: chạy pytest trong môi trường hiện tại với `DEBUG=release`.
- Expected: cấu hình hợp lệ hoặc thông báo cấu hình sớm, rõ.
- Actual: Pydantic `bool_parsing` trước khi collect test.
- Đề xuất: dùng `APP_ENV=release` riêng, `DEBUG=false`; validate trong startup/deployment.

## QA-014 và QA-015 — Contract tests admin mâu thuẫn/stale

- `booking-form-contract.test.ts` vừa kỳ vọng `shouldAutoAssignTherapists(2,3)` là `true`, vừa là `false`.
- `CurrentTimeLine.test.ts` kỳ vọng `top: -HEADER_HEIGHT + 5`, source dùng `+25`.
- Tác động: pipeline đỏ dù chưa đủ bằng chứng product sai.
- Đề xuất: product owner chốt quy tắc reassign và vị trí label; thay source-string assertion bằng behavior/visual test.

