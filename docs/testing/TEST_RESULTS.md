# Booking AI System — Test Results

Ngày chạy: 2026-07-28  
Phạm vi: Phase 1 — phân tích, bổ sung test, chạy test và báo cáo; chưa sửa product code.

## Kết luận release

**NO-GO cho production** tại snapshot hiện tại.

Lý do chính:

1. Endpoint SSE và audio chưa được rate limit.
2. STT nhận nhiều transcript rác và không xác thực nội dung audio.
3. Secret Groq cũ vẫn tồn tại trong Git history.
4. Backend nghiệp vụ chưa có suite integration hermetic; 121 test phụ thuộc Supabase không sẵn sàng.
5. SSE frontend có hai lỗi protocol đã tái hiện bằng unit test.

Frontend build và E2E chat mock đều pass, nhưng không bù được các lỗi security/integration trên.

## Kết quả theo thành phần

| Thành phần / lệnh | Kết quả | Chi tiết |
|---|---|---|
| Chatbot backend `ruff check app tests` | PASS | Không có lint error |
| Chatbot backend `mypy app` | BLOCKED | Windows Application Control chặn DLL khi import mypy |
| Chatbot backend `pytest -q` | FAIL | 92 pass, 10 fail, 2 skip |
| Chatbot backend `pytest -m integration -q` | PASS/SKIP | 2 skip, 102 deselected; không có local external stack |
| Chatbot frontend `npm run lint` | PASS | ESLint sạch |
| Chatbot frontend `npm run typecheck` | PASS | TypeScript sạch |
| Chatbot frontend `npm test` | FAIL | 8 pass, 2 fail |
| Chatbot frontend `npm run test:e2e` | PASS | 12/12 (6 case × desktop/mobile) |
| Chatbot frontend `npm run build` | PASS | Next production build thành công |
| Booking backend `pytest -q` | FAIL | 109 pass, 7 fail, 121 error |
| Booking backend `ruff check app tests` | FAIL | 152 lint errors |
| Booking backend `mypy app` | BLOCKED | Windows Application Control chặn DLL |
| Admin frontend `npm run lint` | PASS | ESLint sạch |
| Admin frontend `npm run typecheck` | PASS | TypeScript sạch |
| Admin frontend `npm test` | FAIL | 129 pass, 2 fail |
| Admin frontend `npm run build` | PASS | Next production build thành công |
| Hai frontend `npm audit --omit=dev` | PASS | 0 vulnerability production |
| Python dependency audit | NOT RUN | `pip-audit` chưa được cài |
| Current source secret pattern scan | PASS | Không thấy key Groq/OpenAI/AWS trong tracked source |
| Git history secret pattern scan | FAIL | Có hai commit lịch sử chứa mẫu `gsk_` |

## Chi tiết chatbot backend

10 failure gồm:

- 5 case transcript rác/ngắn/lặp được chấp nhận;
- 1 false-positive blacklist từ chối câu hợp lệ;
- 1 MIME spoof không bị chặn trước upstream;
- 1 RAG test phụ thuộc Redis thật dù phần RAG đã mock;
- 1 SSE rate-limit bypass;
- 1 audio rate-limit bypass.

Các case oversize, Groq model/language, error sanitization và luồng hiện có còn lại pass. Không có request production.

## Chi tiết chatbot frontend

Unit test xác nhận:

- PASS: stream token/done bình thường, error event, stream thiếu `done`, malformed JSON, abort, transcription route và chat route.
- FAIL: unnamed SSE `message` bị bỏ qua; duplicate `done` gọi callback hai lần.

E2E Playwright dùng route mock, không gọi backend/Groq:

- gửi và nhận nội dung streamed;
- Shift+Enter xuống dòng;
- lỗi stream có Retry;
- gửi ngay khi trang vừa mở;
- keyboard interaction;
- layout desktop và Pixel 7.

Tất cả 12 lượt pass. Cảnh báo còn lại: `next start` với `output: standalone`; không ảnh hưởng kết quả chạy local nhưng CI nên chạy standalone server đúng cách.

## Chi tiết booking backend

Lần chạy đầu chết khi import do `DEBUG=release` không parse được thành boolean. Lần chạy kiểm thử dùng override process-only `DEBUG=false`, không sửa `.env`.

Kết quả sau override:

- 109 pass;
- 7 fail;
- 121 error do Supabase local/auth không kết nối.

Failure độc lập:

- bốn test flow phụ thuộc `BOOKING_ID` từ test create trước đó;
- `AppError` thiếu `code` như contract test;
- public mapper cần `booking.shop`;
- test gọi private slot method đã biến mất.

Do database/auth integration không sẵn sàng, chưa xác minh được persistence, RBAC, race-condition slot và transaction rollback end-to-end.

## Chi tiết admin frontend

Build/lint/typecheck pass. Hai test fail đều cần quyết định contract:

- quy tắc auto-assign 2→3 tự mâu thuẫn ngay trong cùng test file;
- vị trí CurrentTimeLine kỳ vọng `+5`, implementation là `+25`.

Không chỉnh assertion để làm xanh giả.

## Coverage

Không công bố phần trăm coverage vì repository chưa có reporter đồng nhất và suite backend chính bị block bởi hạ tầng. Dùng số pass để suy ra coverage sẽ gây hiểu nhầm. Phase 2 nên thêm:

- `pytest-cov` với branch coverage cho hai backend;
- Vitest V8 coverage cho hai frontend;
- threshold ban đầu dựa trên baseline, tăng dần cho workflow mutation/security.

## File QA được bổ sung

- `docs/testing/TEST_PLAN.md`
- `docs/testing/BUG_REPORT.md`
- `docs/testing/TEST_RESULTS.md`
- `booking-ai-chatbot/backend/tests/test_audio_qa_security.py`
- `booking-ai-chatbot/backend/tests/test_security_qa.py`
- `booking-ai-chatbot/frontend/services/chat-api.test.ts`
- `booking-ai-chatbot/frontend/e2e/chat.spec.ts`
- `booking-ai-chatbot/frontend/playwright.config.ts`
- `booking-ai-chatbot/frontend/vitest.config.ts`

`@playwright/test` chỉ được thêm dưới `devDependencies`. Không sửa application/runtime source.

## Phần chưa kiểm thử được

- Groq/Whisper thật, Qdrant retrieval thật, Redis durability;
- PostgreSQL/Supabase persistence và auth/RBAC;
- microphone thật, noise corpus và browser permission;
- Firefox/WebKit MediaRecorder compatibility;
- concurrent booking race trên disposable DB;
- load test nhiều client và time-to-first-token;
- calendar/SMS/email vì source không có adapter tương ứng.

## Thứ tự đề xuất cho Phase 2

1. Revoke secret và làm sạch history có phối hợp.
2. Khóa rate limit SSE/audio và harden audio/STT validation.
3. Sửa parser/lifecycle SSE frontend.
4. Tách unit/integration backend; dựng disposable Supabase/Postgres.
5. Chốt OpenAPI/error contract và sửa mapper/query.
6. Chốt hai contract admin, sau đó thêm visual/behavioral test.
7. Bổ sung coverage, Firefox/WebKit và load/security CI.

