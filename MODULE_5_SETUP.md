# Module 5: AI Interview Engine — Adaptive Q&A + Voice Pipeline

Real-time voice interview system: LangGraph adaptive Q&A agent (score answer → follow-up if weak, else next question), personalized question generation from JD/resume gaps, STT/TTS via OpenAI, WebRTC VAD-based silence detection over a WebSocket, aur ek voice-capable interview room UI.

## Folder Structure (naya)

```
backend/app/
├── agents/
│   ├── interview_agent.py       # LangGraph turn state machine, Redis session memory
│   └── question_generator.py    # personalized question set (40/30/20/10 mix, CoT rationale)
├── api/v1/routes/
│   └── interview.py             # start/answer/transcript REST + /ws/interview/{id} WebSocket
├── schemas/
│   └── interview.py             # question/answer/transcript/WS payload models
├── services/
│   ├── voice_service.py         # Whisper STT, OpenAI TTS, WebRTC VAD, PCM→WAV
│   └── s3_service.py            # +upload_interview_audio()
frontend/
├── app/interview/
│   ├── page.tsx                 # candidate_id/job_id → POST /interview/start → redirect
│   └── [sessionId]/page.tsx     # interview room: question, timer, counter, text/voice, transcript
├── components/
│   ├── VoiceRecorder.tsx        # mic capture, raw PCM16 streaming over WS, turn state machine
│   └── WaveformVisualizer.tsx   # canvas waveform driven by an AnalyserNode
├── lib/pcm.ts                   # downsample-to-16kHz + Float32→PCM16 helpers
└── types/interview.ts
```

## Kya Setup Hua

### LangGraph Turn State Machine (`interview_agent.py`)

```
analyze_answer → (score < 3 AND follow_up_depth < 2) → generate_follow_up → END
              → (else)                                → advance             → END
any node error → error_handler → END
```

Pipeline ke orchestrator (Module 4) se alag — yeh graph poore interview ka nahi, balki **ek turn** ka hai. Har `POST /interview/answer` (ya WS voice turn) is graph ko ek baar `.ainvoke()` karta hai: candidate ka answer state me daalo, grade karo, follow-up ya next-question decide karo, Redis me save karo, response return karo. State stateless HTTP requests ke beech Redis me carry hoti hai (`session:{session_id}`, JSON, 2hr TTL) — ismein `questions` (pre-generated set), `current_q_index`, `follow_up_depth`, `history` (poora Q&A log), sab kuch hai.

- **`analyze_answer`** — Groq (`TaskComplexity.SIMPLE`) se answer ko 1-5 score karta hai + one-line feedback. Task spec explicitly bola "Use Groq for fast response (low latency critical for voice)" — isliye grading *and* follow-up generation dono Groq pe hain, sirf question-generation (ek-baar, session start pe, latency-insensitive) GPT-4o pe hai.
- **`generate_follow_up`** — score < 3 aur `follow_up_depth < MAX_FOLLOW_UP_DEPTH` (=2, task spec me explicit number nahi tha, infinite-loop se bachne ke liye cap laga) ho to hi chalta hai. Same category me ek focused follow-up banata hai, verbatim repeat nahi karta.
- **`advance`** — `current_q_index` ko badhata hai; agar sab questions ho gaye to `complete=True`.

### Question Generation (`question_generator.py`)

`TOTAL_QUESTIONS=8`, category split largest-remainder rounding se **exactly** 40/30/20/10 (technical=3, behavioral=2, situational=2, culture=1) sum tak pahunchta hai chahe total kuch bhi ho. Resume ke `skills` ko JD ke `required_skills` se compare karke gaps nikalta hai, phir chain-of-thought prompt me explicitly bolta hai gaps aur seniority level ke against har question ko justify karo — `rationale` field me wo reasoning save hoti hai.

**Real test output** (Senior Backend role, candidate ki resume me Kubernetes missing): generated questions ne genuinely Kubernetes gap target kiya ("How would you approach deploying a FastAPI application on Kubernetes?") aur mentoring responsibility target kiya, sirf generic questions nahi diye.

### Voice Pipeline (`voice_service.py`)

- **STT**: OpenAI Whisper (`whisper-1`), koi client-side transcoding nahi chahiye — Whisper webm/wav/mp3 sab accept karta hai.
- **TTS**: OpenAI TTS (`tts-1`, voice=`alloy`), mp3 bytes return karta hai (ya `pcm` format jab raw samples chahiye).
- **VAD**: `webrtcvad` frame-by-frame (30ms frames, 16kHz mono PCM16) speech/silence classify karta hai; `VoiceActivityDetector` class ~800ms trailing silence ke baad "utterance ended" signal deta hai — WebSocket handler isse pata karta hai ki candidate bol chuka.
- **`pcm_to_wav()`** — raw PCM ko minimal WAV header ke saath wrap karta hai taaki Whisper accept kare (no external audio lib chahiye).

