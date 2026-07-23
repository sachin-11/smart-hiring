# Module 7: MLOps Pipeline + RAG Evaluation System

Production monitoring, evaluation, aur drift detection: RAGAS se candidate-lookup RAG flow ka real evaluation, PSI-based embedding drift detection, MLflow experiment tracking, Prometheus metrics, aur Redis cache-aside — sab real data pe verify kiya, koi mock nahi.

## Folder Structure (naya)

```
backend/app/
├── core/
│   └── cache_service.py         # Redis cache-aside: match results (1h), JD embeddings (24h)
├── models/
│   └── mlops.py                 # RagEvalLog, DriftReport tables
├── schemas/
│   └── analytics.py             # dashboard/trigger request-response models
├── services/
│   ├── monitoring.py            # Prometheus metrics + middleware
│   └── mlops/
│       ├── ragas_evaluator.py   # real embedding-retrieval RAG eval, scored by RAGAS
│       ├── drift_detector.py    # PSI on real resume embeddings (not Evidently — see below)
│       └── experiment_tracker.py # MLflow: prompt versions, match scores, pipeline cost
├── api/v1/routes/
│   └── analytics.py             # POST /mlops/ragas/run, /mlops/drift/run, GET /analytics/dashboard
frontend/
├── app/analytics/page.tsx       # admin dashboard: stat cards, RAGAS trend chart, alerts panel
└── types/analytics.ts
```

## Kya Setup Hua

### RAGAS Evaluation (`ragas_evaluator.py`)

Is app me koi traditional "RAG chatbot" nahi hai, isliye eval ke liye ek genuine, real RAG flow define kiya: **candidate skill-lookup** — question ("Which candidate has experience with Kubernetes?") → real pgvector embedding retrieval over resumes (wahi primitive jo `matching_service` Module 3 me use karta hai) → Groq se grounded answer generation → RAGAS se 4 metrics (faithfulness, answer_relevancy, context_precision, context_recall) score. Sample Q&A pairs runtime pe real DB candidates se banti hain (question = ek real skill unke resume se, reference = unki actual stored skills list) — koi fabricated eval set nahi.

**Real bug pakड़ा during dev**: pehla design "What skills does NAMED_PERSON have?" tha — retrieval isse consistently GALAT candidates retrieve kar raha tha (do purane, unrelated real candidates, jo apparently kisi bhi generic-phrasing question ke "closest" the), kyunki question ka embedding kisi specific NAME se match nahi karta, resume content se karta hai. `context_precision`/`context_recall` exactly 0.0 aa rahe the — RAGAS ne genuinely ek real retrieval-design flaw pakड़ liya. Fix: question ko skill-lookup shape me badla ("Which candidate has experience with X?") — ab retrieval correctly sahi candidate retrieve karta hai (verified: real skill query "Kubernetes and PostgreSQL" → top match Arjun Mehta, jiski exactly wahi skills hain).

Threshold: `faithfulness < 0.75` → alert (`RagEvalLog.alert_triggered`), Postgres `rag_eval_logs` table me store, MLflow me bhi log.

### Drift Detection (`drift_detector.py`) — **Evidently AI use nahi kiya**

Task ne Evidently AI bola tha, lekin ek real, verified dependency conflict mila: `evidently==0.7.21` unconditionally apna litestar-based UI server import karta hai (`from evidently import ui`, no try/except), aur litestar ka `multipart` dependency **exact same import namespace** occupy karta hai jo FastAPI ka `python-multipart` use karta hai. Dono ek saath install karne se `python-multipart` ki files overwrite ho gayi — **real test se confirm kiya ki isse resume upload (`POST /resume/upload`) tootne laga** (multipart form parsing fail). Yeh sirf theoretical concern nahi tha — maine actually dono install karke, real multipart POST request bhेजkar break hote dekha, phir `evidently`+`litestar`+`multipart` (standalone package) uninstall karke `python-multipart` reinstall kiya aur re-confirm kiya ki upload wapas kaam karta hai.

Isliye PSI (Population Stability Index) directly implement kiya (well-defined formula, koi framework nahi chahiye):
- Baseline: pehle N (default 100) candidates ke resume embeddings.
- Har embedding ko ek scalar me reduce kiya — baseline centroid se cosine similarity (standard embedding-drift technique, 1536-dim PSI directly nahi ho sakta).
- PSI: baseline ke deciles se bins banao, dono distributions (baseline vs current) ko un bins me histogram karo, standard PSI formula.
- `PSI > 0.2` → alert, `DriftReport` table me store, JSON report S3 pe (`mlops/drift-reports/{id}.json`), MLflow me bhi log.

