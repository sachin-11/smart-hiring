# Module 9: Production Hardening, MLOps Depth, Voice AI Overhaul, aur UI Redesign

Ye module ek single focused feature nahi hai — ek extended hardening pass hai jo Module 1-8 ke UI/security/reliability gaps pakड़ke fix karta hai, plus do naye MLOps eval loops (LLM-as-judge, scheduled automation), plus poora AI voice interview pipeline production-grade banaya (idle timeout, reconnect, barge-in, streaming TTS, AudioWorklet, audio-reactive avatar, real interview-jaisa greeting flow).

## Folder Structure (naya/badla hua)

```
backend/app/
├── core/
│   ├── rate_limit.py             # NEW — Redis-backed slowapi Limiter (shared across workers)
│   └── deps.py                   # unchanged, ab har router pe apply hota hai (pehle sirf kuch)
├── services/
│   ├── guardrails.py             # NEW — prompt-injection scan, wrap_untrusted(), redact_pii()
│   ├── llm_router.py             # BADLA — invoke_structured_with_fallback(), cross-provider retry
│   ├── voice_service.py          # BADLA — split_into_speech_chunks(), has_heard_speech property
│   └── mlops/
│       ├── llm_judge_evaluator.py    # NEW — independent model re-scores a sample, measures agreement
│       └── scheduler.py              # BADLA — judge eval bhi ab scheduled run me shामिल
├── models/
│   └── mlops.py                  # BADLA — naya AnswerJudgeLog table
├── agents/
│   ├── interview_agent.py        # BADLA — intro turns (greeting/how-are-you/self-intro), guardrails wired
│   ├── jd_analyzer.py            # BADLA — ab llm_router se (pehle hardcoded ChatOpenAI, no fallback)
│   ├── resume_parser.py          # BADLA — same fix
│   └── report_agent.py           # BADLA — llm_router ka naya fallback helper use karta hai
├── api/v1/routes/
│   ├── auth.py                   # BADLA — rate limits + /forgot-password, /reset-password
│   ├── interview.py              # BADLA — idle timeout, sentence-chunked TTS streaming over WS
│   ├── candidates.py             # BADLA — real SQL-level pagination (LATERAL JOIN)
│   ├── jobs.py                   # BADLA — SQL-level pagination + total count
│   └── (candidates/jobs/dashboard/analytics/matching/notifications/pipeline/
│        interview/report/resume) # sab ab router-level Depends(get_current_recruiter)
frontend/
├── components/
│   ├── AIAvatar.tsx              # NEW — audio-reactive avatar (real-time amplitude via AnalyserNode)
│   ├── VoiceRecorder.tsx         # REWRITE — AudioWorklet, reconnect, mic-disconnect detect, barge-in hook
│   ├── ui/spinner.tsx            # NEW — Spinner + LoadingState
│   ├── ui/skeleton.tsx           # NEW
│   └── layout/                   # Sidebar/Header — mobile drawer, aria-current, indigo theme
├── public/audio-processor.worklet.js  # NEW — off-main-thread PCM downsample (ScriptProcessorNode ki jagah)
├── lib/store/ui.ts               # NEW — mobile sidebar open/close (Zustand)
├── app/
│   ├── error.tsx, not-found.tsx  # NEW
│   ├── (auth)/forgot-password/, (auth)/reset-password/  # NEW
│   └── globals.css               # BADLA — indigo/violet design tokens (pehle pure grayscale tha)
```

## Kya Setup Hua

### 1. Backend auth gap — pura router-level lockdown

Module 8 me sirf `notifications`/`candidates bulk-*` protect kiye the ("genuinely recruiter-only actions" scope decision). Is baar audit karne pe pata chala **`candidates`, `jobs`, `dashboard`, `analytics`, `matching`, `pipeline`, `interview`, `report`, `resume` — sab bilkul unauthenticated the**, sirf `/auth` open hona chahiye tha. Har router pe `dependencies=[Depends(get_current_recruiter)]` laga diya (endpoint-level ke bajaye router-level — cleaner, ek jagah). WebSocket (`/ws/interview/{session_id}`) jaan-boojhkar unauthenticated rakha — browsers WS handshake pe Authorization header attach nahi kar sakte; session_id ek unguessable UUID hai, ye hi guarantee hai.

