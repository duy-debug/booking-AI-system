# Kiến trúc Booking AI System

## Tổng quan

Hệ thống gồm 2 thành phần chính: **Frontend** (Next.js) và **Backend** (FastAPI), giao tiếp qua REST API.

```
┌──────────────────────────────────────────────────────┐
│                   booking-ai-system                  │
├────────────────────────┬─────────────────────────────┤
│   Frontend (FE)        │   Backend (BE)              │
│   Next.js 16 + React19 │   FastAPI + Python 3.12     │
│   TypeScript           │   Supabase (PostgreSQL)     │
│   Tailwind CSS v4      │   + Alembic + OpenAI / RAG  │
│   Port 3000            │   Port 8000                 │
├────────────────────────┴─────────────────────────────┤
│   Docker: Backend container (root Dockerfile)         │
│   Docs: docs/architecture.md, api-design.md, db-design│
└──────────────────────────────────────────────────────┘
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

- `src/app/` — Định tuyến theo file (hiện có layout gốc và trang home mặc định)
- `src/components/` — Component dùng chung (chưa có)
- `src/features/` — Module theo tính năng (chưa có)
- `src/lib/` — Axios/fetch client, helpers (chưa có)
- `src/types/` — Định nghĩa types (chưa có)

### Supabase Client

File: `src/lib/supabase.ts` — dùng **anon key** (bị chặn bởi RLS).

### Biến môi trường

- `.env` — File cấu hình chính
- `.env.example` — File mẫu

```env
NEXT_PUBLIC_SUPABASE_URL=https://<project>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon_key>
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Backend — `booking-ai-system-be/`

**Công nghệ:** FastAPI + Python 3.12 + Supabase (PostgreSQL) + Alembic + OpenAI API

### Cấu trúc thư mục

```
app/
├── api/           # REST API endpoints
├── modules/       # Business logic modules
├── core/          # Config, security, dependencies
├── db/            # Models, repository, database session
├── integrations/  # Third-party integrations (OpenAI, ...)
└── rag/           # Retrieval Augmented Generation
```

- `app/api/` — Định nghĩa router và endpoint
- `app/modules/` — Logic nghiệp vụ theo module
- `app/core/` — Config, auth, logging, Supabase client (`supabase.py`)
- `app/db/` — SQLAlchemy models, migrations
- `app/integrations/` — Tích hợp OpenAI, Google Calendar, v.v.
- `app/rag/` — Xử lý tài liệu, vector search, LLM pipeline
- `alembic/` — Database migration scripts
- `documents/` — Dữ liệu đầu vào cho RAG
- `scripts/` — Utility scripts (seed data, import, ...)
- `infra/` — Infrastructure config (Docker, K8s, ...)

### Supabase Client

File: `app/core/supabase.py` — dùng **service key** (admin, vượt RLS).

### Biến môi trường

```env
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_KEY=<service_role_key>
SUPABASE_ANON_KEY=<anon_key>
DATABASE_URL=postgresql://<user>:<password>@<project>.supabase.co:5432/postgres
OPENAI_API_KEY=sk-...
```

---

## Docker

Dockerfile đặt tại root project:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY booking-ai-system-be/ .
RUN pip install -e .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build command: `docker build -t booking-ai-be .`

---

## Database

- **Nền tảng:** Supabase (PostgreSQL managed + Auth + Realtime + Storage)
- **Migration:** Alembic (cấu hình tại `alembic.ini`)
- **Kết nối trực tiếp DB:** `DATABASE_URL` dạng Supabase connection string (dùng cho Alembic/SQLAlchemy)
- **Client SDK (BE):** `supabase-py` với service key (admin)
- **Client SDK (FE):** `@supabase/supabase-js` với anon key (RLS)
- **Auth:** Supabase Auth (email/password, OAuth, magic link)
- **RLS:** Row Level Security — FE chỉ truy cập được dữ liệu được phép

---

## Giao tiếp FE ↔ BE

- **Giao thức:** HTTP REST
- **Base URL:** `http://localhost:8000` (BE)
- **FE gọi API qua:** `NEXT_PUBLIC_API_URL`
- **Định dạng:** JSON

---

## Trạng thái hiện tại

Dự án đang ở giai đoạn **scaffolding ban đầu**:

- Frontend: boilerplate từ `create-next-app`, chưa có code nghiệp vụ
- Backend: cấu trúc thư mục và config, chưa có source code Python
- Database: chưa có model hay migration
- Tài liệu: đang ở dạng placeholder
