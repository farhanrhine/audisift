# Audisift — Full Upgrade Plan
## For Claude Code Execution

> **Goal:** Transform the current prototype into a production-grade, real-world hiring tool.
> **Rules:** SQLite locally, PostgreSQL in production. Email/password auth. No breaking changes to existing interview flow.

---

## PHASE 1 — Database Migration (SQLite → SQLAlchemy ORM)

**Why first:** Everything else (auth, multi-tenancy, ATS) depends on a proper DB layer.

### 1.1 — Install new dependencies

Add to `pyproject.toml`:
```
sqlalchemy>=2.0
alembic
fastapi-users[sqlalchemy]
asyncpg          # PostgreSQL async driver (production)
aiosqlite        # SQLite async driver (local)
python-jose[cryptography]
passlib[bcrypt]
python-multipart
```

### 1.2 — Rewrite `database.py` using SQLAlchemy ORM

Replace all raw SQL with SQLAlchemy models. Keep the same table structure but add proper relationships:

**Tables to define as ORM models:**
- `User` — id, email, hashed_password, full_name, is_active, is_superuser, is_verified, created_at, role (recruiter / admin)
- `Organization` — id, name, created_at (for future multi-tenant support, add now)
- `Session` — id, candidate_name, candidate_email, status, created_at, completed_at, organization_id (FK)
- `Message` — id, session_id (FK), role, content, timestamp
- `Assessment` — id, session_id (FK, unique), scores JSON, recommendation, summary, created_at

**Connection string logic in `config.py`:**
```python
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./audisift.db")

# Fix Render's legacy postgres:// URL format
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
```

### 1.3 — Add Alembic for migrations

```bash
alembic init alembic
```

Configure `alembic.ini` and `alembic/env.py` to read `DATABASE_URL` from environment and use the SQLAlchemy models. This allows `alembic upgrade head` to create tables on both SQLite and PostgreSQL without writing SQL by hand.

---

## PHASE 2 — Authentication System (fastapi-users)

### 2.1 — User model and auth setup

Create `backend/auth.py`:

- Use `fastapi-users` with SQLAlchemy async adapter
- JWT strategy — tokens expire in 24 hours
- Cookie transport (easier for browser-based app, no manual header handling)
- Two roles: `recruiter` (default) and `admin`

**Endpoints fastapi-users provides automatically:**
```
POST /auth/register       → create account (email + password + full_name)
POST /auth/login          → returns JWT cookie
POST /auth/logout         → clears cookie
GET  /users/me            → current user info
PATCH /users/me           → update profile
```

### 2.2 — Protect existing routes

Add `current_active_user` dependency to:
- `GET /dashboard` — any logged-in recruiter
- `GET /api/sessions` — any logged-in recruiter
- `GET /api/sessions/{id}/report` — any logged-in recruiter
- `DELETE /api/sessions/{id}` — admin only
- `GET /api/stats` — any logged-in recruiter

**Interview routes stay PUBLIC** (no login required):
- `GET /` — interview page (candidate visits this)
- `POST /api/session/start`
- `POST /api/chat`
- `POST /api/transcribe`
- `POST /api/session/{id}/end`

Reason: Candidates are external users — they should never need an account.

### 2.3 — Frontend auth pages

Create these new HTML pages in `frontend/`:

**`login.html`**
- Email + password form
- "Don't have an account? Register" link
- Error message display on bad credentials
- On success → redirect to `dashboard.html`
- Editorial Parchment theme, same design system as rest of app

**`register.html`**
- Full name + email + password + confirm password
- Client-side validation (passwords match, email format)
- On success → redirect to `login.html` with success message

**`auth.js`** (new JS module in `frontend/js/`):
- `login(email, password)` → POST to `/auth/login`
- `register(data)` → POST to `/auth/register`
- `logout()` → POST to `/auth/logout` → redirect to login
- `checkAuth()` → GET `/users/me` → if 401, redirect to login
- Call `checkAuth()` at top of `dashboard.js` and any protected page

### 2.4 — Navigation update

Add to `dashboard.html` header:
- Logged-in user's name (from `/users/me`)
- Logout button (calls `auth.js logout()`)

---

## PHASE 3 — LangGraph Interview Brain

**Why:** Current interview engine is a simple loop — one LLM call per turn with the full history. No real state tracking, no intelligent dimension routing, no probing logic. LangGraph makes the interview actually adaptive.

### 3.1 — Install LangGraph

```
langgraph
langchain-core
langchain-groq
```

### 3.2 — Rewrite `conversation.py` as a LangGraph state machine

**State schema:**
```python
class InterviewState(TypedDict):
    session_id: str
    candidate_name: str
    messages: list[BaseMessage]
    dimensions_covered: list[str]      # which of the 5 have been assessed
    dimensions_scores: dict[str, int]  # running soft scores per dimension
    follow_up_count: int               # how many follow-ups in a row
    short_answer_count: int            # consecutive short answers
    current_dimension: str             # what Sarah is currently probing
    turn_count: int
    interview_complete: bool
    end_reason: str                    # "natural" | "early" | "max_turns"
```

