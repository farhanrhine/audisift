# Audisift — Product Roadmap & Improvement Plan

**Last Updated:** June 2026  
**Current Version:** 1.0.0  
**Live:** https://audisift.onrender.com

---

## Phase 1 — Core Quality (This Week)
> Low effort, high impact. Ship fast.

### P1-1 · Role Archetype System (Weighted Dimension Scoring)
**Inspiration:** Career-Ops classifies job types (LLMOps / PM / SA) and weights scoring per archetype.  
**Our equivalent:** Recruiters pick a role type when creating an interview — Sarah's questions and scoring weights adapt automatically.

**Archetypes to support:**
| Archetype | Boosted Dimensions |
|-----------|-------------------|
| Software Engineer | Structured Explanation, English Fluency |
| Sales / BD | Communication Clarity, Culture Fit |
| People Manager | Collaboration & Teamwork, Culture Fit |
| Customer Support | Communication Clarity, English Fluency |
| Product / Design | Structured Explanation, Candidate Fit |
| General / Default | All equal (current behavior) |

**Changes needed:**
- `backend/models.py` — add `role_archetype` field to `InterviewSession`
- `backend/conversation.py` — load dimension weights from archetype config
- `backend/prompts.py` — archetype-aware `SARAH_SYSTEM` prefix
- `backend/assessment.py` — apply weights to final dimension scores
- `frontend/dashboard.html` — archetype dropdown when sending invite links
- `frontend/candidates.html` — archetype selector on bulk invite

**Effort:** 2–3 days  
**Impact:** Reports become role-specific, not generic. Huge quality jump.

---

### P1-2 · STAR Story Extraction in Reports
**Inspiration:** Career-Ops accumulates STAR+Reflection behavioral stories across evaluations.  
**Our equivalent:** Auto-detect and surface STAR stories from the interview transcript in the report.

When a candidate narrates a story (detectable by past-tense, "I once…", "There was a time…", team/project references), extract:
- **Situation** — context
- **Task** — what they were responsible for
- **Action** — what they did
- **Result** — outcome

Display as collapsible STAR cards in `report.html` above the raw transcript.

**Changes needed:**
- `backend/assessment.py` — LLM pass to extract STAR stories from transcript
- `frontend/report.html` — STAR card UI component
- `backend/models.py` — add `star_stories: JSON` field to `Assessment`

**Effort:** 1–2 days  
**Impact:** Recruiters can scan behavioral evidence instantly without reading full transcript.

---

### P1-3 · Human Interviewer Prep Kit
**Inspiration:** Career-Ops generates interview prep questions for job seekers.  
**Our equivalent:** After Sarah's AI interview, the report includes a **5-question follow-up guide** for the human interviewer, targeting gaps identified in Sarah's assessment.

Example output in report:
> **Suggested Follow-Up Questions for Human Interview:**
> 1. Candidate was vague on conflict resolution → *"Tell me about a time you disagreed with your manager. What happened?"*
> 2. Structured Explanation scored 4/10 → *"Walk me through how you'd architect a system to handle 1M daily users."*

**Changes needed:**
- `backend/assessment.py` — generate `follow_up_questions` array in report JSON
- `frontend/report.html` — "Human Interviewer Prep Kit" section in report UI

**Effort:** 1 day  
**Impact:** Bridges AI pre-screen → human interview. Makes Audisift a complete hiring workflow tool.

---

## Phase 2 — Recruiter Dashboard (Next 2 Weeks)
> Makes Audisift a proper ATS-lite, not just an interview widget.

### P2-1 · Candidate Pipeline Stages
**Inspiration:** Career-Ops has a visual pipeline TUI (Apply → Applied → Interview → Offer).  
**Our equivalent:** Recruiter-side pipeline with drag-able status columns.

**Stages:**
```
Invited → Interview Started → Completed → Under Review → Shortlisted → Rejected → Hired
```

**Changes needed:**
- `backend/models.py` — add `pipeline_stage` field to `InterviewSession`
- `backend/main.py` — `PATCH /api/session/{id}/stage` endpoint
- `frontend/dashboard.html` — Kanban-style column view or stage filter tabs
- `frontend/candidates.html` — stage badge per candidate row

**Effort:** 2–3 days  
**Impact:** Recruiters can manage a full hiring funnel inside Audisift.

---

### P2-2 · Side-by-Side Candidate Comparison
**Inspiration:** Career-Ops batch-evaluates 10 job offers in parallel for comparison.  
**Our equivalent:** Recruiter selects 2–4 candidates and sees their scores side-by-side with a radar chart.

**URL pattern:** `/compare.html?sessions=id1,id2,id3`

**UI:** 
- Radar chart overlaying all selected candidates' dimension scores
- Score table with delta highlighting (green = best, red = weakest per dimension)
- Side-by-side recommendation banners

**Changes needed:**
- `frontend/compare.html` — new page
- `backend/main.py` — `GET /api/sessions/compare?ids=...` bulk report endpoint
- `frontend/dashboard.html` — checkbox selection + "Compare" action button

**Effort:** 2 days  
**Impact:** Makes shortlisting fast and data-driven.

---

### P2-3 · Recruiter Decision Notes (Private Annotations)
Keep current feature but improve:
- Sticky notes per candidate visible only to the recruiter
- "Internal Rating" (1–5 stars) separate from AI score
- Notes searchable from dashboard

**Effort:** 1 day  
**Impact:** Recruiters trust the tool more when they own the final decision.

---

## Phase 3 — Intelligence Layer (Month 2)
> Pre-interview context + smarter AI = dramatically better assessments.

### P3-1 · Pre-Interview CV/LinkedIn Context
**Inspiration:** Career-Ops does deep company research before applying. Flip it: research the candidate before interviewing.