**Real test**: 10 backend-engineering resumes ko baseline banaya, 3 marketing/design resumes ko "current" (deliberate domain shift) — PSI=**12.43** (threshold 0.2 se bohot upar), alert correctly trigger hua. Baseline candidates ki centroid-similarity mean ~0.80 thi, current ki ~0.51 — real, interpretable signal.

### MLflow (`experiment_tracker.py`)

`mlflow>=3` ne filesystem backend (`file:./mlruns`) ko maintenance mode me daal diya hai (write refuse karta hai bina `MLFLOW_ALLOW_FILE_STORE=true` ke) — isliye SQLite backend use kiya (`sqlite:///mlflow.db`), jo bhi modern default hai aur `mlflow.search_runs()` se query karne ke liye better hai (dashboard ko yehi chahiye). 4 experiments: pipeline runs (match_score + per-model cost), prompt versions (artifact), RAGAS evaluations, embedding drift. Sab sync MLflow calls `asyncio.to_thread` me wrapped hain (jaise boto3 already the).

### Prometheus (`monitoring.py`)

Sab 4 spec'd metrics: `hiring_pipeline_duration_seconds` (histogram, `routes/pipeline.py` me wrap kiya), `llm_token_usage_total` (counter, `llm_router.log_cost()` me wire kiya — jo already **har** LLM call se guzarta hai, isliye ek jagah instrument karne se poori app cover ho gayi), `match_score_distribution` (histogram, `/match` endpoint me), `api_request_total` (counter, ek generic `PrometheusMiddleware` sabhi requests ke liye — route ka path template label banta hai, raw UUID URLs nahi, taaki cardinality na phategi). `GET /metrics` real Prometheus text format return karta hai.

### Caching (`cache_service.py`)

Cache-aside pattern, do jagah:
- **Match results** (`POST /match`, 1hr TTL) — genuinely valuable, kyunki cross-encoder rerank is app ki sabse slow call hai (cold ~56s dekha). **Real measured speedup: 22.9x** (56.5s → 2.5s).
- **JD embeddings** (24hr TTL) — honestly kam value hai is specific codebase me, kyunki `Job.description_embedding` already Postgres column pe permanently stored hota hai (ek baar compute hoke), isliye "recompute" cost pehle se hi avoid ho chuka hai DB design se. Cache-aside PATTERN correctly demonstrate karta hai (check cache → miss → source of truth → populate cache), bas jis "source of truth" ko cache kar rahe hain wo already-cheap DB read hai, expensive embedding API call nahi. Real value tab milegi jab koi future caller sirf embedding chahiye bina poori Job row load kiye.

### Analytics Dashboard (`/analytics`)

Backend `GET /analytics/dashboard` sab real sources se aggregate karta hai: MLflow (pipeline run count + avg match score + cost), Redis (`llm_cost:total_usd`), Postgres (RAGAS trend — `rag_eval_logs` grouped by `run_id`; drift alerts — `drift_reports`; cost-per-hire — `total_cost / count(candidates where status=HIRED)`). Frontend: 4 stat cards, RAGAS trend line chart (recharts, 4 lines), unified "Recent Alerts" panel (drift + RAGAS alerts merged, sorted by time). Manual trigger buttons ("Run RAGAS Eval", "Run Drift Check") — real cron scheduler is stack me nahi hai (koi APScheduler/Celery-beat/system cron already setup nahi), isliye "weekly" job ko ek callable async function banaya jo manually (button) ya future me kisi scheduler se equally call ho sake.

## Design Decisions / Task Se Deviations

1. **Evidently AI use nahi kiya** — real verified dependency conflict jo file uploads todता (upar detail me). PSI directly implement kiya.
2. **"Weekly cron job" nahi hai** — is stack me koi scheduler infra nahi hai. `ragas_evaluator.run_evaluation()` aur `drift_detector.run_drift_check()` plain async functions hain, `POST /mlops/*/run` se manually (ya kisi future scheduler se) trigger ho sakte hain.
3. **MLflow SQLite backend, file store nahi** — `mlflow>=3` ne file store deprecate kar diya, real error mila, sqlite pe switch kiya.
4. **RAGAS eval questions skill-lookup hain, name-lookup nahi** — real bug (0.0 scores) dekhne ke baad redesign kiya, upar detail me.
5. **JD embedding caching ka value modest hai** is specific codebase me (upar explained) — phir bhi correctly wire kiya kyunki task ne explicitly maanga tha.
6. **`python-multipart` explicitly reinstalled** after evidently uninstall, taaki `multipart/` namespace ownership 100% confirm ho — verified via real multipart POST test, do baar.

## Verification Kya Kiya

Sab real APIs/services se (OpenAI, Groq, real S3, real Neon Postgres, real Redis, real MLflow SQLite) — koi mock nahi.

