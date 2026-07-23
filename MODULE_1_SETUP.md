# Module 1: Project Setup

Smart AI Hiring Platform ka initial scaffold — backend (FastAPI) + frontend (Next.js) + Docker infra.

## Folder Structure

```
smart-hiring/
├── backend/
│   ├── app/
│   │   ├── api/v1/routes/     # API route handlers (empty, Module 2+ me fill hoga)
│   │   ├── agents/            # LangGraph/LangChain agents (Module 2+)
│   │   ├── core/
│   │   │   ├── config.py      # Pydantic BaseSettings (env vars)
│   │   │   ├── database.py    # Async SQLAlchemy engine + pgvector setup
│   │   │   └── redis_client.py
│   │   ├── models/
│   │   │   ├── candidate.py   # Candidate model + resume_embedding (vector)
│   │   │   ├── job.py         # Job model + Application (join table)
│   │   │   └── interview.py   # Interview model
│   │   ├── schemas/           # Pydantic schemas (empty, Module 2+)
│   │   ├── services/          # Business logic (empty, Module 2+)
│   │   └── main.py            # FastAPI app, CORS, /health
│   ├── alembic/                # DB migrations (initial migration done)
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── frontend/
│   ├── app/                    # Next.js 14 App Router
│   ├── components/ui/          # shadcn/ui components
│   ├── lib/api.ts              # axios client
│   ├── types/index.ts          # shared TS types
│   ├── package.json
│   ├── .env.local.example
│   └── Dockerfile
└── docker-compose.yml           # postgres(pgvector) + redis + backend + frontend
```

## Kya Setup Hua

### Backend (FastAPI, async)
- **Config** (`app/core/config.py`) — `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, `GROQ_API_KEY`, `AWS_S3_BUCKET` etc. Pydantic `BaseSettings` se load hote hain `.env` se.
- **Database** (`app/core/database.py`) — async SQLAlchemy engine, startup pe `CREATE EXTENSION IF NOT EXISTS vector` chalta hai (pgvector).
- **Redis** (`app/core/redis_client.py`) — async connection pool.
- **Models**:
  - `Candidate` — resume text, skills, `resume_embedding` (1536-dim vector, OpenAI embeddings ke liye)
  - `Job` — description, required skills, `description_embedding` (matching ke liye)
  - `Application` — candidate ↔ job join table, match score
  - `Interview` — candidate + job se linked, AI score/feedback (JSON)
- **Alembic** — initial migration (`0001_initial_schema.py`) sabhi 4 tables + enums banata hai.
- **main.py** — CORS, global exception handler, structured logging, `/health` endpoint (DB + Redis dono check karta hai).

### Frontend (Next.js 14 + TypeScript + Tailwind + shadcn/ui)
- Next.js version **pinned to 14.2.35** (latest CLI 16 install kar raha tha, isliye explicitly `create-next-app@14` use kiya).
- shadcn/ui init kiya — but naya CLI Tailwind v4-style CSS generate karta hai jo humare Tailwind v3 setup se incompatible tha (`border-border`, `outline-ring/50` jaise classes tootrahe the). Manually `tailwind.config.ts` aur `globals.css` fix kiya taaki v3 ke saath kaam kare.
- `lib/api.ts` — axios client, `NEXT_PUBLIC_API_BASE_URL` se backend ko point karta hai, response interceptor error logging ke saath.
- `types/index.ts` — Candidate/Job/Interview ke TypeScript types (backend models se match karte hain).

### Docker
- `docker-compose.yml` — 4 services: `postgres` (pgvector/pgvector:pg16 image), `redis`, `backend`, `frontend`. Healthchecks lagaye hain taaki backend postgres/redis ready hone ke baad hi start ho.

## Verification Kya Kiya

- Backend: venv banake `pip install -r requirements.txt` — clean install, koi error nahi.
- `app.main`, `app.models`, `app.core.*` import karke check kiya — sab load ho raha hai, 4 tables (`candidates`, `jobs`, `applications`, `interviews`) metadata me registered hain.
- `alembic check` chalaya — env.py sahi se DB tak connect karne ki koshish karta hai (real Postgres na hone ki wajah se auth error aaya, jo expected hai — matlab config sahi hai).
- Frontend: `npm run build` — clean compile, static pages generate ho gaye.

## Local Run (Next Steps)

1. `backend/.env.example` ko `backend/.env` me copy karke apni keys daalo (OpenAI, Groq, AWS).
2. `frontend/.env.local.example` ko `frontend/.env.local` me copy karo.
3. `docker compose up --build` — sabhi 4 services start ho jayenge.
   - Backend: http://localhost:8000/health
   - Frontend: http://localhost:3000

## Aage Kya (Module 2+)

- `app/api/v1/routes/` me actual endpoints (candidates, jobs, interviews CRUD)
- `app/schemas/` me Pydantic request/response schemas
- `app/agents/` me LangGraph agents (resume screening, interview Q&A, matching)
- `app/services/` me business logic (embedding generation, S3 upload, scoring)
