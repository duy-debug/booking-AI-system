# Kiến trúc Booking AI System

## Tổng quan

Hệ thống gồm 3 thành phần: **Frontend** (Next.js), **Backend** (FastAPI) và **Chatbot AI** (FastAPI service riêng). Giao tiếp qua REST API.

```
┌──────────────────────────────────────────────────────────────────────┐
│                         booking-ai-system                            │
├──────────────────────┬────────────────────────┬──────────────────────┤
│   Frontend (FE)      │   Backend (BE)         │   Chatbot (AI)       │
│   Next.js 16 + React │   FastAPI + Python 3.12│   FastAPI + Python   │
│   TypeScript         │   PostgreSQL / Supabase │   3.12               │
│   Tailwind CSS v4    │   + Alembic           │   + Qdrant + Groq   │
│   Port 3000          │   Port 8000            │   Port 8001          │
├──────────────────────┴────────────────────────┴──────────────────────┤
│   Docker: Backend container (root Dockerfile)                        │
│   Docs: docs/architecture.md, api-design.md, db-design.md            │
└──────────────────────────────────────────────────────────────────────┘
```

### Luồng giao tiếp

```
User → FE (Next.js) → BE (FastAPI) → PostgreSQL
                    → Chatbot (FastAPI) → Qdrant (vector DB)
                                        → Groq (LLM API)
                                        → BE (internal API)
```

---

## Frontend — `booking-ai-system-fe/`

**Công nghệ:** Next.js 16.2.10 (App Router) + React 19.2.4 + TypeScript 5 + Tailwind CSS v4

### Cấu trúc thư mục

```
src/
├── app/           # App Router pages (layout.tsx, page.tsx)
├── components/    # Shared UI components
├── features/      # Feature-based modules
├── lib/           # Utilities, helpers, API client
└── types/         # TypeScript type definitions
```

### Biến môi trường