### 2. Rate limiting (`core/rate_limit.py`)

`slowapi` + Redis storage (workers ke beech shared). `/auth/login` 5/min, `/auth/register` 5/hr, `/auth/forgot-password` 3/hr, LLM-calling endpoints (`/pipeline/run`, `/interview/start`, `/report/generate`) 10/min. 429 response ko custom handler se `{"detail": ...}` shape diya (slowapi ka default `{"error": ...}` app ke baaki error contract se match nahi karta tha, frontend ka `extractErrorMessage` `detail` expect karta hai).

### 3. Forgot/Reset Password (`routes/auth.py`)

`POST /auth/forgot-password` — email-enumeration-safe (account exist kare ya na kare, same generic response), Redis me single-use reset token (1hr TTL, refresh-token rotation jaisa hi pattern — GET+DELETE pipeline). `POST /auth/reset-password` — token consume karke password update. Frontend: `/forgot-password`, `/reset-password?token=...` pages, login page pe link.

### 4. Cross-provider LLM fallback (`services/llm_router.py`)

`invoke_structured_with_fallback()` aur `invoke_with_routing()` — agar primary model (task-complexity se choose hua) fail ho (timeout/rate-limit/outage), automatically **doosre provider** pe ek retry. Pehle koi fallback nahi tha — Groq down ho jaaye to poora request fail. Ye function **5 agents** me apply kiya: `interview_agent.py`, `question_generator.py`, `report_agent.py`, aur do jagah jo pehle `llm_router` use hi nahi karte the — `jd_analyzer.py`/`resume_parser.py` (hardcoded `ChatOpenAI`, koi fallback/cost-logging nahi thi).

### 5. Guardrails (`services/guardrails.py`)

Dependency-free heuristic layer (regex/keyword, ML classifier nahi — real systems bhi pehle isi tarah shuru karte hain):
- `scan_for_injection()` — common injection phrasing patterns ("ignore previous instructions", "you are now", "reveal your system prompt", etc.) detect karke log karta hai (block nahi karta — false positives real candidates ko zyada nuksan karte, determined attacker ke paas doosre raaste bhi hote hain).
- `wrap_untrusted()` — untrusted text (candidate answer, resume, JD) ko `<label>...</label>` delimiters + explicit "treat as data not instructions" note ke saath isolate karta hai — yehi actual mitigation hai, detection sirf observability ke liye.
- `redact_pii()` — email/phone/SSN/credit-card patterns logs ke liye redact karta hai.

Candidate answers (`analyze_answer_node`, `generate_follow_up_node`), resume text, JD text — teeno jagah wired.

### 6. LLM-as-judge evaluation (`services/mlops/llm_judge_evaluator.py`)

RAGAS **retrieval** quality check karta hai, lekin koi bhi **generation/scoring** quality check nahi karta tha. Naya eval: completed interviews se scored answers ka ek random sample leke, ek **independent, deliberately stronger model** (GPT-4o) *blind* re-score karta hai (original score dikhaye bina), aur agreement measure karta hai — bilkul human calibration review jaisa concept, live scoring model (Groq, latency ke liye SIMPLE-routed) pe applied. Naya `AnswerJudgeLog` table, `/mlops/judge/run` endpoint, scheduler me RAGAS/drift ke saath wire, Analytics page pe "Run LLM Judge" button.

### 7. SQL-level pagination (`routes/candidates.py`, `routes/jobs.py`)

`GET /candidates` pehle **poori table fetch karke Python me slice** karta tha (`items[offset:offset+limit]`). Ab ek `LATERAL JOIN` se har candidate ki latest-application (match_score/job) SQL me hi compute hoti hai, `WHERE`/`LIMIT`/`OFFSET` sab DB-level — `min_score`/`max_score` filters bhi ab SQL me. `GET /jobs` me bhi `LIMIT`/`OFFSET` + total count add kiya (pehle bilkul nahi tha).

