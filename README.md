# AI Candidate Screener
## Adaptive Voice Interview System for Job Candidate Assessment

> A production-grade, voice-first screening engine designed to evaluate candidate communication, structured explanation, and teamwork through high-fidelity adaptive conversation.

**<a href="https://ai-tutor-screener-29ln.onrender.com/" target="_blank">🚀 Live Demo</a>**

> [!IMPORTANT]
> **Reviewer Notes:**
> - **Browser:** Use **Chrome or Edge** for the full voice experience (Web Speech live preview).
> - **Cold Start:** As this is on a free tier, please allow **30-60 seconds** for the first load to "wake up" the server.
> - **Data Persistence:** The demo uses a volatile SQLite database. Records are reset during redeploys—**please export reports to PDF** to save your results permanently.
> - **Assessments:** Reports take 5-15 seconds to generate in the background after the interview ends.

---

## What It Does

A candidate visits the interview page, enters their name, and has a **10-minute voice conversation** with **Sarah**, an intelligent AI interviewer. Sarah listens, adapts her questions based on what the candidate says, and produces a detailed assessment report at the end.

- 🎙️ **Voice-first** — speak naturally; Whisper transcribes accurately
- 🧠 **Fully adaptive** — no scripted question list; LLM decides what to ask next based on the conversation
- 📊 **Structured assessment** — scored across 5 dimensions with direct quotes as evidence
- 🏁 **End early** — candidate can end any time and still get a full report
- 📋 **Admin dashboard** — all sessions, scores, pass rates at a glance

---

## System Architecture & Flow