**Nodes:**
1. `route_node` — decides which dimension to probe next based on `dimensions_covered` and conversation so far
2. `question_node` — generates Sarah's next question for the chosen dimension (LLM call)
3. `probe_node` — if last answer was short/weak, generates a follow-up probe instead of moving on
4. `wrap_up_node` — generates Sarah's closing when interview is complete
5. `score_node` — updates soft dimension scores based on latest candidate turn

**Edges (conditional routing):**
```
START → route_node
route_node → question_node (normal flow)
route_node → wrap_up_node (all dimensions covered OR max turns hit)
question_node → END (return Sarah's response to API)

On next candidate message:
START → score_node → probe_node (if short answer) OR route_node (if sufficient answer)
```

### 3.3 — Probing logic

In `probe_node`:
- If candidate answer < 20 words → trigger one follow-up probe ("Can you walk me through a specific example?")
- If candidate says "I don't know" twice in a row → gracefully move to next dimension
- If candidate gives a strong answer → mark dimension as covered and route to next

### 3.4 — Persist LangGraph state to DB

After every node execution, serialize `InterviewState` to JSON and store in the `Session` table. On reconnect, deserialize and continue. This replaces the current in-memory `sessions` dict which breaks on server restart.

---

## PHASE 4 — Upgraded Assessment Engine

### 4.1 — Rubric-based scoring in `assessment.py`

Replace vague 1-10 scoring with rubric anchors. Pass rubrics into the assessment LLM prompt:

```
Communication Clarity:
  1-3: Disorganized, hard to follow, frequent self-corrections
  4-6: Generally clear but occasional ambiguity or long pauses
  7-9: Consistently structured, easy to follow
  10:  Exceptionally clear with natural signposting

Warmth & Patience:
  1-3: Mechanical or cold tone, no empathy signals
  4-6: Polite but not warm, empathy is procedural
  7-9: Genuine warmth, uses encouraging language naturally
  10:  Remarkably warm, would make students feel safe immediately
```

Same pattern for all 5 dimensions. Include rubrics in the LLM system prompt.

### 4.2 — Add confidence score to assessment output

Extend assessment JSON schema:
```json
{
  "dimensions": {
    "communication_clarity": {
      "score": 7,
      "confidence": "high",     // high | medium | low
      "justification": "...",
      "evidence_quote": "..."
    }
  },
  "overall_score": 6.8,
  "recommendation": "Move to next round",
  "flags": ["short_answers_detected", "repeated_i_dont_know"],
  "summary": "..."
}
```

If `confidence` is `low` for 3+ dimensions → add `"insufficient_data"` flag to report.

### 4.3 — Comparative ranking (future-ready)

Add `percentile_rank` field to Assessment model (nullable for now). Once 10+ assessments exist in the DB, calculate percentile on report generation: "This candidate scored better than 73% of assessed candidates."

---

## PHASE 5 — ATS Dashboard Upgrade

### 5.1 — Backend API additions

New endpoints (all protected, require login):

```
GET  /api/stats                    → total sessions, avg score, pass rate, this week's count
GET  /api/sessions?status=&score_min=&score_max=&recommendation=&search=
     → filtered + paginated session list
GET  /api/sessions/{id}/report     → full assessment JSON
DELETE /api/sessions/{id}          → admin only, hard delete
GET  /api/sessions/export/csv      → download all sessions as CSV
POST /api/sessions/{id}/notes      → recruiter adds private note to a session
GET  /api/sessions/{id}/notes      → get notes for a session
```

### 5.2 — Dashboard UI overhaul (`dashboard.html`)

**Top stats bar:**
- Total candidates screened
- Average score (across all sessions)
- Pass rate (% "Move to next round")
- This week's count

**Filters bar:**
- Search by candidate name/email
- Filter by recommendation (all / move forward / reservations / reject)
- Filter by score range (slider: 0-10)
- Filter by date range

**Candidate table columns:**
- Name, Email, Date, Duration, Overall Score (colored badge), Recommendation, Actions

**Actions per row:**
- View Full Report
- Add Note
- Delete (admin only)

**Export button:**
- "Export CSV" → calls `/api/sessions/export/csv` → downloads file

### 5.3 — Report page upgrade (`report.html`)

- Add recruiter notes section (if logged in)
- Show `flags` from assessment (e.g., "⚠️ Insufficient data detected")
- Show confidence level per dimension
- Add "Compare with other candidates" link (future)
- Print/PDF export already works — keep it

---

## PHASE 6 — Real-time WebSocket Transcription

**Why:** Current flow is: record audio → stop recording → upload to Whisper → wait → show text. Laggy. Replace with streaming.

### 6.1 — Backend WebSocket endpoint