1. **Dependency conflict discovery aur fix** — `evidently`+`litestar` install karne ke baad real `POST /resume/upload` multipart test kiya → **genuinely tootа** (`ImportError: cannot import name 'MultipartSegment'`). Root cause trace kiya (`multipart` PyPI package `python-multipart` ki files overwrite kar raha tha). `evidently`+`litestar`+standalone `multipart` uninstall kiya, `python-multipart` explicitly reinstall kiya, **phir se real upload test kiya — confirm pass**. `pip check` clean.
2. **RAGAS end-to-end**: real 4-sample eval run kiya — pehle broken design se degenerate 0.0 scores mile (jo khud ek valid finding tha), redesign ke baad real, meaningful, varying scores mile (faithfulness=1.0, answer_relevancy 0-0.58 range, precision~1.0, recall 0/1 mix) — DB rows manually inspect kiye, retrieval aur generation dono sahi kaam kar rahe the, ek genuinely interesting case bhi mila (LLM ne "Adobe Photoshop" ko "Adobe Creative Suite" se match karne se mana kiya — overly cautious, relevancy=0 — bilkul wahi cheez jo eval system pakड़ne ke liye banaya jaata hai).
3. **Drift detection end-to-end**: 10 backend-engineer + 3 marketing/design candidates seed kiye (real OpenAI embeddings), PSI=12.43 (threshold se bohot upar), alert correctly trigger hua. S3 JSON report fetch karke verify kiya (real presigned URL, real content). MLflow run query karke confirm kiya.
4. **MLflow query verify kiya**: `mlflow.search_runs()` se sabhi 4 experiments (pipeline-runs, ragas-evaluations, embedding-drift) ke real logged runs fetch kiye — metrics/tags sab sahi.
5. **Prometheus `/metrics`**: real text-format output confirm kiya, custom metrics (`hiring_pipeline_duration_seconds`, `api_request_total`, `match_score_distribution`, `llm_token_usage_total`) sab registered aur real values ke saath populate ho rahe the ek full pipeline run ke baad.
6. **Cache-aside**: real `/match` call do baar kiya — pehla (cache miss) 56.5s, dusra (cache hit) 2.5s — **22.9x measured speedup**, responses identical.
7. **Full pipeline run**: real `/pipeline/run` chalaya, `hiring_pipeline_duration_seconds` (33.3s) aur MLflow pipeline-run (real per-model cost + match_score=98.74) dono confirm kiye.
8. **Frontend**: `tsc --noEmit` clean, `next lint` clean. Playwright se poora dashboard load kiya (zero console errors), sab stat cards/chart/alerts real data ke saath render hue (screenshot verify kiya). "Run Drift Check" button click kiya — default baseline_size(100) is dev DB (sirf ~13 relevant candidates) ke liye insufficient hai, jo REALISTIC hai ek fresh system ke liye — UI ne error ko gracefully dikhaya (koi crash nahi, button re-enable hua). "Run RAGAS Eval" button bhi real trigger kiya, server-side successfully complete hua (5 real rows DB me confirm kiye) — sirf test-script ka apna wait-timeout chhota tha, real user experience is fine (frontend ka apna axios timeout 300s hai).
9. **Cleanup**: seeded test candidates/job delete kiye, ek stale Redis cache key clean kiya, scratch scripts remove kiye. Analytics history (RagEvalLog, DriftReport, MLflow runs) jaan-boojhkar rakhi — wahi dashboard ko meaningfully populate karti hai.

## Local Run

```
http://localhost:3000/analytics
```

Dashboard automatically load hoti hai jo bhi data available hai. Manual triggers: "Run RAGAS Eval" (chahiye: kam se kam 2 candidates parsed resume + embedding ke saath) aur "Run Drift Check" (chahiye: `?baseline_size=N` query param agar dev DB me 100 se kam candidates hain — default 100 hai jo spec match karta hai).

`GET /metrics` Prometheus scrape format me — local Prometheus se point kiya ja sakta hai.

**MLflow UI dekhne ke liye**: `mlflow ui --backend-store-uri sqlite:///mlflow.db` (backend/ folder se).

## Aage Kya (Module 8+)

- Real scheduler (APScheduler ya system cron) taaki `run_evaluation`/`run_drift_check` genuinely weekly chalein bina manual trigger ke
- Prometheus histogram buckets ko production traffic dekhkar tune karna
- Cache invalidation `matching_service` se automatically trigger karna (naya resume parse hone par) — abhi sirf TTL-based staleness hai
- Drift baseline ko periodically refresh karna (abhi hardcoded "first N candidates")
- MLflow artifact store (abhi sirf metrics/params — PDF reports, prompt templates artifacts ke liye dedicated storage backend chahiye production me)