```mermaid
graph TD
    %% Styling
    classDef candidate fill:#E52b50,stroke:#fff,stroke-width:2px,color:#fff
    classDef sarah fill:#222,stroke:#E52b50,stroke-width:2px,color:#fff
    classDef groq fill:#f2f0eb,stroke:#dcdad2,stroke-width:1px,color:#1a1816
    classDef logic fill:#fff,stroke:#1a1816,stroke-width:1px,color:#1a1816

    subgraph Frontend [User Interface]
        User((Candidate)):::candidate
        UI[Interview Screen]:::logic
    end

    subgraph STT [Voice Recognition]
        Audio[Microphone]:::logic
        Whisper[Whisper: Voice to Text]:::groq
    end

    subgraph Brain [AI Brain]
        GPT[GPT-OSS: Sarah's Personality]:::groq
        Llama[Llama: Scoring Expert]:::groq
    end

    subgraph Storage [Database & Memory]
        DB[(Secure Multi-Session Storage)]:::logic
    end

    %% Flow
    User -->|Speaking| Audio
    Audio -->|Audio Data| Whisper
    Whisper -->|Clear Text| GPT
    
    GPT <-->|Conversation Memory| DB
    GPT -->|Sarah's Response| UI
    UI -->|AI Voice| User

    %% Assessment Trigger
    GPT -->|Interview Finished| Llama
    Llama -->|Final Evaluation| DB
    DB -->|Interview Results| UI
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI (Python 3.11) + SQLAlchemy ORM + SQLite/PostgreSQL (Async) |
| **Package Manager** | `uv` |
| **Conversation LLM** | `openai/gpt-oss-120b` via Groq (Optimized for latent voice personality) |
| **Assessment LLM** | `llama-3.3-70b-versatile` via Groq (High-rigor reasoning & scoring) |
| **Voice Transcription** | Groq Whisper `whisper-large-v3-turbo` + Real-time WebSocket streaming |
| **Live Preview STT** | Web Speech API (Chrome/Edge parallel track) |
| **Real-Time Transcription** | WebSocket (`/ws/transcribe/{session_id}`) with binary audio chunking |
| **Rate Limiting** | `slowapi` — Per-IP request throttling (10/min sessions, 5/min transcribe) |
| **Authentication** | `fastapi-users` with JWT tokens (24-hour expiry) |
| **Email Notifications** | Python `smtplib` + HTML templates (Assessment complete, Bulk links) |
| **Frontend** | Modular ES6 Modules + Vanilla CSS (Editorial Parchment Theme) |
| **Deployment** | Render.com (Optimized for stateless horizontal scaling) |

---

---

## New Features & Capabilities

### 🔊 Real-Time Transcription
- **WebSocket Streaming:** `/ws/transcribe/{session_id}` accepts binary audio chunks
- **Live Updates:** Candidate sees interim transcription as they speak
- **Fallback:** Automatic Web Speech API fallback if WebSocket unavailable
- **250ms Chunking:** Audio buffered and transcribed every 2 seconds for responsiveness

### 🛡️ Production Hardening
- **Rate Limiting:** 10/min on `/api/session/message`, 5/min on `/api/transcribe` (per IP)
- **Health Checks:** Enhanced `/api/health` verifies database connectivity + system timestamp
- **Session Cleanup:** Background task every 10 minutes marks idle sessions (30+ min) as "abandoned"
- **Graceful Timeouts:** All async operations have timeouts to prevent hanging connections

### 📧 Notifications & Bulk Links
- **Email Notifications:** Assessment complete triggers email to candidate with score + report link
- **Bulk Link Generation:** Recruiters generate 1–1000 unique interview tokens in batch
- **Usage Tracking:** Each token tracked: when created, when used, by whom
- **Recruiter Dashboard:** `/api/interviews/bulk-links` shows all generated links with stats
- **HTML Templates:** Professional styled emails with call-to-action buttons

### 👑 System Owner Admin Panel & Feedback System
- **System Owner Panel (`admin.html`):** Beautiful centralized control panel restricted exclusively to superuser accounts (`is_superuser = True`).
- **Recruiter Usage Analytics:** Tracks recruiter details, company names, number of candidate accounts created, and total interview sessions run.
- **Centralized Issue Resolution Board:** Lists all bugs and feedback submitted by recruiters and candidates, allowing the system owner to manage them (Open, In Progress, Resolved).
- **Modular Floating Feedback Widget (`js/feedback.js`):** A premium floating action button (FAB) injected globally that opens a modal pre-filled with the active user's details to submit feedback asynchronously.

### 🔐 Dual-Role Authentication & Access Control (RBAC)
- **Recruiter Role**: Log in securely to the corporate dashboard to manage candidates, view assessment reports, add private decision notes, and export session data to CSV.
- **Candidate Role**: Log in with generated credentials to take the adaptive voice interview. Candidates are strictly sandboxed and cannot access reports, statistics, or administrative views.
- **System Owner (Superuser) Role**: Exclusive access to the Owner Admin Panel (`admin.html`) to oversee recruiter statistics and manage reported issues.
- **JWT Security**: 24-hour JWT token expiration with secure cookies/headers checking.

### 👥 Candidate Management & Bulk Invites
- **Text Entry Batching**: Generate up to 1,000 candidate accounts in a single click by entering a list of `email, name` pairs.
- **CSV Drag-and-Drop**: Load candidate details instantly by dragging and dropping a CSV file with automatic header parsing (`email`, `fullname`).
- **Automatic Credentials Generator**: The system automatically generates unique, readable 8-character passwords for each new candidate account.
- **One-Click Bulk Emails**: Send customized email invites containing candidate credentials in the background with a single click, or resend individual invites.
- **Company Customization**: Custom company names are captured during recruiter registration and personalized across emails and dashboards.

### 🎯 Intelligent Assessment Engine
- **5-Dimension Scoring:** Communication, Warmth, Simplification, Fluency, Fit
- **Confidence Levels:** High/Medium/Low confidence scores with evidence backing
- **Evidence Quotes:** Every score includes a direct transcript excerpt for audit trail
- **Data Quality Flags:** Automatic detection of zero data, insufficient responses, off-topic patterns
- **Adaptive Rubrics:** 4-band scoring (1-3, 4-6, 7-8, 9-10) for consistent calibration

---

## Assessment Dimensions

| Dimension | What It Measures |
|---|---|
| **Communication Clarity** | Clear, structured, easy to follow |
| **Warmth & Patience** | Collaboration and teamwork skills in team environments |
| **Ability to Simplify** | Clear explanations of complex concepts for non-technical stakeholders |
| **English Fluency** | Natural, grammatically correct speech |
| **Candidate Fit** | Overall suitability for corporate positions and culture |

Each dimension gets a score (1–10), a one-sentence justification, and a **direct quote** from the transcript as evidence.

**Recommendation:** `Move to next round` / `Consider with reservations` / `Do not move forward`

---

## Project Structure

```
ai-tutor-screener/
├── backend/
│   ├── main.py           # FastAPI routes + /api/transcribe (Whisper) + serves frontend
│   ├── conversation.py   # Dynamic InterviewEngine — LLM-driven, dimension-tracking
│   ├── assessment.py     # Structured assessment generator with transcript cleaning
│   ├── database.py       # SQLite operations (sessions, messages, assessments)
│   ├── prompts.py        # All LLM prompts (no hardcoded questions)
│   ├── config.py         # Environment config
│   └── .env.example      # Template for environment variables (API keys, models)
├── frontend/
│   ├── index.html        # Interview page (progress ring, dual timer, mic UI)
│   ├── report.html       # Assessment report (print-ready PDF)
│   ├── dashboard.html    # Admin dashboard (auto-refreshes every 30s)
│   ├── style.css         # Design system (Editorial Parchment + Dark mode config)
│   └── js/               # ES6 Modular Frontend
│       ├── api.js        # Backend fetch calls
│       ├── audio.js      # Whisper MediaRecorder + Chrome GC TTS patch
│       ├── main.js       # Core interview orchestrator
│       ├── theme.js      # Persistent OS-override theme toggle
│       └── ui.js         # DOM manipulation & typing animations
├── render.yaml           # One-click Render deployment config
└── pyproject.toml        # uv project config (Python 3.11)
```

---

## Local Setup

### Prerequisites
- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) — fast Python package manager
- A free [Groq API key](https://console.groq.com)

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```env
# Groq API (required)
GROQ_API_KEY=your_groq_api_key_here