If recruiter pastes a LinkedIn URL or uploads a CV PDF when creating a candidate:
- Extract: current role, years of experience, skills, career trajectory
- Feed this context to Sarah at session start
- Sarah references their background in questions

Before:
> *"Could you tell me about yourself?"*

After (with CV context):
> *"I can see you've been at Infosys for 3 years as a backend engineer. What led you to explore new opportunities now?"*

**Changes needed:**
- `backend/main.py` — CV upload endpoint, PDF text extraction (`PyMuPDF`)
- `backend/models.py` — `cv_summary` field on `InterviewSession`
- `backend/conversation.py` — inject CV context into `SARAH_SYSTEM`
- `frontend/candidates.html` — CV/LinkedIn URL field per candidate

**Effort:** 3–4 days  
**Impact:** Most valuable feature upgrade. Interview quality becomes dramatically more relevant.

---

### P3-2 · Server-Side PDF Report Generation
**Inspiration:** Career-Ops generates ATS-optimized CVs via Playwright + HTML template.  
**Our equivalent:** Generate a proper PDF on the server (not browser print) — clean, professional, email-ready.

**Tech:** `playwright` server-side render of `report.html` → save PDF to `/reports/{session_id}.pdf`

**Changes needed:**
- `backend/main.py` — `GET /api/session/report/{id}/pdf` endpoint
- `backend/report_renderer.py` — Playwright PDF generation
- `frontend/report.html` — "Download PDF" button

**Effort:** 1–2 days  
**Impact:** Reports look professional when shared with hiring managers.

---

### P3-3 · Offer / Salary Guidance for Recruiters
**Inspiration:** Career-Ops generates salary negotiation scripts for candidates.  
**Our equivalent:** After assessment, suggest a salary band based on candidate score + detected seniority.

In report:
> **Offer Guidance (AI-Generated)**  
> Overall Score: 7.4 / 10 · Detected Seniority: Mid-Senior  
> Suggested Band: ₹18–24 LPA | $65K–85K  
> ⚠️ Candidate showed strong communication but gaps in structured reasoning — negotiate below band midpoint.

**Changes needed:**
- `backend/assessment.py` — seniority detection + offer guidance generation
- `frontend/report.html` — offer guidance card (collapsible, labeled "AI Suggestion")

**Effort:** 1–2 days  

---

## Phase 4 — Growth & Automation (Month 3+)
> Turn Audisift into a sourcing + screening end-to-end platform.

### P4-1 · Inbound Candidate Sourcing Scanner
**Inspiration:** Career-Ops scans 45+ company job boards for open roles.  
**Our equivalent:** Recruiters paste a job description → Audisift scans LinkedIn/Naukri/Wellfound and auto-sends interview invite links to matching profiles.

### P4-2 · Human-in-the-Loop Report Gate
**Inspiration:** Career-Ops never auto-submits — human always reviews first.  
**Our equivalent:** Report is private by default. Recruiter clicks "Approve & Share" to send the report link to the hiring manager via email.

### P4-3 · Interview Template Library
Recruiters build and save custom interview "templates" (role archetype + question focus + time limit) and reuse them across candidates. Share templates with the team.

### P4-4 · Multi-Recruiter Team Workspaces
Currently one recruiter per account. Add team support:
- Workspace with shared candidate pool
- Role-based access (Recruiter / Hiring Manager / Admin)
- Activity log per candidate

### P4-5 · Integration Webhooks
POST to Slack / Notion / Greenhouse / Lever when:
- Interview completed
- Score crosses threshold
- Recruiter shortlists a candidate

---

## Quick Wins (Can ship in hours, not days)

| # | Feature | File | Description | Status |
|---|---------|------|-------------|--------|
| QW-1 | Score letter grade | `report.html` | Show A/B/C/D/F grade alongside score number (A = 8+, B = 6–8, C = 4–6, D = 2–4, F = <2) | ✅ Completed |
| QW-2 | Interview share link | `report.html` | One-click copy of candidate's interview link to share with colleagues | ✅ Completed |
| QW-3 | Session duration in report | `report.html` | Show total interview duration (already tracked via timer) | ✅ Completed |
| QW-4 | Retry interview button | `dashboard.html` | Let recruiter send a new invite if candidate had technical issues | ✅ Completed |
| QW-5 | CSV export with scores | `dashboard.html` | Export session list with all dimension scores, not just metadata | ✅ Completed |
| QW-6 | Email report to HM | `report.html` | One-click email the report URL to a hiring manager email address | ✅ Completed |
| QW-7 | Dark mode report PDF | `report.html` | Toggle between light/dark PDF export | ✅ Completed |

---

## Implementation Order (Recommended)

```
Week 1:  QW-1 to QW-6  +  P1-3 (Prep Kit)
Week 2:  P1-1 (Archetypes)  +  P1-2 (STAR extraction)
Week 3:  P2-1 (Pipeline stages)  +  P2-2 (Comparison)
Week 4:  P3-2 (PDF generation)  +  P3-3 (Offer guidance)
Month 2: P3-1 (CV context — biggest lift, most impact)
Month 3: P4-x (Growth features)
```

---

## Current Stack Reference

| Layer | Tech |
|-------|------|
| Backend | FastAPI + SQLAlchemy + aiosqlite / PostgreSQL |
| AI | Groq (LLaMA 3.3 70B conversation, Whisper V3 transcription) |
| Auth | fastapi-users JWT |
| Frontend | Vanilla HTML/CSS/JS (no framework) |
| Hosting | Render (free tier) |
| Voice | Web Speech API + MediaRecorder → Groq Whisper |

---

*This document lives at `ROADMAP.md` in the project root.*  
*Update it as features ship — cross off completed items.*