### REST + WebSocket (`routes/interview.py`)

- `POST /interview/start` — candidate+job DB se load, question set generate, Interview row bana ke (`status=IN_PROGRESS`) uska `id` hi `session_id` use karta hai, Redis me initial state save, first question ka TTS synthesize+S3 upload, presigned URL return.
- `POST /interview/answer` — multipart form (`session_id` + `answer_text` **ya** `audio_file`); audio ho to pehle Whisper se transcribe karta hai, phir same turn-graph logic.
- `GET /interview/{session_id}/transcript` — live ho to Redis se (current pending question bhi included, answer=null), complete ho gaya ho to Interview DB row se (`ai_feedback` JSON me poora history, `ai_score` = average).
- `WS /ws/interview/{session_id}` — client raw PCM16LE 16kHz binary frames bhejta hai; server VAD se end-of-utterance detect karta hai, Whisper se transcribe, agent turn chalata hai, `{"type":"transcript"}` → `{"type":"result"}` → `{"type":"audio_start"}` + binary TTS bytes wapas bhejta hai.

**Important routing detail**: WS route ko `/interview` prefix wale router se **alag** `ws_router` (no prefix) pe register kiya, warna path `/interview/ws/interview/{id}` ban jata (spec `/ws/interview/{id}` chahta hai, `/api/v1/` prefix ke sath).

### Frontend (`VoiceRecorder.tsx`, `WaveformVisualizer.tsx`, `[sessionId]/page.tsx`)

- Mic capture → `AudioContext` + `ScriptProcessorNode` (AudioWorklet ka simpler alternative — koi separate worklet module file serve nahi karni padti) → Float32 samples ko 16kHz pe downsample (linear interpolation, `lib/pcm.ts`) → PCM16 → WebSocket binary send. Same `MediaStreamSource` se ek parallel `AnalyserNode` waveform visualizer ko drive karta hai.
- Interview room `GET /interview/{sessionId}/transcript` se hydrate hoti hai (page refresh-safe — Redis ya DB se resume ho jaata hai), current pending question ko "answer=null" wale last exchange se detect karta hai.
- Text aur voice mode ek hi `commitAnswer()` path se history/next-question update karte hain — WS ka `is_follow_up` field agla question follow-up hai ya nahi bolta hai (jis question ka abhi answer diya wo follow-up tha ya nahi, wo `currentQuestionRef` me pehle se track hota hai, response field se confuse nahi hona chahiye — ismein ek bug pakड़ा aur fix kiya during dev).

## Design Decisions / Task Se Deviations

1. **`webrtcvad-wheels==2.0.14`** (not raw `webrtcvad`) — plain `webrtcvad` ko Windows pe compile karne ke liye MSVC Build Tools chahiye (nahi the). `webrtcvad-wheels` same API deta hai with prebuilt wheels; pinned version `2.0.11.post1` ke liye Windows/cp312 wheel nahi tha, `2.0.14` pe hai.
2. **Presigned S3 URLs for audio playback** — bucket private hai (resumes jaisa hi), raw object URL browser me 403 deta hai. TTS audio actually play hona chahiye, isliye `s3_service.generate_presigned_url()` use kiya (resume upload flow me already tha, bas interview audio ke liye bhi apply kiya).
3. **`MAX_FOLLOW_UP_DEPTH = 2`** — task spec ne koi cap nahi bataya; bina cap ke ek consistently-weak answer infinite follow-up loop bana sakta tha.
4. **Question count = 8**, 40/30/20/10 → 3 technical / 2 behavioral / 2 situational / 1 culture (largest-remainder rounding se exact sum guarantee).
5. **ScriptProcessorNode instead of AudioWorklet** — deprecated hai lekin universally supported aur koi extra `.js` worklet file serve nahi karni padti; comment likh diya code me.
6. **`total_questions`/`question_index` fields transcript response me add kiye** — original schema draft me nahi the, frontend ko accurate "Question X of 8" counter ke liye chahiye the (follow-ups ki wajah se exchange-list length se index derive karna galat hota — ek follow-up round mein 2 exchanges but same question slot).
7. **CORS**: local `.env` me `CORS_ORIGINS` ko `http://localhost:3000,http://localhost:3001` kar diya — testing ke waqt port 3000 pe ek unrelated Node process already chal raha tha, Next dev 3001 pe start hua. `.env` gitignored hai, harmless local dev change.