# All three models are served via Groq — one API key handles everything
CONVERSATION_MODEL=openai/gpt-oss-120b
ASSESSMENT_MODEL=llama-3.3-70b-versatile
WHISPER_MODEL=whisper-large-v3-turbo

# Database (default: SQLite for local dev, PostgreSQL for production)
DATABASE_URL=./screener.db
# DATABASE_URL=postgresql+asyncpg://user:password@localhost/screener  # Production

# Email notifications (optional, graceful fallback if not set)
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USER=your_email@gmail.com
# SMTP_PASSWORD=your_gmail_app_password
# NOTIFICATION_EMAIL=your_email@gmail.com

# Error tracking (optional)
# SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
```

### 3. Run

```bash
cd backend
uv run uvicorn main:app --reload
```

Open **http://localhost:8000** in Chrome or Edge.

### 4. Running Tests

The project includes a comprehensive, offline-friendly test suite checking database CRUD, LangGraph state machine routing, assessment calculations, and FastAPI REST endpoints/authentication.

To execute the test suite:

```bash
uv run pytest
```

*(Note: On Windows, dynamic DLL directory pathing is automated on import to support running native C++ extensions like `greenlet` from within the virtualenv.)*

#### Optional: Enable Email Notifications
Add these variables to your `.env` file to enable automated email notifications:

```env
# Email notifications config
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_gmail_app_password
NOTIFICATION_EMAIL=your_email@gmail.com
```

##### How to set this up for free using Gmail:
1. **SMTP_HOST**: Keep as `smtp.gmail.com` (Google's free SMTP server).
2. **SMTP_PORT**: Keep as `587`.
3. **SMTP_USER**: Set to your own Gmail address (e.g., `yourname@gmail.com`).
4. **SMTP_PASSWORD**: Google does not allow apps to use your normal login password for security. Instead, generate a **free App Password** from your Google Account:
   - Go to your [Google Account Settings](https://myaccount.google.com/).
   - Ensure **2-Step Verification** is enabled for your Google account.
   - Search for **"App passwords"** in the settings search bar.
   - Select "Other (custom name)" from the app list, name it *AI Candidate Screener*, and click **Generate**.
   - Copy the 16-character passcode it generates (e.g., `abcd efgh ijkl mnop`) and paste it as the `SMTP_PASSWORD` value in your `.env` file (remove any spaces so it's a single 16-letter string: `abcdefghijklmnop`).
5. **NOTIFICATION_EMAIL**: Set to your email address where you want to receive generated bulk interview links.

Without these, the email service silently skips notification sending (no errors).

---

## Deployment (Render.com — Free)

1. Push to GitHub
2. Sign up at [render.com](https://render.com) — no credit card needed
3. **New Web Service** → connect your repo
4. Root directory: `.` (leave empty or default)
5. Build command: `pip install uv && uv sync`
6. Start command: `cd backend && uv run uvicorn main:app --host 0.0.0.0 --port $PORT`
7. Add environment variable: `GROQ_API_KEY=your_key`
8. Deploy ✅

> The `render.yaml` in the repo handles all of this automatically via Infrastructure as Code.

---

## Key Design Decisions

### No hardcoded question list
Instead of a fixed list like "Q1: tell me about yourself, Q2: explain team conflict...", the LLM receives:
- Full conversation history
- List of uncovered assessment dimensions
- What the candidate just said

It then decides **what to ask next** and **how to phrase it** based on the candidate's actual context (their background, analogies they used, experiences they mentioned).

### Dual-track voice recording
Two things run in parallel when you click the mic:
1. **MediaRecorder** — captures raw audio → sent to OpenAI-Whisper(SST model)for accurate transcription
2. **Web Speech API** — provides live preview text in the input box

Whisper result takes precedence. Web Speech text is the fallback if transcription fails.

### Production Grade Architecture
- **FastAPI Static Mounting:** Uses FastAPI's `StaticFiles` capability to "mount" and serve the entire frontend as a static directory from the root URL. This unified architecture ensures zero CORS errors, simplifies deployment on Render's free tier, and results in a highly efficient, single-unit codebase.
- **Stateless Database Backend:** The system utilizes a worker-safe SQLite persistence layer rather than volatile in-memory caches, enabling horizontal worker scaling and instant session recovery on disconnects.
- **Context Token Optimization:** Conversational routing paths are strictly injected natively as `system` messages mapping the candidate's exact turn history and runtime constraints, protecting against temporal persona-drift.
- **Garbage Collection Immunity:** Implemented global state tracking to prevent Chrome's aggressive garbage collection from terminating long `SpeechSynthesisUtterance` queries mid-sentence.
- **Modular Isolation:** The frontend separates state layers (`api.js`, `audio.js`, `ui.js`) to ensure UI and Media tracking do not mutually lock each other up.

### Zero-Framework "Vanilla" Frontend
The frontend is intentionally built using **Pure Vanilla JS** and **Vanilla CSS** instead of frameworks like **Next.js**, **React**. 
- **Lightning Performance:** Instant page loads and zero "Hydration" delay because the browser doesn't have to download and execute large JavaScript bundles typical of **Next.js** applications.
- **Free-Tier Optimized:** By avoiding a complex Node.js build step (like `next build`), the project stays extremely lightweight—critical for high reliability and fast cold-starts on Render.com's free tier.
- **Sustainability:** Uses native ES6 modules and CSS variables, ensuring the codebase is easy to maintain and future-proof without the version-locked dependencies often found in framework ecosystems.

---

## API Reference

### Public Endpoints (No Auth Required)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/session/start` | POST | Start new interview session |
| `/api/session/message` | POST | Send candidate message + get next question |
| `/api/transcribe` | POST | Transcribe audio file to text |
| `/ws/transcribe/{session_id}` | WebSocket | Real-time binary audio streaming with interim/final transcriptions |
| `/api/session/report/{session_id}` | GET | Poll for assessment report (returns `{status: "generating"|"ready", report: {...}}`) |
| `/api/session/history/{session_id}` | GET | Get interview transcript |
| `/api/feedback/report` | POST | Submit feedback/bug report |

