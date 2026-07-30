# Kiến trúc backend chatbot

Backend là modular monolith. Mỗi dependency chỉ được đi từ lớp ngoài vào lớp trong:

```text
api -> bootstrap -> application -> domain
                    |       ^
                    v       |
                 workflows -+
                    ^
                    |
             infrastructure
```

## Điểm bắt đầu đọc source

1. `app/main.py`: lifecycle, middleware, router và readiness.
2. `app/api/chat.py`: HTTP/SSE transport.
3. `app/bootstrap.py`: composition root duy nhất ghép concrete adapter.
4. `app/application/orchestrator.py`: điều phối một conversation turn.
5. `app/application/nlu.py`: chuẩn hóa intent và entity.
6. `app/workflows/`: state machine và nghiệp vụ booking.
7. `app/infrastructure/`: Redis, Booking API, Qdrant và OpenRouter.
8. `app/rag/`: ingestion, retrieval, evaluation và grounded generation.

## Trách nhiệm package

- `api`: chỉ xử lý transport, schema và SSE event.
- `application`: use case, routing, NLU và các port dạng `Protocol`.
- `domain`: state, intent và model không phụ thuộc framework/adapter.
- `workflows`: create, lookup, update và cancel booking.
- `infrastructure`: triển khai các port bằng dịch vụ bên ngoài.
- `rag`: bounded context truy xuất knowledge base.
- `core`: cấu hình và cross-cutting concern.
- `dialog`: schema/tool calling và quyết định route hội thoại.

## Quy tắc dependency

- `domain` không import `api`, `infrastructure` hoặc FastAPI.
- `application` phụ thuộc port, không phụ thuộc concrete Redis/HTTP client.
- `workflows` nhận dependency qua constructor.
- Chỉ `bootstrap.py` được phép tạo concrete adapter và ghép object graph.
- Mutation phải đi qua confirmation token và idempotency key.
- Lỗi provider không được tự ý advance booking state.

## Luồng một turn

```text
POST /api/v1/chat/stream
  -> ConversationOrchestrator
  -> input guard
  -> StructuredNLU / extract_intent
  -> DialogController
  -> handler hoặc booking workflow
  -> Redis state commit
  -> SSE token/ui/done hoặc error
```

## Luồng create booking

```text
idle
  -> shop
  -> main course
  -> add-on
  -> number of people
  -> date
  -> available slot
  -> therapist preference
  -> customer
  -> confirmation
  -> idempotent mutation
  -> completed
```

Flow configuration nằm cạnh implementation tại
`app/workflows/create/booking_flow.json`.
