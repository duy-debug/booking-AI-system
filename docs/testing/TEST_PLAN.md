# Booking AI System — Test Plan

## 1. Mục tiêu và phạm vi

Kế hoạch này kiểm thử repository tại thời điểm 2026-07-28, tập trung vào ba ứng dụng:

| Thành phần | Công nghệ xác nhận từ source | Vai trò |
|---|---|---|
| `booking-ai-chatbot/backend` | Python 3.11, FastAPI, Pydantic, Redis, Qdrant, OpenAI-compatible Groq client | NLU/orchestration, RAG, booking workflow, SSE, STT |
| `booking-ai-chatbot/frontend` | Next.js 16 App Router, React 19, TypeScript, Tailwind CSS 4 | Chat UI, SSE client, MediaRecorder/VAD, BFF proxy |
| `booking-ai-system-be` | FastAPI, SQLAlchemy 2, Alembic, PostgreSQL/Supabase | Booking, shop, course, therapist, schedule và admin API |
| `booking-ai-system-fe` | Next.js, React Query, Supabase Auth, Vitest | Admin UI và lịch làm việc |

Không gọi Groq, Qdrant, Redis, Supabase hoặc Booking API production. Integration/E2E sử dụng mock, test double hoặc local test service.

## 2. Kiến trúc được xác nhận

### Chat và SSE

1. `ChatApp.tsx` trim input, chặn gửi khi `loading`, tạo user/assistant placeholder.
2. Frontend gọi BFF `/api/chat/stream`.
3. Next route chuyển tiếp tới chatbot `/api/v1/chat/stream`.
4. `ConversationOrchestrator` phân loại intent và chọn handler.
5. Backend phát SSE `start`, `token`, tùy chọn `ui`, cuối cùng `done`; lỗi phát `error`.
6. Frontend `streamChat` parse từng block phân cách bởi dòng trống và ghép token.

### Microphone, VAD và STT

1. `MessageComposer` dùng `getUserMedia` và `MediaRecorder`.
2. VAD phía client dùng RMS threshold `0.025`, đếm tối thiểu 6 animation frames và yêu cầu bản ghi tối thiểu 700 ms.
3. Bản ghi tối đa 60 giây, sau đó upload qua BFF `/api/audio/transcriptions`.
4. Chatbot endpoint giới hạn 10 MB và allowlist MIME.
5. Groq OpenAI-compatible client gọi model cấu hình `whisper-large-v3-turbo`, `language="vi"`.
6. Guardrail backend reject transcript rỗng và một số chuỗi hallucination tiếng Việt.
7. Transcript chỉ điền vào textarea; người dùng phải chủ động gửi.

### Booking và tool policy

- Intent create/lookup/update/cancel đi qua các application flow riêng.
- Chỉ tool trong `PUBLIC_TOOLS` được phép thực thi.
- Mutation dùng pending action + confirmation token.
- Create dùng idempotency key ổn định; update/cancel chỉ chạy sau xác nhận.
- Chatbot gọi Booking Backend bằng service key tùy cấu hình.
- Booking Backend lưu PostgreSQL bằng SQLAlchemy; Alembic quản lý schema.
- Public lookup yêu cầu đồng thời UUID booking và số điện thoại.

### Authentication, logging và lỗi

- Admin API xác minh JWT Supabase và phân quyền; service-to-service có `X-Service-Key`.
- Public lookup bảo vệ ownership bằng booking ID + phone, chưa dùng OTP/session.
- Correlation ID được chuẩn hóa UUID và truyền sang Booking API.
- `AppError` được trả theo Problem Details; lỗi không mong đợi được log server-side và trả thông báo chung.
- Rate limit dùng Redis, hiện được khai báo cho một tập path cụ thể.

## 3. Risk assessment

| Rủi ro | Mức | Tác động | Ưu tiên test |
|---|---|---|---|
| Mutation không có confirmation/idempotency | Critical | Booking sai hoặc trùng | P0 |
| Sửa/hủy booking người khác | Critical | Vi phạm dữ liệu | P0 |
| SSE lỗi/duplicate token | High | Câu trả lời sai hoặc UI kẹt | P0 |
| Audio giả MIME/quá lớn | High | Abuse tài nguyên | P0 |
| Whisper hallucination khi im lặng | High | Ý định/booking sai | P0 |
| Rate-limit bypass qua SSE/audio | High | DoS/chi phí API | P0 |
| API key lộ frontend/log | Critical | Mất secret | P0 |
| Slot race condition | High | Double booking | P1 |
| VAD false positive/negative | Medium | UX/STT sai | P1 |
| Prompt/tool injection | High | Thao tác vượt quyền | P1 |
| Browser không hỗ trợ MediaRecorder | Medium | Mất voice input | P1 |
| Accessibility/mobile overflow | Medium | Không sử dụng được UI | P2 |