## Verification Kya Kiya

Sab real APIs se (OpenAI Whisper/TTS/GPT-4o, Groq, real S3 bucket, real Neon Postgres, local Redis) — koi mock nahi.

1. **Real Redis nahi tha running** (Module 4 jaisa hi issue) — Docker Desktop start kiya, existing `instagram-market-redis` container (port 6379) use kar liya.
2. **Question generation** — real candidate (Priya Sharma, skills: Python/FastAPI/PostgreSQL/Docker, no Kubernetes) vs real job (Senior Backend Engineer, requires Kubernetes+System Design) seed kiya. Generated 8 questions: exact 3/2/2/1 split, rationales genuinely skill-gap-aware (Kubernetes, mentoring) — generic nahi the.
3. **Text-mode full turn loop**: weak answer → real follow-up triggered (score=1, same `q_index`, `is_follow_up=True`); good answer to follow-up → advanced to next question; ek off-topic "good" answer bhi correctly low-scored (context-aware grading confirm hua, sirf keyword-matching nahi).
4. **Full 8-question completion loop**: sab 8 questions clear kiye, `complete=True` aaya turn 8 pe, Interview DB row `status=completed`, `ai_score` (average) populate hua, transcript endpoint Redis se DB-backed switch ho gaya.
5. **TTS → S3 → playback**: presigned URL se real 129KB mp3 fetch kiya (`\xff\xf3` MPEG magic bytes confirm), status 200.
6. **WebSocket voice pipeline (poora real)**: OpenAI TTS se ek real spoken answer synthesize kiya (`response_format=pcm`, 24kHz), 16kHz pe resample kiya, WS pe binary chunks stream kiye — server ne webrtcvad se end-of-utterance detect kiya, Whisper se transcribe kiya (near-verbatim match), LangGraph agent ne score+next-question decide kiya, TTS reply binary audio wapas mila. Poora `audio → VAD → STT → agent → TTS` loop end-to-end verify hua.
7. **Error paths**: bad candidate/job (404), bad/expired session_id on answer (404), missing answer_text+audio_file (400), bad session on transcript (404) — sab correct.
8. **Frontend**: `tsc --noEmit` clean, `next lint` clean. Playwright (headless Chromium, `chromium-cli` available nahi tha isliye seedha `playwright` npm package use kiya) se poora browser flow: `/interview` → start → question display (category badge, timer, "Question 1 of 8") → text answer submit → score badge + transcript update + "Question 2 of 8" → Voice mode toggle (UI switch hoti hai, getUserMedia headless env me gracefully fail hota hai — real mic test already WS script se ho chuka tha) → **zero console errors** poore flow me.
9. **Bug pakड़ा during frontend dev**: `InterviewAnswerResponse.is_follow_up` "next question follow-up hai" bolta hai, na ki "abhi jo answer diya wo follow-up tha" — pehle draft me ismein exchange ko galat tag kar raha tha. `CurrentQuestion` state me `isFollowUp` explicitly track karke fix kiya.
10. **Cleanup**: sab seeded DB rows (candidate, job, 12 test interview sessions), Redis `session:*` keys, aur scratch test scripts delete kar diye. `llm_cost:*` Redis keys (shared telemetry, Module 4 se) chhod diye.

## Local Run

```
http://localhost:3000/interview   (ya jo bhi port free ho — CORS dono allow karta hai ab)
```

Candidate ID aur Job ID chahiye (parsed resume + analyzed job — Module 2/3 se). `/upload` aur `/jobs/new` se bana sakte ho.

**Local Redis zaroori hai** is module ke liye (session memory ka poora base hai) — Module 4 ke unlike, bina Redis ke yeh feature completely non-functional hoga, sirf degrade nahi.

## Aage Kya (Module 6+)

- AudioWorklet migration (ScriptProcessorNode deprecated hai, abhi kaam karta hai but future-proof nahi)
- WS reconnect/resilience agar connection beech-interview drop ho jaye
- `/interview` start page abhi raw candidate_id/job_id leta hai (jaise `/pipeline` — koi candidate-facing invite/auth flow nahi hai)
- Redis session TTL (2hr) hardcoded hai, env-configurable nahi
- Follow-up "digging deeper" ka koi UI indicator nahi (bas category badge ke aage "· follow-up" text hai)
- Test S3 audio objects (`interviews/*` prefix) cleanup nahi kiye — harmless but accumulate honge