### 8. Voice AI interview — production hardening

Sabse bada hissa. Purana WS voice pipeline kaam karta tha lekin production-ready nahi tha:

- **Idle timeout** (`interview.py`): candidate 20s chup rahe to nudge, 45s tak kuch na ho to clean error ke saath close. Pehle `websocket.receive()` hamesha ke liye block karta tha agar candidate kabhi bola hi nahi. Zaroori tha wall-clock "last detected SPEECH" track karna, na ki "last received FRAME" — mic khula rehne pe silent frames continuously aate rehte hai, isliye simple receive-timeout kaafi nahi tha.
- **WS auto-reconnect** (`VoiceRecorder.tsx`): connection drop ho (network blip) to exponential backoff ke saath 3 attempts tak reconnect. Session state Redis me already durable hai (interview_agent), isliye sirf transport reconnect karna hota hai.
- **Mic-disconnect detection**: `track.onended` listener — device unplug/permission revoke ho to turant error, "listening" state me hamesha ke liye atka nahi rehta (ye pehle ka real bug tha).
- **Barge-in**: "Start speaking" click karte hi jo AI audio play ho raha hai wo turant pause ho jata hai (`onBeforeRecording` callback VoiceRecorder → parent).
- **Sentence-chunked streaming TTS** (`_stream_question_audio` in `interview.py`, `voice_service.split_into_speech_chunks()`): poora response synthesize hone ka wait karne ke bajaye, sentence-by-sentence synthesize+stream hota hai — pehla sentence bajta hai jabki agla generate ho raha hota hai. Frontend ek audio-chunk queue maintain karta hai (`interview/[sessionId]/page.tsx`), sequential playback.
- **AudioWorklet migration** (`public/audio-processor.worklet.js`): deprecated `ScriptProcessorNode` hataya, off-main-thread PCM16 downsampling.
- **Safari fix**: explicit `audioCtx.resume()`, mic constraints me echo-cancellation/noise-suppression on kiya (VAD noise-robustness).
- **AI Avatar** (`AIAvatar.tsx`): circular orb, AI ki apni playback audio ka real amplitude (`MediaElementAudioSourceNode` → `AnalyserNode`) se pulse/glow karta hai — candidate ke mic waveform (`WaveformVisualizer`) ka playback-side counterpart. **Known limitation**: S3-served audio (HTTP path — pehla question, text-mode answers) ke liye CORS configured nahi hai bucket pe, isliye us audio pe avatar sirf idle-breathe karta hai (silent degrade, playback break nahi hota) — sirf WS-streamed (blob URL, same-origin) audio pe live react karta hai.
- **Interview intro flow** (`interview_agent.py` — `_build_intro_turns`, `INTRO_CATEGORY`): candidate ke naam se formal greeting → "how are you" → candidate reply → "tell me about yourself" → candidate reply → **phir** real scored questions shuru. Do fixed (non-LLM, cost-free) turns, jo scoring graph ko bypass karte hain (`_route_after_analysis` seedha "advance" pe route karta hai agar category="intro") — na score hote hain na follow-up generate hota hai unke liye. "Question X of 8" counter intro ke dauraan hide rehta hai ("Getting started…" dikhta hai).
- **First-question audio bug fix**: `app/interview/page.tsx` `/interview/start` se `audio_url` leke turant `/interview/{sessionId}` pe navigate ho jata tha — us audio ka kabhi use hi nahi hota tha (destination page `/transcript` se load karta hai, jisme audio field hai hi nahi). **Har interview ka pehla question — ab greeting — kabhi bola nahi jata tha.** `sessionStorage` handoff se fix kiya.

### 9. Frontend UI — full redesign