## 4. Test matrix

| Module | Unit | API | Integration | E2E | Security | Regression |
|---|---:|---:|---:|---:|---:|---:|
| Chat input/state | ✓ |  | ✓ | ✓ | XSS | ✓ |
| SSE parser/server | ✓ | ✓ | ✓ | ✓ | rate limit | ✓ |
| MediaRecorder/VAD | giới hạn |  | ✓ | giới hạn | permission | ✓ |
| STT/Groq adapter | ✓ mock | ✓ | ✓ mock | route mock | secret/MIME | ✓ |
| NLU/RAG/tool policy | ✓ | ✓ | ✓ mock | một phần | injection | ✓ |
| Booking workflow | ✓ | ✓ | ✓ mock | một phần | ownership/replay | ✓ |
| Booking persistence | ✓ | ✓ | cần DB test | chưa | SQL/mass assignment | ✓ |
| Admin auth/UI | hiện có | ✓ | cần Supabase local | chưa | JWT/RBAC | ✓ |

## 5. Functional cases

### Happy paths

- Text được trim, gửi một lần, token đúng thứ tự và kết thúc bằng `done`.
- General conversation dùng LLM; FAQ dùng RAG; booking intent dùng workflow.
- Audio tiếng Việt hợp lệ được transcript, hiển thị để sửa, không tự gửi.
- Create đủ shop/course/date/slot/customer tạo summary, chỉ mutation sau confirm.
- Lookup đúng UUID + phone trả booking detail.
- Update/hủy trả summary đầy đủ và chỉ thực thi sau token.

### Edge/failure cases

- Empty/whitespace/2.001 ký tự; double-click trong lúc loading; abort giữa stream.
- SSE malformed JSON, unnamed `message`, duplicate `done`, thiếu `done`, upstream error.
- Microphone denied/unsupported; blob rỗng; <700 ms; 60 giây; cleanup track.
- Im lặng đầu/cuối, speech ngắn, RMS thấp, quạt/bàn phím/nhạc nền.
- STT empty/special-only/short/repeated/English hallucination/bad schema/timeout/401/429/500.
- Booking thiếu từng entity; ngày quá khứ; slot unavailable; retry; concurrent slot.
- Booking/Redis/Qdrant/Groq timeout hoặc không sẵn sàng.

## 6. Security cases

- Prompt injection yêu cầu bỏ qua policy hoặc gọi admin tool.
- Tool name ngoài allowlist và payload sai kiểu/mass assignment.
- XSS/HTML/script trong message và transcript.
- Không có secret thật trong frontend bundle, `.env.example`, response hoặc log.
- Ownership lookup/update/cancel sai phone.
- Confirmation token sai/replay; idempotency retry.
- Rate limit JSON chat, SSE và audio.
- MIME spoofing, oversized upload, filename traversal; không nhận URL audio nên SSRF audio không áp dụng.
- CSRF: chatbot dùng JSON/multipart không cookie auth; admin Supabase bearer token cần kiểm tra riêng.

## 7. Performance và compatibility

- Đo time-to-first-token, tổng stream, 30 concurrent chat mocked, Redis/Qdrant timeout.
- Audio 10 MB boundary và 60 giây; memory không tăng sau nhiều lần record.
- Chromium desktop/mobile là E2E baseline.
- Firefox/WebKit cần kiểm tra MIME MediaRecorder (`webm`/`mp4`) và permission thủ công/CI có browser.
- `prefers-reduced-motion`, keyboard focus, responsive 320/375/768/1440 px.

## 8. Automation strategy và command

```powershell
# Chatbot backend
python -m ruff check app tests
python -m mypy app
python -m pytest -q
python -m pytest -m integration -q

# Chatbot frontend
npm run lint
npm run typecheck
npm test
npm run test:e2e
npm run build

# Booking Backend
python -m pytest -q

# Admin frontend
npm run lint
npm test
npm run build
```

Coverage chạy bằng `pytest-cov`/Vitest coverage nếu plugin tồn tại; không cài runtime dependency chỉ để tạo số coverage giả.

## 9. Phần chưa thể kiểm thử đầy đủ

- Groq/Whisper chất lượng thật, Qdrant retrieval và Redis durability: cấm gọi production; cần staging key và dataset được phê duyệt.
- Race condition PostgreSQL thật: cần disposable database/local Supabase; không dùng database hiện tại.
- Microphone noise corpus: repository chưa có WAV fixture chuẩn có nhãn.
- Browser permission và thiết bị vật lý: Playwright mock không thay thế hardware lab.
- Supabase JWT/RBAC integration: local auth service hiện chưa được xác nhận sẵn sàng.
- Calendar integration: source hiện dùng booking database, không thấy Google/Outlook Calendar adapter.
- SMS/email/call: không có adapter trong source và bị loại khỏi phạm vi an toàn.