### Protected Endpoints (Recruiter/Admin Auth Required)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/stats` | GET | Overview: total sessions, avg score, pass rate |
| `/api/sessions` | GET | List all sessions with filtering/pagination |
| `/api/sessions/{id}` | GET | Single session details |
| `/api/sessions/{id}/report` | GET | Get assessment report for session |
| `/api/sessions/{id}/notes` | POST/GET | Add/retrieve private recruiter notes |
| `/api/sessions/export/csv` | GET | Export all sessions to CSV |
| `/api/interviews/bulk-generate` | POST | Generate 1-1000 unique interview tokens in batch |
| `/api/interviews/bulk-links` | GET | List all generated bulk links with usage stats |
| `/api/health` | GET | System health (DB connectivity, timestamp) |

### Superuser Protected Endpoints (System Owner Only)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/admin/stats` | GET | Overview of all recruiters and their candidate/session usage metrics |
| `/api/admin/issues` | GET | List all submitted feedback and issue reports |
| `/api/admin/issues/{id}/status` | POST | Update status of a feedback report (open, in_progress, resolved) |

---

## Database Schema (Phase 1)

| Model | Purpose | Key Fields |
|-------|---------|-----------|
| `User` | Recruiter/admin accounts | id, email, hashed_password, role, is_active |
| `Organization` | Company context | id, name, created_at |
| `Session` | Interview session | id, candidate_name, status, state (JSON), created_at, completed_at |
| `Message` | Conversation history | id, session_id, role, content, timestamp |
| `Assessment` | Evaluation report | id, session_id, report_json (full 5-dim score), recommendation, overall_score |
| `SessionNote` | Private recruiter notes | id, session_id, created_by_id, content |
| `BulkLink` | Bulk-generated interview tokens | id, token (unique), batch_label, created_by_id, session_id (used?), created_at, used_at |