```python
@app.websocket("/ws/transcribe/{session_id}")
async def transcribe_ws(websocket: WebSocket, session_id: str):
    # Accept connection
    # Receive audio chunks as binary frames
    # Buffer chunks, send to Whisper every 2-3 seconds
    # Send transcription back as text frame
    # Keep connection alive for full interview duration
```

### 6.2 — Frontend `audio.js` update

Replace `MediaRecorder stop → fetch` pattern with:
- Open WebSocket on interview start
- Stream audio chunks via `websocket.send(chunk)` every 2 seconds
- Receive partial transcriptions, update input box live
- On mic stop → send end signal → receive final transcription
- Keep Web Speech API as visual fallback only (no longer primary)

---

## PHASE 7 — Reliability & Production Hardening

### 7.1 — Session timeout handling

In `conversation.py`:
- If a session has no new messages for 30 minutes → mark as `abandoned`
- Background task (APScheduler or FastAPI lifespan) runs every 10 minutes to clean up abandoned sessions

### 7.2 — Rate limiting

Install `slowapi`:
```python
# Limit per IP
@limiter.limit("10/minute")  # on /api/chat
@limiter.limit("5/minute")   # on /api/transcribe
@limiter.limit("3/minute")   # on /auth/register
```

### 7.3 — Error telemetry

Add Sentry:
```
sentry-sdk[fastapi]
```

```python
sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), traces_sample_rate=0.2)
```

SENTRY_DSN is optional env var — if not set, Sentry is disabled. Free tier handles the load.

### 7.4 — Health check endpoint

```python
@app.get("/health")
async def health():
    # Check DB connection
    # Return {"status": "ok", "db": "ok", "timestamp": ...}
```

Render uses this for uptime monitoring.

### 7.5 — Keep-alive for free tier

Add a `keep_alive.py` script that pings `/health` every 10 minutes. Run it as a separate Render cron job (free). Eliminates cold starts during active demo periods.

---

## PHASE 8 — Notification System (Lightweight)

### 8.1 — Email notifications via SMTP

When a report is ready:
- Send email to the recruiter who owns the session (or the org admin)
- Use Python's built-in `smtplib` + Gmail SMTP (free)
- Template: "Candidate [Name] has completed their screening. Overall score: X/10. Recommendation: [...]"

New env vars:
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=app_password_here   # Gmail App Password, not account password
NOTIFICATION_EMAIL=recruiter@company.com
```

If SMTP vars not set → skip notification silently (optional feature).

### 8.2 — Bulk interview link generation

New endpoint:
```
POST /api/interviews/bulk-generate
Body: { "count": 50, "label": "May 2026 Batch" }
Returns: list of unique interview URLs
```

Each URL is a one-time token tied to a session slot. Recruiter generates links, pastes into email, sends to candidates. Dashboard shows which links were used vs pending.

---

## EXECUTION ORDER FOR CLAUDE CODE

Run phases in this exact order. Do not skip ahead.

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 8
```

After each phase:
1. Run the app locally (`uv run uvicorn main:app --reload`)
2. Confirm no errors in terminal
3. Confirm existing interview flow still works
4. Then proceed to next phase

---

## Environment Variables (Final `.env.example`)

```env
# Database
DATABASE_URL=sqlite+aiosqlite:///./audisift.db   # local default

# AI Models (Groq)
GROQ_API_KEY=your_groq_api_key
CONVERSATION_MODEL=openai/gpt-oss-120b
ASSESSMENT_MODEL=llama-3.3-70b-versatile
WHISPER_MODEL=whisper-large-v3-turbo

# Auth (JWT)
SECRET_KEY=generate_a_random_64_char_string_here
JWT_LIFETIME_SECONDS=86400

# Email Notifications (optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
NOTIFICATION_EMAIL=

# Monitoring (optional)
SENTRY_DSN=
```

---

## Render Production Setup (Updated)

1. Add PostgreSQL database from Render dashboard (free tier)
2. Render auto-sets `DATABASE_URL` env var pointing to the PostgreSQL instance
3. Add `SECRET_KEY` env var (generate with `openssl rand -hex 32`)
4. Add `GROQ_API_KEY`
5. Build command: `pip install uv && uv sync && alembic upgrade head`
6. Start command: `cd backend && uv run uvicorn main:app --host 0.0.0.0 --port $PORT`

The `alembic upgrade head` in the build command auto-runs migrations on every deploy.

---

## What This Becomes After All 8 Phases

- A recruiter signs up, gets an account
- They generate a batch of interview links and send to candidates
- Each candidate visits their link, completes the voice interview with Sarah (LangGraph brain, actually adaptive)
- Report auto-generates with rubric-based scores, confidence flags, evidence quotes
- Recruiter logs into dashboard, sees all candidates, filters by score, adds notes, exports CSV
- Gets email when each report is ready
- Entire thing runs on Render free tier with PostgreSQL

That is a real product. Not a demo.
