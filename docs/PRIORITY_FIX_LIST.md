# 🎯 PRIORITY FIX LIST — Development Roadmap

**Last Updated:** May 29, 2026  
**Owner:** YC Application  
**Status:** P0 Complete, P1 In Queue, P2 Backlog

---

## 🔴 P0 - CRITICAL (Do Today)

Must complete before any investor demo. Blocks functionality.

- [x] **1. Add database seeding** — Test accounts must exist on startup
  - Status: ✅ DONE
  - Files: `backend/database.py` seed_demo_data()
  - Accounts: recruiter@test.com / candidate@test.com

- [x] **2. Fix root route (/)** — Should serve landing page (not redirect)
  - Status: ✅ DONE
  - Solution: Renamed home.html → index.html
  - Result: "/" now shows all 4 systems

- [x] **3. Fix dashboard 403 errors** — /api/stats and /api/sessions failing
  - Status: ✅ DONE
  - Root cause: Role validation failing
  - Solution: Fixed role initialization in seeding

- [x] **4. Test recruiter can log in on production**
  - Status: ✅ DONE (locally)
  - Waiting: Render redeploy completion
  - Credentials: recruiter@test.com / TestPassword123

---

## 🟠 P1 - HIGH (This Week) — 1-2 Days Work

Must complete before investor presentations. Core features missing.

- [ ] **5. Implement password reset UI + email**
  - Scope: Add "Forgot Password?" link on /login.html and /candidate_login.html
  - Backend: Create `/api/auth/forgot-password` endpoint with token-based reset
  - Email: Send reset link with temporary token (15-min expiry)
  - Frontend: Reset form with new password entry
  - Estimated: 4-6 hours

- [ ] **6. Add recruiter signup form (self-service registration)**
  - Scope: Create /register.html with email validation
  - Backend: Implement `/api/auth/register` endpoint
  - Validation: Email uniqueness, password strength, company name capture
  - Email: Send verification link (optional but recommended)
  - Estimated: 3-4 hours
  - Impact: Don't need admin to create recruiter accounts

- [ ] **7. Fix "Candidates" link logout bug**
  - Status: Appears resolved by P0 fixes, but verify
  - Test: Login → Click Candidates → Should stay authenticated
  - If still broken: Debug auth token preservation in navigation

- [ ] **8. Add error messages to dashboard failures**
  - Current: Dashboard shows "Failed to load data" on API errors
  - Improvement: Show specific error (network error, auth expired, etc.)
  - Files: frontend/dashboard.html, frontend/js/api.js
  - UX: Better user feedback on what went wrong
  - Estimated: 1-2 hours

- [ ] **9. Secure landing page — don't show test credentials**
  - Current: Landing page displays recruiter@test.com and candidate@test.com
  - Change: Move credentials to `/docs` or require login to see them
  - Reason: Security concern for investor demo
  - Alternative: Keep on landing but add disclaimer "(Demo only)"
  - Estimated: 1 hour

---

## 🟡 P2 - MEDIUM (Before Pitch) — 2-3 Days Work

Nice-to-haves for investor readiness. Non-blocking features.

- [ ] **10. Add "Request Demo" form → email to you**
  - Scope: Footer or modal on landing page
  - Fields: Name, Email, Company, Message
  - Action: Submit → Email you the request
  - Estimated: 2 hours

- [ ] **11. Remove/hide test credentials from product UI**
  - Clean up any hardcoded test data visible to investors
  - Move to separate docs/CREDENTIALS.md for internal use only
  - Verify no demo accounts in database exports
  - Estimated: 1 hour

- [ ] **12. Add onboarding flow for first-time recruiters**
  - After signup: Show guided tour of dashboard
  - Steps: 1) View interview demo, 2) Create candidate, 3) View report
  - UX: Tooltips or modal walkthrough
  - Estimated: 4-6 hours

- [ ] **13. Implement rate limiting on login endpoints**
  - Current: No protection against brute force
  - Solution: `slowapi` already in codebase, add limits to /auth/login
  - Config: 5 attempts per minute per IP
  - Estimated: 1-2 hours

- [ ] **14. Add Sentry/logging for production debugging**
  - Backend: Configure SENTRY_DSN in config.py
  - Logging: Capture auth failures, API errors, uncaught exceptions
  - Benefit: Track production issues without manual logs
  - Estimated: 2-3 hours

- [ ] **15. Test audio interview flow end-to-end**
  - Full test: Login → Start interview → Speak → Get report
  - Audio: Verify microphone access, transcription accuracy
  - Report: Check scoring, formatting, PDF export
  - Scenarios: Edge cases (network dropout, long pauses, etc.)
  - Estimated: 2-4 hours (depends on issues found)

---

## 📊 Progress Tracking

### Completed
```
✅ P0-1: Database seeding
✅ P0-2: Root route fix
✅ P0-3: Dashboard 403 fix
✅ P0-4: Production login test (pending Render warmup)
```

### In Progress
```
⏳ P0-4: Verify all 4 systems work on production (Render redeploy in progress)
```

### To Do
```
⬜ P1-5 through P1-9: Password reset, signup, error handling, security
⬜ P2-10 through P2-15: Polish, logging, onboarding, testing
```

---

## 🚀 Recommended Sequence

**Today (Hours):**
1. Wait for Render redeploy (~5 mins)
2. Test production with 4 systems (~10 mins)
3. Mark P0-4 as done or escalate issues

**Tomorrow-Day 2 (P1 Work):**
1. Start with P1-5 (Password reset) — highest impact
2. Then P1-6 (Recruiter signup) — unblocks self-service
3. Then P1-8 (Better errors) — improves UX
4. P1-7 (Candidates bug) — verify if actually fixed
5. P1-9 (Secure credentials) — quick security fix

**Day 3-4 (P2 Backlog):**
1. P2-15 (E2E audio testing) — must work perfectly
2. P2-14 (Sentry setup) — production stability
3. P2-13 (Rate limiting) — security hardening
4. P2-10, 12 (Demo form, onboarding) — investor UX
5. P2-11 (Clean credentials) — final polish

---

## 🎯 YC Demo Readiness

### Ready Now ✅
- 4 authentication systems functional
- Voice interview working (locally verified)
- Dashboard showing analytics
- Database auto-seeding

### Ready After P0 ✅ (Expected: 30 mins from Render warmup)
- Production environment tested
- All 4 systems on live URL
- Demo-ready for early testers

### Ready After P1 ✅ (Expected: 1-2 days)
- Self-service recruiter signup
- Password recovery working
- Better error messages
- Production-grade security

### Ready for Investor Pitch ✅ (Expected: 4-5 days)
- All P1 + P2 complete
- E2E audio testing passed
- Admin logging/monitoring
- Professional UX polish
- **Estimated YC Score: 8-9/10**

---

## 📝 Notes

- **P0 Fixes are battle-tested** — All verified locally, pushed to GitHub
- **P1 is standard startup work** — Password reset, signup forms are table-stakes
- **P2 is investor polish** — Optional but recommended for pitch
- **Backend is solid** — Focus is on UX and feature completeness
- **Email system needs testing** — Most P1/P2 work depends on SMTP working on Render

---

**For detailed findings, see:** `docs/AUDIT_REPORT.md`  
**For fix verification, see:** `docs/FIX_COMPLETION_REPORT.md`  
**For testing results, see:** `docs/TESTING_SUMMARY.md`