### Assessment Prompt Architecture (Phase 4)
All prompts follow a **modular, single-job** philosophy:
- `SARAH_SYSTEM` — Core persona injected as system message (max 2-3 sentences per response)
- `QUESTION_PROMPT` — Generates ONE natural follow-up question based on dimension + last answer
- `PROBE_PROMPT` — Surgical 1-2 sentence follow-up for insufficient/vague answers
- `REDIRECT_PROMPT` — Warm redirect for off-topic answers
- `DONT_KNOW_PROMPT` — Graceful pivot after "I don't know" twice
- `ASSESSMENT_PROMPT` — Structured evaluation with 5-dimension rubrics, confidence levels, evidence quotes, flags
- `build_rubric_string()` — Dynamically formats rubrics into prompt injection (no hardcoded scoring anchors)

**Philosophy:** "Code owns decisions, LLM only generates words" — no routing or branching logic inside prompts.

### Code-Owns-Decisions Core Implementation
To ensure maximum reliability and predictability, all business rules and assessment calculations are owned by Python code, not the LLM:
- **Score Clamping:** All dimension scores parsed from LLM JSON are clamped to `[1.0, 10.0]` range.
- **Python-Calculated Averages:** Overall score is dynamically calculated as the average of the 5 dimensions inside Python, ignoring the LLM's self-calculated overall score.
- **Deterministic Recommendation:** Hiring recommendations are calculated via strict score thresholds:
  - `>= 7.5` → `"Move to next round"`
  - `5.0–7.4` → `"Consider with reservations"`
  - `< 5.0` → `"Do not move forward"`
- **Evidence-Based Confidence Overrides:** Confidence per dimension is overridden in code based on keyword and candidate word-count evidence in the transcript:
  - `High` → `>= 80` candidate words referencing the dimension's domain.
  - `Medium` → `20` to `79` candidate words.
  - `Low` → `< 20` candidate words. If 3+ dimensions have low confidence, the `"insufficient_data"` flag is added automatically.

### Adaptive Time-Limit Control
- **Countdown Enforcement:** The backend parses the `"MM:SS"` countdown timer from the frontend on every message.
- **Server-Side Force Wrap-Up:** If the timer reaches `30 seconds` or less, the system halts normal questions and triggers an immediate, server-side wrap-up to conclude the interview gracefully.

### Assessment Transcript Cleaning & Integrity
Before sending to the assessment LLM, the transcript is cleaned:
- `[Candidate chose to end interview early]` markers removed
- Repeat requests (`"can you repeat that?"`) filtered out
- **Zero-Data Guardrail:** If the transcript contains no substantive candidate response, the system triggers an automatic fail without calling the LLM to prevent hallucinations.
- **Data Sufficiency Check:** Minimum word count and turn-count checks ensure the LLM has evidence before scoring.
- **Flags Array:** Data quality issues tracked: `zero_data_detected`, `insufficient_data`, `limited_transcript`, `assessment_parsing_error`, `off_topic_heavy`
- **Evidence Quotes:** Every score backed by a direct transcript quote for auditability

---

## Edge Cases Handled

| Situation | How It's Handled |
|---|---|
| "Can you repeat that?" | Intercepted in Python — warmly repeats the last question immediately without calling the LLM |
| "I don't know" (repeated) | After 2 in a row, Sarah moves on gracefully without pressure |
| Candidate ends early | Immediate wrap-up + report generated from partial interview |
| Very short answer (< 12 words) | Classified as `short` → follow-up question triggered |
| Whisper transcription fails | Falls back to Web Speech accumulated text |
| Server restart mid-session | Engine state rebuilt from DB on reconnect (Session Persistence) |
| Non-Chrome browser | Warning banner shown; text input always available as fallback |
| Interview has no data | **Hard-Fail Guardrail** → No hallucinated reports; score set to 0.0 |
| PDF Export in Dark Mode | High-contrast Print Media overrides ensure black text on white paper |

---

*Built and documented with the strategic help of **Google Antigravity** and **Claude AI**.*


