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
│   Tailwind CSS v4    │   + Alembic + pgvector │   + Qdrant + Groq   │
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

**Công nghệ:** FastAPI + Python 3.12 + Supabase (PostgreSQL) + Alembic + Groq

### Cấu trúc thư mục

```
app/
├── api/           # REST API endpoints (admin + public)
│   ├── admin/     # Shops, courses, therapists, shifts, bookings, restrictions
│   └── public/    # Shops, slots, eligibility, bookings, auth, therapist schedule
├── core/          # Config, auth, dependencies, Supabase client
├── db/            # SQLAlchemy models, migrations (Alembic)
├── integrations/  # Third-party integrations (POS removed)
├── modules/       # Business logic modules
└── rag/           # Legacy RAG (pgvector) — knowledge base search
    ├── chain.py
    ├── embeddings.py
    ├── ingestion.py
    ├── prompts.py
    ├── router.py
    └── vector_store.py
```

- **REST API:** Quản lý shops, courses, therapists, shifts, bookings, customer restrictions, auth
- **Database:** PostgreSQL qua SQLAlchemy, migration bằng Alembic
- **RAG (legacy):** Dùng pgvector trên PostgreSQL, sentence-transformers embedding, Groq LLM
- **POS:** Đã xóa hoàn toàn (RealPOSClient, router, tests)

### Biến môi trường

```env
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/postgres
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_KEY=<service_role_key>
SUPABASE_ANON_KEY=<anon_key>
GROQ_API_KEY=gsk-...
GROQ_MODEL=mixtral-8x7b-32768
GROQ_BASE_URL=https://api.groq.com/openai/v1
JWT_SECRET=...
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
CORS_ORIGINS=["http://localhost:3000"]
```

---

## Chatbot — `booking-ai-chatbot/`

**Công nghệ:** FastAPI + Python 3.12 + Qdrant + Groq + sentence-transformers

Dịch vụ AI riêng, xử lý hội thoại thông minh với RAG và intent routing.

### Cấu trúc thư mục

```
app/
├── main.py            # FastAPI app, lifespan, router mount
├── core/
│   ├── config.py      # Settings (GROQ_API_KEY, QDRANT_HOST, ...)
│   └── exceptions.py  # AppError base exception
├── integrations/
│   ├── groq.py        # Groq LLM client (OpenAI-compatible SDK)
│   ├── qdrant.py      # Qdrant async client (lifespan-managed)
│   └── booking_api.py # HTTP client gọi Booking Backend internal API
├── rag/               # RAG pipeline
│   ├── prompts.py     # System prompt template
│   ├── embeddings.py  # Sentence-transformers embedding (threadpool)
│   ├── vector_store.py# Qdrant operations (search, upsert, count, delete)
│   ├── ingestion.py   # Document chunking + embed + seed to Qdrant
│   ├── chain.py       # Retrieval + Groq generation
│   └── router.py      # /api/chat, /api/kb/seed, /api/kb/stats
└── tools/             # Intent classification + tool dispatch
    ├── intent.py      # classify_query, extract_params
    ├── faq.py         # FAQ answering (RAG-based)
    ├── shop.py        # Shop / course info search (gọi BE API)
    ├── slot.py        # Slot availability + eligibility (gọi BE API)
    ├── booking.py     # Booking CRUD với confirmation gate (gọi BE API)
    └── state.py       # Conversation state (in-memory, pending confirmations)
```

### Luồng xử lý chat

```
User query → classify_query() → intent dispatch:

  faq             → answer_faq() → embed → Qdrant search → Groq
  shop_info       → search_shop_info() → gọi BE API /api/public/shops
  course_info     → search_courses() → gọi BE API
  check_slot      → search_available_slots() → gọi BE API
  check_eligibility→ check_customer_eligibility() → gọi BE API
  create_booking  → initiate_create_booking() → confirmation gate → BE API
  cancel_booking  → initiate_cancel_booking() → confirmation gate → BE API
  update_booking  → initiate_update_booking() → confirmation gate → BE API
  lookup_booking  → lookup_customer_booking() → gọi BE API
  unknown         → fallback → answer_faq()
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
- **Auth:** Supabase Auth (email/password, OAuth, magic link)
- **Vector:** pgvector extension cho RAG legacy trên BE

Các bảng chính: `bookings`, `shops`, `courses`, `therapists`, `therapist_shifts`, `customer_restrictions`, `kb_chunks`

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
| Chatbot | `booking-ai-chatbot/Dockerfile` | python:3.12-slim |
| Frontend | `booking-ai-system-fe/Dockerfile` | node:22-alpine (multi-stage) |

### docker-compose.yml

```yaml
services:
  qdrant:        # image: qdrant/qdrant:latest, port 6333, volume qdrant_data
  backend:       # build ./booking-ai-system-be, port 8000
  chatbot:       # build ./booking-ai-chatbot, port 8001, depends_on: qdrant
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

- **Frontend:** Scaffolding ban đầu, chưa có code nghiệp vụ
- **Backend:** Hoàn chỉnh API booking + RAG legacy (pgvector), POS đã xóa
- **Chatbot:** Hoàn chỉnh RAG pipeline (Qdrant + Groq) + intent routing + tools
- **Tests:** Chatbot có 44 tests (integrations, RAG, tools, main)
