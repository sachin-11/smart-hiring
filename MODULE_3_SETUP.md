# Module 3: JD Analyzer Agent + Matching Engine (Hybrid Search)

JD text → structured requirements + embedding → hybrid search (dense + BM25 + RRF + cross-encoder) → ranked, explained candidate matches.

## Folder Structure (naya/updated)

```
backend/app/
├── agents/
│   └── jd_analyzer.py          # JDAnalyzerAgent (GPT-4o structured output)
├── api/v1/routes/
│   ├── jobs.py                 # POST /jobs (create + synchronous JD analysis), GET /jobs/{id}
│   └── matching.py             # POST /match (hybrid search pipeline)
├── models/
│   └── job.py                  # updated: nice_to_have_skills, responsibilities, seniority_level
├── schemas/
│   ├── job.py                  # JDAnalysis, JobCreateRequest, JobDetailResponse
│   └── matching.py             # MatchRequest, MatchResult, MatchResponse
├── services/
│   └── matching_service.py     # dense search, BM25, RRF, cross-encoder, LLM explanations
alembic/versions/
└── 0003_jd_analysis_fields.py
frontend/
├── app/jobs/
│   ├── new/page.tsx            # JD creation form
│   └── [id]/matches/page.tsx   # ranked results, score bars, threshold filter
├── components/
│   ├── SkillTagInput.tsx       # tag input for required skills
│   └── ui/{input,textarea,label}.tsx
└── types/{job,matching}.ts
```

## Kya Setup Hua

### JD Creation → Analysis (synchronous, not backgrounded)
Module 2 ke resume upload ke ulat, `POST /api/v1/jobs` **synchronous** hai — job create hote hi usi request me `JDAnalyzerAgent` chal jaata hai (title/required_skills/nice_to_have/responsibilities/seniority_level extract) aur embedding generate ho jaati hai. Ye zaroori tha kyunki frontend "auto-trigger matching" turant next request me karta hai — agar background me hota to matching se pehle embedding ready hone ka guarantee nahi hota.

Flow: `jobs/new` form submit → `POST /jobs` (returns job with embedding + status=open) → redirect to `/jobs/{id}/matches` → us page pe mount hote hi `POST /match` call hota hai.

### Hybrid Search Pipeline (`matching_service.py`)

1. **Dense search** — pgvector cosine similarity (`Candidate.resume_embedding.cosine_distance()`), top-20
2. **Sparse search (BM25)** — `rank_bm25`, candidate pool (max 1000, completed parsing + resume_text) pe in-memory BM25Okapi index, JD text query, top-20
3. **Reciprocal Rank Fusion** — `rrf_score = Σ 1/(k + rank_i)`, k=60, dense aur sparse dono lists ka union, jo bhi candidate jis list me nahi hai uska us method se contribution 0
4. **Cross-encoder reranking** — `cross-encoder/ms-marco-MiniLM-L-6-v2` (sentence-transformers), RRF ke top `top_k` (default 10) ko JD-vs-resume_text pairs se rerank, logit ko sigmoid se 0-100% score me convert
5. **LLM explanations** — ek hi batched GPT-4o call se sabhi top candidates ke explanations (N alag calls ki jagah)

Dense aur sparse dono independent corpora pe chalte hain (dense = DB-wide ANN query via ivfflat index, sparse = bounded in-memory pool) — ye standard RRF practice hai, dono ko same pool tak seemit karna zaroori nahi.

### Heavy Dependency
`sentence-transformers` ke saath `torch` bhi aaya (~700MB). Cross-encoder model lazy-loaded singleton hai — pehli `/match` call pe model download+load hota hai (~30-50s), uske baad process ke jeevit rehne tak memory me cached rehta hai (fast, ~5-10s per call).

## Ek Known Limitation

LLM explanations sirf candidate ke `skills` array (structured data) dekhte hain, `resume_text` nahi — isliye kabhi-kabhi GPT-4o adjacent skills se galat inference kar leta hai (e.g. "Terraform, CI/CD" dekhkar "AWS experience" bol dena, jabki AWS explicitly listed nahi tha). Prompt me explicit "don't invent skills" instruction add ki, lekin poori tarah eliminate nahi hui — ye ek known LLM hallucination behavior hai. **`match_score`, `skill_overlap`, `missing_skills` sab structured/deterministic hain aur is issue se affected nahi** — sirf free-text `explanation` field occasionally over-confident ho sakta hai.

## Verification Kya Kiya

1. Sab naye modules import verify kiye.
2. Migration 0003 Neon pe chalaya — `jobs` table me `nice_to_have_skills`, `responsibilities`, `seniority_level` columns + enum confirm kiya.
3. **4 synthetic test candidates** seed kiye (real embeddings ke saath) — ek strong backend match, ek partial match, ek unrelated (sales), ek full-stack — taaki ranking discriminate kar sake ye verify ho.
4. Real HTTP server pe: `POST /jobs` (JD analysis confirm — skills/responsibilities/seniority sab sahi extract hue) → `POST /match` → ranking bilkul expected order me aaya (99.6% strong match → 70.9% partial → ...→ 0.3% unrelated).
5. Isi test ke dauraan ek REAL candidate ("Sachin Singh", user ka apna pehle se uploaded data) bhi results me aaya — confirm kiya ki cleanup sirf `(TEST)`-suffixed/synthetic emails delete kare, real data ko haath na lagaye.
6. Frontend build (`npm run build`) — clean, TypeScript pass.
7. **Full browser test** (Playwright): `/jobs/new` form fill (title, description, skill tags, min experience) → submit → auto-redirect to `/jobs/{id}/matches` → matches load ho ke ranked cards dikhe, color-coded progress bars (green/amber/red) sahi thresholds pe, skill overlap/missing badges, explanations, threshold slider — sab kaam kiya, koi console error nahi.
8. Sab test data (candidates + test job) cleanup kar diya.

## Local Run

```
http://localhost:3000/jobs/new
```

Note: `/match` ka pehla call slow ho sakta hai (cross-encoder cold start) — frontend isके liye 120s timeout use karta hai (default 30s ke bajaye), specifically us request ke liye.

## Aage Kya (Module 4+)

- Interview scheduling agent
- Candidate-side job search (reverse: candidate → matching jobs)
- Application pipeline (status tracking via existing `Application` model)
- Explanation quality improve karna (resume_text bhi context me dena, ya hallucination-resistant prompting)