```env
NEXT_PUBLIC_SUPABASE_URL=https://<project>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon_key>
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Backend — `booking-ai-system-be/`

**Công nghệ:** FastAPI + Python 3.12 + Supabase (PostgreSQL) + Alembic + PyJWT

### Cấu trúc thư mục (layered)

```
app/
├── main.py         # FastAPI entrypoint — routers, CORS, RFC 9457 exception handlers
├── api/           # REST API endpoints (routers — lớp mỏng, không thao tác DB)
│   ├── admin/     # /api/admin/* — Shops, courses, therapists, shifts, bookings, restrictions
│   ├── public/    # /api/* — Shops, slots, eligibility, bookings, auth, therapist schedule
│   └── deps.py    # get_db(), parse_uuid()
├── services/       # Business logic — SỞ HỮU transaction (commit/rollback/refresh)
├── repositories/   # Data-access mỏng — chỉ query + add/flush, KHÔNG commit
├── schemas/        # Pydantic request/response models
├── core/          # Config, auth (JWT), exceptions (RFC 9457), Supabase client
├── db/            # SQLAlchemy models, session, base
│   └── models/    # Shop, Course, Therapist, TherapistShift, Customer,
│                   # Booking, Reservation, ReservationCourse, CustomerRestriction
└── scripts/       # Seed dữ liệu mẫu (seed_data.py)
```

### Nguyên tắc phân lớp (layering)

1. **Routers (`api/`)** — mỏng: parse request → gọi Service → trả response.
   Không `session.add` / `commit` / `refresh` trực tiếp.
2. **Services (`services/`)** — sở hữu transaction:
   `try → repo.save → session.commit() → session.refresh() → except → session.rollback() → raise`.
   Chứa toàn bộ business validation (mã duy nhất, overlap ca làm việc, NG list…).
3. **Repositories (`repositories/`)** — chỉ truy vấn và `add`/`flush`; không `commit`/`rollback`.
4. **Admin vs Public** — `/api/admin/*` yêu cầu JWT; `/api/*` công khai.

- **REST API:** Quản lý shops, courses, therapists, shifts, bookings, customer restrictions, auth
- **Database:** PostgreSQL qua SQLAlchemy, migration bằng Alembic
- **RAG:** Đã **tách hoàn toàn** khỏi backend. Vector search (Qdrant + Groq) nằm trong
  service độc lập `booking-ai-chatbot/` (xem mục Chatbot). Backend không còn thư mục
  `app/rag/` hay `app/modules/`.
- **POS:** Đã xóa hoàn toàn (RealPOSClient, router, tests).
- **RAG schema:** Bảng `kb_chunks` + model `KnowledgeChunk` (phần dư RAG cũ) đã xoá
  qua migration `a3f7c9d2e1b0_remove_kb_chunks_table`.

### Xác thực (Supabase Auth — asymmetric / JWKS)

- Backend **không tự viết login**. Frontend login qua Supabase Auth, gửi access token vào
  header `Authorization: Bearer <supabase_jwt>`.
- Backend verify token bằng **public key từ JWKS** (`SUPABASE_JWKS_URL`), thuật toán `ES256`
  (ECC P-256 — Supabase mặc định). Không dùng shared secret.
- Quyền admin: email trong token phải nằm trong `ADMIN_EMAILS`, nếu không trả `403`.

### Biến môi trường

```env
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/postgres
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_KEY=<service_role_key>
SUPABASE_ANON_KEY=<anon_key>
SUPABASE_JWKS_URL=https://<project>.supabase.co/auth/v1/keys  # Verify token ECC/RS256
JWT_ALGORITHM=ES256
ADMIN_EMAILS=["admin@example.com"] # Whitelist email admin
CORS_ORIGINS=["http://localhost:3000"]
```

---

## Chatbot — `booking-ai-chatbot/backend/`

**Công nghệ:** FastAPI + Python 3.12 + Qdrant + Groq + sentence-transformers

Dịch vụ AI riêng, xử lý hội thoại thông minh với RAG và intent routing.

### Cấu trúc thư mục

```
app/
├── api/               # FastAPI router và Pydantic schema
├── application/       # Orchestrator, NLU, Intent Router, workflow
├── domain/            # Intent, entity, state và pending action
├── handlers/          # Information, booking, FAQ, general, clarification
├── policies/          # Input guard và public tool allowlist
├── tools/             # Read-only tools và mutation tools
├── integrations/      # Booking API, Redis, Groq và Qdrant
├── rag/               # Ingestion, embedding, retrieval và grounded response
├── core/              # Settings và exception
└── main.py            # Composition root và lifecycle
```

### Luồng xử lý chat

```
Chat API → Input Guard → Orchestrator → Structured NLU → Intent Router

  information → Information Handler → Read-only Tools → Public Booking API
  booking     → Booking Workflow → Confirmation Gate → Mutation Tools
  faq         → FAQ Handler → Qdrant → Groq
  general     → General Handler
  unknown     → Clarification Handler
```

### Biến môi trường

```env
GROQ_API_KEY=gsk-...
GROQ_MODEL=mixtral-8x7b-32768
GROQ_BASE_URL=https://api.groq.com/openai/v1
EMBED_MODEL_NAME=all-MiniLM-L6-v2
EMBED_DIM=384
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=kb_chunks
REDIS_URL=redis://localhost:6379/0
CONVERSATION_TTL_SECONDS=1800
BUSINESS_TIMEZONE=Asia/Tokyo
BOOKING_API_URL=http://localhost:8000
BOOKING_API_SERVICE_KEY=...
ADMIN_API_KEY=change-me-in-production
```

---

## Database

### PostgreSQL (Supabase) — BE sử dụng

- **Migration:** Alembic
- **Client BE:** SQLAlchemy + `supabase-py` (service key)
- **Client FE:** `@supabase/supabase-js` (anon key, RLS)
- **Auth:** Supabase Auth (email/password, OAuth, magic link) + JWT nội bộ cho Admin API
- **Vector:** pgvector extension — chỉ còn trong `kb_chunks` (legacy RAG, sẽ xoá).
  RAG thực tế giờ chạy trên **Qdrant** bên phía Chatbot, không phải PostgreSQL.

Các bảng chính: `bookings`, `shops`, `courses`, `therapists`, `therapist_shifts`,
`customer_restrictions`, `reservations`, `reservation_courses`

### Qdrant — Chatbot sử dụng

- Vector database chuyên dụng cho RAG của chatbot
- Collection: `kb_chunks` (cấu hình qua `QDRANT_COLLECTION`)
- Managed qua lifespan (init on startup, close on shutdown)

---

## Docker

Mỗi service có Dockerfile riêng, orchestrate bằng `docker-compose.yml` ở root.

### Dockerfiles

| Service | Dockerfile | Base image |
|---------|-----------|------------|
| Backend | `booking-ai-system-be/Dockerfile` | python:3.12-slim |
| Chatbot | `booking-ai-chatbot/backend/Dockerfile` | python:3.12-slim |
| Frontend | `booking-ai-system-fe/Dockerfile` | node:22-alpine (multi-stage) |

### docker-compose.yml

```yaml
services:
  qdrant:        # image: qdrant/qdrant:latest, port 6333, volume qdrant_data
  backend:       # build ./booking-ai-system-be, port 8000
  chatbot:       # build ./booking-ai-chatbot/backend, port 8001, depends_on: qdrant
  frontend:      # build ./booking-ai-system-fe, port 3000, depends_on: backend
```

### Khởi chạy

```bash
docker compose up -d
```

### Lưu ý

- Backend cần Supabase (PostgreSQL cloud) — cấu hình qua `.env`
- Chatbot dùng Qdrant trong compose — tự động khởi tạo
- Frontend dùng `output: "standalone"` (Next.js) — build arg `NEXT_PUBLIC_API_URL` trỏ đến BE

---

## Trạng thái hiện tại

- **Frontend:** Giao diện đặt lịch, tra cứu/huỷ booking, admin dashboard (shop/course/therapist/shift/restriction)
- **Backend:** Hoàn chỉnh API booking với kiến trúc phân lớp (api → services → repositories → db).
  Services sở hữu transaction; RAG và POS đã xóa khỏi backend.
- **Chatbot:** Hoàn chỉnh RAG pipeline (Qdrant + Groq) + intent routing + tools
- **Tests:**
  - Backend: **174 tests** (6 modules: services, admin_services, repositories, booking_flow, admin_flow, contract_public_fields)
  - Chatbot: 44 tests (integrations, RAG, tools, main)
