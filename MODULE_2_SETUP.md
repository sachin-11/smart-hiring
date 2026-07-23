# Module 2: Resume Parser Agent

PDF/DOCX resume upload → LLM structured extraction → embeddings, end-to-end.

## Folder Structure (naya/updated)

```
backend/
├── app/
│   ├── agents/
│   │   └── resume_parser.py       # ResumeParserAgent (PyMuPDF/docx + GPT-4o structured output)
│   ├── api/v1/
│   │   ├── router.py              # api_router aggregator (naya)
│   │   └── routes/
│   │       └── resume.py          # upload / status / detail endpoints
│   ├── models/
│   │   └── candidate.py           # updated: parsing_status, education, experience, s3_key
│   ├── schemas/
│   │   └── resume.py              # ResumeData, ExperienceEntry, EducationEntry, API schemas
│   ├── services/
│   │   ├── s3_service.py          # boto3 upload (async via to_thread)
│   │   └── embedding_service.py   # OpenAI text-embedding-3-small
│   └── core/
│       └── database.py            # updated: db_enum() helper (bug fix, neeche dekho)
├── alembic/versions/
│   └── 0002_resume_parsing_fields.py
frontend/
├── app/upload/page.tsx            # dropzone + upload progress + status polling
├── components/
│   ├── ResumeCard.tsx             # parsed data display (skills/experience/education)
│   └── ui/{badge,card}.tsx        # shadcn components (v3-compatible rewrite)
└── types/resume.ts                # ResumeDetailResponse, ExperienceEntry, etc.
```

## Kya Setup Hua

### Backend Flow
1. **POST `/api/v1/resume/upload`** — PDF/DOCX accept karta hai (multipart), ek `Candidate` row `status=pending` ke saath turant create karta hai, aur `BackgroundTasks` me actual processing queue kar deta hai. Response turant milta hai (`candidate_id` + status) — upload block nahi hota.
2. **Background task** (`_process_resume`):
   - S3 pe file upload (`s3_service.py`)
   - `ResumeParserAgent.parse()` — PyMuPDF (PDF) / python-docx (DOCX) se text extract, phir LangChain + GPT-4o (`with_structured_output`) se `ResumeData` Pydantic model me structured JSON (name, email, phone, skills[], experience[], education[], total_years_exp)
   - `embedding_service.py` — OpenAI `text-embedding-3-small` se 1536-dim embedding, `candidates.resume_embedding` (pgvector) column me store
   - Candidate row update: `status=completed` (ya `failed` + error message agar kuch toota)
3. **GET `/api/v1/resume/{id}/status`** — frontend polling ke liye (pending/processing/completed/failed)
4. **GET `/api/v1/resume/{id}`** — full parsed data return karta hai

### Chunking Strategy
Resumes chhote documents hain (1-3 pages) — isliye full map-reduce chunking pipeline overkill hai. Iske bajaye `resume_parser.py` me ek simple bounded-truncation strategy hai: agar text `MAX_RESUME_CHARS` (12000) se lamba hai, to head ka 85% (contact info + recent experience) + tail ka 15% (aksar education) LLM ko bhejte hain.

### pgvector Index
Migration 0002 me `ivfflat` index bana:
```sql
CREATE INDEX ix_candidates_resume_embedding_ivfflat
ON candidates USING ivfflat (resume_embedding vector_cosine_ops) WITH (lists = 100)
```

## Ek Important Bug Mila Aur Fix Kiya

SQLAlchemy ka `Enum()` type by default Python enum ke **member name** (`"PENDING"`) DB ko bhejta hai, `.value` (`"pending"`) nahi — jab tak `values_callable` explicitly na diya jaye. Humare saare migrations lowercase values use karte hain, isliye bina fix ke koi bhi ORM insert (jaise default `CandidateStatus.NEW`) crash hota.

Fix: `app/core/database.py` me ek `db_enum()` helper add kiya jo `values_callable=lambda obj: [e.value for e in obj]` automatically laga deta hai. Sabhi 3 model files (`candidate.py`, `job.py`, `interview.py`) ke saare `Enum(...)` calls ko is helper se replace kiya.

## Frontend

- **`app/upload/page.tsx`** — `react-dropzone` se drag-and-drop, axios `onUploadProgress` se real upload % dikhata hai, phir `/status` endpoint ko har 2s poll karta hai (max 60 attempts, ~2 min timeout) jab tak `completed`/`failed` na aaye.
- **`components/ResumeCard.tsx`** — name, skills (badges), experience (timeline), education dikhata hai. "View Match Score" button disabled hai (future module ke liye placeholder).
- shadcn CLI ka latest version Tailwind v4-only syntax generate kar raha tha (`@base-ui/react` imports, `rounded-4xl`, `gap-(--card-spacing)`) jo humare pinned Tailwind v3 setup se incompatible tha — Badge aur Card components ko classic v3-compatible style me manually rewrite kiya.

## Verification Kya Kiya

1. **Backend imports** — sab naye modules (`agents`, `services`, `schemas`, `routes`) clean import hue.
2. **Live end-to-end smoke test** (synthetic PDF, real API calls):
   - PyMuPDF text extraction ✓
   - GPT-4o structured extraction — real resume text se name/email/phone/skills/experience/education/total_years_exp sab correctly nikla ✓
   - `text-embedding-3-small` se 1536-dim embedding ✓
   - DB insert (enum fix confirm — raw row me lowercase `'pending'`/`'completed'` aaya, `'PENDING'` nahi) ✓
3. **S3 bucket** `smart-hiring-uploads` (us-east-1) exist nahi karta tha — user confirm karne ke baad create kiya, upload verify kiya.
4. **Real HTTP test** — actual `uvicorn` server chalake curl se `/upload` → poll `/status` → `/{id}` detail fetch, sab real request-response cycle se pass hua.
5. **Migration 0002** Neon pe chalaya — `candidates` table me naye columns (`parsing_status`, `parsing_error`, `education`, `experience`, `s3_key`, `original_filename`) + `ivfflat` index confirm.
6. **Frontend build** (`npm run build`) — clean compile, TypeScript type-check pass.
7. **Browser test** (Playwright, headless Chromium) — `/upload` page real browser me drive kiya: idle → uploading (0%) → parsing → completed state, sab screenshots liye. Koi console error nahi. "View Match Score" button visible + disabled confirm kiya.
   - Isi test ke dauraan ek stale dev-server process port 3000 pe already chal raha tha jisse pehla test run unstyled page dikha raha tha (galat port hit ho raha tha) — cleanup karke dobara verify kiya, sab sahi.
8. Saara test data (candidate rows, S3 objects) cleanup kar diya — koi test data DB/S3 me nahi bacha.

## Local Run

Backend aur frontend Module 1 wale steps se hi start honge. Upload page yahan hai:

```
http://localhost:3000/upload
```

## Aage Kya (Module 3+)

- Job description parser + job-candidate matching (embeddings cosine similarity, `ivfflat` index yahi use karega)
- "View Match Score" button ko actual functionality dena
- Candidate list/search page (pgvector similarity search)
- Interview scheduling agent
