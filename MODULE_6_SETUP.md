# Module 6: Feedback Report Generator + PDF Scorecard

Interview complete hone ke baad ek GPT-4o structured-output report banta hai (few-shot calibrated), phir usse ek PDF scorecard (reportlab + matplotlib chart) me render karke S3 pe upload, aur ek beautiful report page (donut + radar chart) se view/download/email-share kar sakte hain.

## Folder Structure (naya)

```
backend/app/
├── agents/
│   └── report_agent.py          # GPT-4o structured output, 2 few-shot calibration examples
├── api/v1/routes/
│   └── report.py                # generate/get/{id}/pdf/{id}/share
├── models/
│   └── report.py                # Report table (report_data JSON, pdf_s3_key)
├── schemas/
│   └── report.py                # ReportSchema (spec ke exact fields) + request/response models
├── services/
│   ├── pdf_service.py           # reportlab PDF + matplotlib skill bar chart
│   └── email_service.py         # SendGrid share email
frontend/
├── app/report/[reportId]/page.tsx   # donut chart, radar chart, recommendation badge, expandable sections
└── types/report.ts
```

## Kya Setup Hua

### Report Generation (`report_agent.py`)

Ek GPT-4o `with_structured_output(ReportSchema)` call, jisme prompt ke andar **2 few-shot example reports** hain — ek "Strongly Hire" (strong senior candidate, specific answers) aur ek "Reject" (candidate couldn't answer even after follow-up). Do examples isliye chuне taaki model sirf ek tarah ke (sab positive) reports na de, balki scoring scale ko dono extremes se calibrate kare. Input: `resume_data` (skills, experience) + `jd_data` (title, required_skills) + `interview_exchanges` (Module 5 ke `Interview.ai_feedback['exchanges']` — poora Q&A + per-answer score/feedback) + `match_score` (Module 3/4 ke `Application.match_score`, agar available ho).

`ReportSchema` task ke exact spec ke fields follow karta hai (`overall_score`, `recommendation`, `technical_assessment`, `communication_assessment`, `culture_fit`, `skill_breakdown`, `interview_highlights`, `suggested_next_steps`, `red_flags`) — bas do jagah types tighten kiye: `recommendation` aur `skill_breakdown[].proficiency_level` ko `Literal` types banaya (task ne informally "Strongly Hire | Hire | Hold | Reject" diya tha, use hi Pydantic `Literal` me convert kiya taaki frontend radar chart proficiency ko reliably numeric map kar sake).

### PDF Generation (`pdf_service.py`)

**reportlab chuna** (weasyprint nahi) — task "reportlab ya weasyprint" bola tha, weasyprint Windows pe GTK3/Cairo native libs maangta hai jo is machine pe nahi hain, reportlab pure-Python hai aur bina kisi native dependency ke chalta hai.

- Skill breakdown ke liye matplotlib se ek horizontal bar chart banta hai (`proficiency_level` → 1-4 numeric scale), `Agg` backend (headless, no display) use karke PNG me render hota hai, phir reportlab `Image` flowable se PDF me embed hota hai.
- **Company logo aur candidate photo dono placeholders hain** — task ne "company logo placeholder" explicitly bola (wahi diya: grey box "COMPANY LOGO" text). Lekin "candidate photo (from S3)" ke liye — is app me kabhi bhi candidate photo upload/storage feature hi nahi bana (Module 1-5 me sirf resume file store hota hai, koi photo field candidate model me nahi hai). Real photo fabricate karne ke bajaye, ek circular initials-avatar placeholder banaya (jaise "AM" for Arjun Mehta) — agar photo upload feature future me add ho to yahi jagah wire ho sakta hai.
- Recommendation badge color-coded hai (Strongly Hire=green, Hire=lime, Hold=amber, Reject=red) — frontend ke badge colors se match karta hai.

PDF S3 pe `reports/{report_id}/scorecard.pdf` key se upload hota hai (naya `s3_service.upload_report_pdf()`), presigned URL on-demand generate hota hai (stored URL nahi — expire ho sakta hai, isliye har `/pdf` aur `/share` call pe fresh presign hota hai).

### Email Share (`email_service.py`)

SendGrid SDK use kiya. **`SENDGRID_API_KEY` is machine pe configured nahi hai** (baaki sab keys — OpenAI, Groq, AWS, DB — configured the, yeh nahi) — isliye actual email delivery real test nahi ho payi. Jo verify hua: missing-key case cleanly `EmailNotConfiguredError` → route `503 "Email sharing is not configured on this server"` deta hai (frontend me bhi yeh gracefully dikhta hai, crash nahi hota) — real Playwright test se confirm kiya ki poora error-handling path (backend se frontend tak) sahi kaam karta hai. Agar `SENDGRID_API_KEY` set ho jaaye to `send_report_share_email()` turant kaam karega (koi aur code change nahi chahiye) — bas live send verify nahi ho paya.

### Frontend (`app/report/[reportId]/page.tsx`)

- **Donut chart**: recharts `PieChart` (2 segments: score + remainder), center me overlay text (`{score}/10`) — recharts khud center-label support nahi karta cleanly, isliye ek absolutely-positioned div overlay use kiya.
- **Radar chart**: recharts `RadarChart`, skill_breakdown ke `proficiency_level` ko 1-4 scale pe map kiya.
- Expandable sections (Technical/Communication/Culture Fit) — koi Accordion primitive is codebase me pehle se nahi thi, ek chhota `ExpandableSection` component banaya.
- **Print-friendly CSS**: Tailwind ke `print:` variants use kiye (custom `@media print` block ki jagah — codebase already Tailwind-first hai). Buttons/share-form `print:hidden`, aur expandable sections print time pe **force-open** (`print:!block` overriding `hidden`) taaki collapsed sections bhi printed page me poori dikhein.

## Design Decisions / Task Se Deviations

1. **reportlab, not weasyprint** — Windows native-dependency issue (upar explained).
2. **`Report` naya DB table** — task explicitly nahi bola tha, lekin `GET /report/{report_id}` implies persistence (baad me bhi retrieve hona chahiye), isliye ek chhota model banaya (`report_data` JSON + `pdf_s3_key` + denormalized `overall_score`/`recommendation` for quick filtering later).
3. **Candidate photo → initials placeholder**, real photo nahi (upar explained — feature hi exist nahi karta).
4. **`total_questions`/`question_index` jaisa Module 5 me, yahan bhi ek chhota schema addition**: koi nahi actually — is module me koi aisa nahi tha.
5. **PDF download: pre-fetch presigned URL on page load, not on click** — pehle click-time-fetch-then-`window.open()` try kiya, lekin real browsers (aur Playwright ne bhi yehi confirm kiya) `window.open()` ko sirf synchronous user-gesture context ke andar allow karte hain; ek `await` ke baad call karne se popup silently block ho sakta hai. Fix: report load hote hi presigned URL background me fetch kar lete hain, "Download PDF" button tabhi enable hota hai jab URL ready ho — click par seedha synchronous `window.open(pdfUrl)`.

## Verification Kya Kiya

Sab real APIs se (GPT-4o, Groq, real S3, real Neon Postgres, real Redis) — koi mock nahi. Ek existing Module 5 interview flow reuse kiya (candidate seed → interview start → 8 turns complete → phir report generate).

1. **Real report generation**: "Arjun Mehta" (6yrs, Kubernetes+FastAPI+PostgreSQL skills) vs "Senior Backend Engineer" role — 8-question interview poore strong answers se complete kiya, `POST /report/generate` call kiya. Result: `overall_score=9.2`, `recommendation="Strongly Hire"` — few-shot Example 1 (jo bhi strong-candidate calibration tha) ke साथ genuinely consistent tha, generic/templated nahi laga.
2. **PDF visually inspect kiya** (Read tool se PDF render karke dekha) — header (logo placeholder + candidate initials avatar), score badge (color-coded green "STRONGLY HIRE"), sab assessment sections, matplotlib skill chart (4 skills, sahi proficiency bars), highlights, next steps — sab professionally laid out. Ek minor cosmetic issue notice kiya: "Suggested Next Steps" page 2 pe akela spill ho jaata hai (thoड़ा white space waste) — functionality par asar nahi, layout-tightening ka scope future me hai.
3. **PDF → S3 → presigned URL → real fetch**: 28KB `%PDF-` magic bytes confirm kiya.
4. **Error paths**: incomplete interview pe report generate (`400 "not completed yet"`), non-existent session (`404`), non-existent report (`404`), invalid email format (`422` Pydantic `EmailStr` validation), missing SendGrid key pe share (`503`) — sab test kiye, sab correct.
5. **Ek real backend hang mila aur confirm kiya ki wo Module 6 ka bug nahi hai**: interview-answer flow (Module 5 se) ke andar OpenAI TTS call ek baar 3+ minute tak hang ho gaya — server logs se confirm kiya ki yeh OpenAI API side ka transient issue tha (turant pehle hi ek 503 aaya tha jo auto-retry se recover hua, phir agla call bina kisi error/response ke hi latak gaya), server ka baaki hissa (health check, doosre requests) bilkul theek chal raha tha isi waqt — matlab genuine external API flakiness thi, koi deadlock/bug nahi. Server restart karke retry kiya, phir sab kaam kar gaya.
6. **Frontend**: `tsc --noEmit` clean, `next lint` clean. Playwright se poora flow: report page load (donut + radar charts render), Communication Assessment expand kiya, Share via Email form (real 503 error gracefully dikha), aur **Download PDF ek asli bug pakड़ा aur fix kiya**:
   - Pehla version: click ke baad `await fetch → window.open()` — Playwright ne confirm kiya popup blocked ho raha tha (`page.waitForEvent('popup')` kuch nahi milta tha) — yeh exact wahi cheez hai jo real Chrome bhi karta hai.
   - Fix try kiya (hidden `<a>` + programmatic click) — abhi bhi popup.url() weird behavior dikhata raha, deep debug kiya.
   - **Root cause mila**: PDF URL pe navigate karna Chromium ko ek *file download* trigger karta hai, page-navigation nahi — isliye Playwright ka `popup.url()`/`page.goto()` navigation-tracking APIs isse "navigation" nahi maante (`page.goto` error: "Download is starting"). Yeh bug nahi tha, feature sahi kaam kar raha tha!
   - Phir bhi ek genuine improvement kiya: presigned URL ko page-load pe hi pre-fetch karna (upar Design Decisions #5) — better UX aur zyada robust popup-blocking-proof pattern, dono.
   - Final confirm: Playwright ke `page.waitForEvent('download')` se — real 28KB PDF download hua, `scorecard.pdf` filename, `%PDF-` magic bytes.
   - **Zero console errors** poore flow me (sirf expected 503 email-share error, jo intentionally surfaced hota hai).
7. **Print-CSS verify kiya**: `page.emulateMedia({media: 'print'})` se screenshot liya — Share/Download buttons hidden, saare expandable sections force-open (collapsed hone ke bawajood print me poora content dikhta hai).
8. **Cleanup**: seeded candidates/jobs/applications/interviews/reports DB se delete kiye, Redis `session:*` keys clear kiye, sab scratch test scripts remove kiye.

## Local Run

```
http://localhost:3000/report/{report_id}   (report_id POST /report/generate se milta hai)
```

Pehle ek Module 5 interview complete karo (`/interview` se), phir `POST /api/v1/report/generate` with `{"session_id": "<interview_id>"}`.

**Email sharing kaam karne ke liye** `backend/.env` me `SENDGRID_API_KEY` aur `SENDGRID_FROM_EMAIL` set karne honge (abhi khaali hain — feature code-complete hai, credentials nahi).

## Aage Kya (Module 7+)

- Candidate photo upload feature (agar chahiye) — abhi sirf initials placeholder
- SendGrid live-send verify (API key milne ke baad)
- PDF pagination tightening (Suggested Next Steps ka page-2 spill)
- Report page se seedha "Generate Report" trigger karna interview-complete screen se (abhi `/report/generate` sirf API hai, koi UI button nahi jo automatically interview complete hone par trigger kare)
- Report history / list view per candidate (abhi sirf direct report_id se access hota hai)
