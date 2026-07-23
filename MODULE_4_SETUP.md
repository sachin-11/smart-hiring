# Module 4: LangGraph Multi-Agent Orchestrator + LLM Router

Sabhi agents (Module 2/3) ko ek LangGraph state machine me wire kiya, dual-LLM routing (Groq vs GPT-4o) ke saath cost optimization, aur live progress SSE se stream.

## Folder Structure (naya/updated)

```
backend/app/
├── agents/
│   └── orchestrator.py          # HiringState, nodes, conditional routing, compiled graph
├── api/v1/routes/
│   └── pipeline.py              # POST /pipeline/run — SSE stream
├── schemas/
│   └── pipeline.py              # InterviewQuestionSet, CandidateReport, PipelineRunRequest
├── services/
│   ├── llm_router.py            # dual-LLM routing + Redis cost logging
│   └── matching_service.py      # updated: score_single_pair() helper
frontend/
├── app/pipeline/page.tsx        # test harness page (candidate_id/job_id inputs)
├── components/PipelineProgress.tsx  # live SSE step tracker
└── types/pipeline.ts
```

## Kya Setup Hua

### LangGraph State Machine (`orchestrator.py`)

```
parse_resume → analyze_jd → match_candidates → (score > 0.7) → generate_questions → create_report
                                              → (score ≤ 0.7) → create_rejection_report
any node error → error_handler
```

- **`parse_resume`** — Candidate DB se load (Module 2 se already-parsed data), phir Groq se ek-line summary generate karta hai (genuinely "simple/extraction" task).
- **`analyze_jd`** — Job DB se load (Module 3 se already-analyzed data), Groq se summary.
- **`match_candidates`** — Cross-encoder (Module 3 wala model, `matching_service.score_single_pair()`) se is specific candidate-job pair ka score (0-1 scale — task spec explicitly `match_score > 0.7` check karta hai, isliye 0-1 rakha, Module 3 ke UI-facing 0-100 se alag).
- **`generate_questions`** — Sirf tab chalta hai jab match_score > 0.7. GPT-4o structured output se 5 tailored interview questions.
- **`create_report`** / **`create_rejection_report`** — GPT-4o se final report (summary, strengths, concerns, recommendation) — same Pydantic schema, alag prompt framing.
- **`error_handler`** — Kisi bhi node me error aane par yahan route hota hai, log karta hai, gracefully end.

Har node apni exceptions khud catch karta hai aur `state["errors"]` me append karta hai (exception propagate nahi hone deta) — isse conditional edges `state["errors"]` check karke route kar sakte hain, LangGraph ke exception-based failure ki bajaye.

### Dual-LLM Router (`llm_router.py`)

- `TaskComplexity.SIMPLE` → **Groq `llama-3.3-70b-versatile`** (note: task ne `llama-3.1-70b-versatile` bola tha, lekin wo Groq pe deprecated ho chuka hai — live Groq API se model list check karke `llama-3.3-70b-versatile` use kiya)
- `TaskComplexity.COMPLEX` → **GPT-4o**
- Agar SIMPLE task ka estimated input bahut bada hai (>6000 tokens), GPT-4o pe escalate ho jaata hai
- Real `usage_metadata` (LangChain response se) use karke accurate cost calculate hota hai, estimate sirf routing decision ke liye
- Cost Redis me log hota hai: `llm_cost:total_usd`, `llm_cost:by_model:{model}`, aur `llm_cost:log` (last 200 entries ki list) — best-effort (Redis down ho to warning log karke aage badh jaata hai, LLM call fail nahi hota)

### SSE Streaming (`routes/pipeline.py`)

`POST /api/v1/pipeline/run` — LangGraph ka `.astream()` (default "updates" mode, har node ke baad `{node_name: partial_state}`) ko SSE me wrap kiya. Har event `data: {"step": ..., "state": {...accumulated full state...}}\n\n` format me stream hota hai, end me `step: "__end__"`.

**Important**: Browser ka native `EventSource` sirf GET support karta hai, POST nahi — isliye frontend `fetch()` + `ReadableStream` reader se manually SSE parse karta hai (EventSource use nahi kar sakte).

## Verification Kya Kiya

Sabse pehle ek real bug pakड़ा: task ne `llama-3.1-70b-versatile` specify kiya tha, lekin live Groq API (`GET /v1/models`) se confirm hua ki ye model ab available hi nahi hai — `llama-3.3-70b-versatile` use kiya, real test call se confirm kiya (`usage_metadata` bhi sahi aata hai).

**Local Redis nahi tha** (Module 1-3 me bhi nahi) — Docker Desktop start kiya (already installed tha), jisme user ke ek doosre project ka Redis container pehle se `restart` policy ke saath tha, wahi use kar liya (port 6379). Cost logging genuinely verify karne ke liye zaroori tha.

2 synthetic candidates seed kiye (ek strong backend match, ek unrelated graphic designer) + 1 real job, phir:

1. **Strong-match pipeline run** — real SSE stream se: parse_resume → analyze_jd → match_candidates (score=0.9987) → generate_questions (5 questions) → create_report (recommendation="proceed to interview"). Koi errors nahi.
2. **Weak-match pipeline run** — match_candidates (score=0.0259, threshold se kam) → seedha create_rejection_report pe route hua, generate_questions skip ho gaya bilkul jaisa design tha. Recommendation="reject".
3. **Error path** — non-existent candidate_id se test kiya → parse_resume ne error capture kiya → seedha error_handler pe route hua, baaki nodes bilkul nahi chale.
4. **Redis cost logs verify kiye** — 8 log entries mile, dono models (`llama-3.3-70b-versatile` for parse_resume/analyze_jd, `gpt-4o` for generate_questions/create_report) confirm, real token counts aur cost calculation sahi.
5. **Full browser test** (Playwright): `/pipeline` page pe candidate/job ID daal ke "Run Pipeline" click kiya — dono branches (strong match aur rejection) live dekhe, step indicators (spinner → checkmark, ya pending rehna jab step skip ho) exactly design ke mutabik render hue, koi console error nahi.
6. Sab test data (DB candidates/job, Redis keys) cleanup kar diya.

## Local Run

```
http://localhost:3000/pipeline
```

Candidate ID aur Job ID chahiye (Module 2 se parsed candidate, Module 3 se banaya job). `/upload` aur `/jobs/new` se in IDs ko create/copy kar sakte ho.

**Note**: Redis chalu na ho to bhi pipeline kaam karega (cost logging silently skip ho jayegi, warning log hogi) — lekin agar cost monitoring dekhni hai to Redis chalana zaroori hai (`docker run -d -p 6379:6379 redis:7-alpine` ya docker-compose se).

## Aage Kya (Module 5+)

- Pipeline results (report, questions, match_score) ko `Application`/`Interview` models me persist karna (abhi ephemeral hai, sirf stream hoke discard ho jaata hai)
- `/jobs/[id]/matches` page se seedha "Run Pipeline" trigger karna (abhi candidate ID manually daalni padti hai)
- LangGraph checkpointing (resume/pause pipeline runs)
- Redis cost dashboard (`llm_cost:log` se) — abhi sirf raw Redis keys hain, koi UI nahi