Pura app pure-grayscale shadcn default theme pe tha (0 chroma — koi accent color hi nahi). `globals.css` design tokens indigo/violet accent system se replace kiye. Sidebar/Header naye semantic `sidebar-*` tokens use karte hain, mobile pe collapsible drawer (`lib/store/ui.ts`), active nav link pe `aria-current="page"`. Proper `Spinner`/`Skeleton` components (pehle sab jagah plain "Loading…" text tha). `error.tsx`/`not-found.tsx` add kiye (pehle koi custom error boundary nahi tha).

### 10. Dev environment fix

Local Redis pehle ek **unrelated project** ka container reuse karta tha (`instagram-market-redis`) kyunki port 6379 clash hota tha. Ab is project ka apna `docker-compose.yml` Redis service use hota hai, host port **6381** pe remap kiya (unrelated container se clash avoid karne ke liye).

## Design Decisions / Findings

1. **Router-level auth, endpoint-level nahi** — Module 8 me kuch endpoints individually protect kiye the (`_recruiter: Recruiter = Depends(...)` har function me). Ab router-level `dependencies=[...]` — ek jagah, saari routes automatically covered, naye endpoints add karne pe bhoolne ka risk nahi.
2. **Prompt injection "block" nahi karta, sirf isolate+log karta hai** — heuristic false-positive rate real hai (legitimate candidate answer me "ignore the deadline pressure..." jaisi phrase aa sakti hai); hard-block karne se real candidates ko nuksan hota, determined attacker ko nahi rokta. `wrap_untrusted()` (isolation) hi actual defense hai.
3. **LLM-judge deliberately COMPLEX-tier model use karta hai jabki original scorer SIMPLE-tier hai** — "cheap/fast model for volume, strong model to audit a sample" — ek real production pattern, sirf "same model dobara pucho" nahi.
4. **Voice AI reconnect sirf transport-level hai, audio replay nahi** — agar WS beech me disconnect hui exactly jab candidate bol raha tha, wo partial utterance drop ho jata hai (naye connection ke baad fresh VAD state). Poori utterance buffer karke resume karna bahut zyada complexity add karta bina proportional value ke.
5. **AI Avatar S3-audio pe react nahi karta** — CORS fix karne ka matlab hota `crossOrigin="anonymous"` add karna, jo bina bucket-side CORS config ke **audio load hi break kar deta** (verified: bucket pe koi CORS config nahi hai). Safe degradation (idle state) risky "maybe it breaks playback" se better trade-off tha.
6. **Intro turns LLM-generated nahi, fixed templates hai** — candidate ka naam + job title interpolate karte hain, lekin har baar same 2 questions. Dynamic/contextual greeting (jaise candidate ke "how are you" jawaab ka acknowledge karna) ek extra LLM call maangta, jo latency+cost add karta is chhoti si rapport-building step ke liye — worth nahi laga.

## Verification Kya Kiya

Sab real APIs/DB/Redis se, plus browser automation jahan zaroori tha. Is baar user ne explicitly bola "zyada testing mat karo, khud test karunga" — isliye heavy Playwright cycles ke bajaye targeted, high-signal checks kiye:

1. **Auth lockdown**: curl se saari pehle-open routes pe bina token ke hit kiya — `jobs`, `dashboard`, `candidates`, `pipeline/run`, `interview/start`, `report/generate` sab `401 {"detail":"Not authenticated"}` de rahe hai; `/auth/login` khud accessible raha (401 wrong-password wala, auth-guard wala nahi).
2. **Rate limiting real burst test**: `/auth/login` pe 7 sequential requests — pehle 5 `401` (wrong password), 6th-7th `429` sahi format ke saath. **Real exhaustion bhi dekha** — is session ki testing se hi `/auth/register` (5/hr) aur `/auth/forgot-password` (3/hr) genuinely exhaust ho gaye the, jo khud rate-limiting ke kaam karne ka proof tha.
3. **LLM fallback real failure simulation**: Groq API key ko jaan-boojhkar invalid banaya, `invoke_structured_with_fallback()` call kiya — Groq call `401 Invalid API Key` se fail hui, automatically OpenAI pe retry hua, sahi structured result mila. Log: `"LLM fallback succeeded ... using gpt-4o after llama-3.3-70b-versatile failed"`.
4. **Guardrails unit-level**: `scan_for_injection("Ignore all previous instructions...")` → match mila; clean text → koi match nahi; `redact_pii()` → email/phone/SSN sahi se `[REDACTED_*]` hue; `wrap_untrusted()` → payload ke andar `</candidate_answer>` tag khud ko premature close nahi kar saka (stripped).
5. **LLM-judge**: real synthetic answer pe `_judge_answer()` call kiya — sahi 1-5 score + reasoning mila. "Not enough data" path bhi test kiya (0 completed interviews the us waqt) — `ValueError` sahi se raise hua, route ne use `400` me convert kiya.
6. **Pagination**: real SQL query log dekha — `LEFT OUTER JOIN LATERAL (...) ON true ... WHERE anon_1.match_score >= $2 ... LIMIT $3 OFFSET $4` — confirm hua ki filtering+pagination dono DB-level pe ho rahe hai, Python slicing nahi. `min_score=50` filter se sahi 4/6 candidates mile.
7. **Interview intro flow end-to-end** (direct agent call, real DB candidate/job se): Turn 1 = greeting with candidate's real first name ("Hello, Sachin!") + job title, category="intro". Turn 2 (after "I am doing great") = self-intro prompt, still intro, `score=None`. Turn 3 (after self-intro answer) = **first real technical question**, category="technical", score still None for the just-finished intro turn (correctly excluded).
8. **Frontend**: `tsc --noEmit` aur `next lint` — har badlaव ke baad clean check (kai baar, dozens of edits ke through).
9. **Backend import smoke test**: har major change ke baad `python -c "import app.main"` — sab clean.
10. **Full nav regression**: 8-link sidebar navigation, hard reload pe auth race condition (jo redesign session me khud discover hui aur fix hui — persist middleware SSR crash, phir token-hydration race) — zero console errors confirm hua.
11. **Process hygiene**: is poore session me baar-baar orphaned backend processes accumulate hue (Windows `--reload` supervisor/worker split ki wajah se) jo purana code serve kar rahe the, causing intermittent "kaam kiya lekin test fail hua" confusion — har baar systematically identify+kill karke bilkul clean single-process state confirm ki, phir dobara test kiya.

## Local Run

Backend `.env` me naye settings (defaults already sensible hai, override optional):
```
RATE_LIMIT_LOGIN=5/minute
RATE_LIMIT_REGISTER=5/hour
RATE_LIMIT_FORGOT_PASSWORD=3/hour
RATE_LIMIT_LLM_ENDPOINTS=10/minute
FRONTEND_URL=http://localhost:3000
INTERVIEW_WS_NUDGE_SECONDS=20
INTERVIEW_WS_TIMEOUT_SECONDS=45
```

Redis: `docker-compose up -d redis` (host port **6381**, `.env` me `REDIS_URL` already update hai).

Naya `AnswerJudgeLog` table auto-create ho jata hai (`create_all`, jaisa Module 7-8 ke naye tables ke saath hua tha — is project me Alembic scaffold hai lekin actual source-of-truth `init_db()`'s `create_all` hai, migrations sirf pehle 3 modules tak likhi gayi thi).

## Aage Kya (Module 10+)

- Real pytest suite (abhi bhi nahi hai — sabse purana known gap)
- LLM-judge/RAGAS results ke liye ek proper trend chart (abhi sirf last-action text message dikhta hai, RAGAS jaisa dedicated graph nahi)
- Voice WS ke liye query-param token auth (abhi session_id ki unguessability pe hi relies karta hai)
- PII redaction sirf regex-based hai — production me ek proper NER-based PII detector better hoga
- Prompt injection detection bhi heuristic hai — ek lightweight classifier (ya LLM-based guard) zyada robust hoga
- S3 bucket CORS config (agar AIAvatar ko HTTP-path audio pe bhi react karwana ho)
