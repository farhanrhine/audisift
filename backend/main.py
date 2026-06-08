import asyncio
import sentry_sdk
import csv
import io
import uuid
import secrets
import platform
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timedelta

# Fix for DLL loading issues on Windows (e.g. greenlet dependency of SQLAlchemy)
if platform.system() == "Windows":
    base_dir = Path(__file__).resolve().parent.parent
    venv_dir = base_dir / ".venv"
    if venv_dir.exists():
        try:
            os.add_dll_directory(str(venv_dir))
            scripts_dir = venv_dir / "Scripts"
            if scripts_dir.exists():
                os.add_dll_directory(str(scripts_dir))
        except Exception as e:
            print(f"[DLL Init Warning] Failed to register DLL directory: {e}", file=sys.stderr)


from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Depends, Query, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
import json

try:
    # When running as module (e.g., uvicorn backend.main:app)
    from backend.database import (
        init_db,
        create_session,
        get_session,
        save_message,
        get_messages,
        get_assessment,
        update_session_status,
        update_session_state,
        get_all_sessions,
        add_session_note,
        get_session_notes,
        abandon_old_sessions,
        create_bulk_link,
        get_bulk_link,
        use_bulk_link,
        get_bulk_links_for_user,
        get_candidates_for_recruiter,
        update_candidate_mail_sent,
        create_issue_report,
        get_all_issue_reports,
        update_issue_status,
        get_recruiters_usage_stats,
        seed_demo_data,
    )
    from backend.conversation import create_engine
    from backend.assessment import generate_assessment
    from backend.transcription import AudioBuffer
    from backend.email_utils import send_email, assessment_complete_email, bulk_links_email, candidate_invite_email
    from backend.auth import (
        fastapi_users, 
        current_active_user, 
        current_superuser, 
        auth_backend,
        UserRead,
        UserCreate,
        UserUpdate,
        current_active_user_optional,
        get_current_recruiter,
        get_user_manager,
    )
    from backend.models import User
    from backend.config import SENTRY_DSN
except ImportError:
    # When running directly from backend directory
    from database import (
        init_db,
        create_session,
        get_session,
        save_message,
        get_messages,
        get_assessment,
        update_session_status,
        update_session_state,
        get_all_sessions,
        add_session_note,
        get_session_notes,
        abandon_old_sessions,
        create_bulk_link,
        get_bulk_link,
        use_bulk_link,
        get_bulk_links_for_user,
        get_candidates_for_recruiter,
        update_candidate_mail_sent,
        create_issue_report,
        get_all_issue_reports,
        update_issue_status,
        get_recruiters_usage_stats,
        seed_demo_data,
    )
    from conversation import create_engine
    from assessment import generate_assessment
    from email_utils import send_email, assessment_complete_email, bulk_links_email, candidate_invite_email
    from auth import (
        fastapi_users, 
        current_active_user, 
        current_superuser, 
        auth_backend,
        UserRead,
        UserCreate,
        UserUpdate,
        current_active_user_optional,
        get_current_recruiter,
        get_user_manager,
    )
    from models import User
    from config import SENTRY_DSN


# --- Sentry Monitoring (optional) ---
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.2,
        environment="production",
    )


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_demo_data()  # Create test accounts if they don't exist
    # Start background task for session cleanup (Phase 7)
    cleanup_task = asyncio.create_task(session_cleanup_loop())
    yield
    # Cleanup on shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


async def session_cleanup_loop():
    """Background task that marks old sessions as abandoned (Phase 7)."""
    while True:
        try:
            await asyncio.sleep(600)  # Every 10 minutes
            await abandon_old_sessions(minutes=30)
        except Exception as e:
            print(f"[Cleanup Error] {e}")


app = FastAPI(title="Audisift", lifespan=lifespan)

# --- Rate Limiting ---
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: JSONResponse(
    status_code=429,
    content={"detail": "Rate limit exceeded. Please try again later."},
))

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Auth Routes (provided by fastapi-users) ---
app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)


# --- Request / Response Models ---
class StartSessionRequest(BaseModel):
    candidate_name: str
    candidate_email: str | None = None
    token: str | None = None


class MessageRequest(BaseModel):
    session_id: str
    candidate_message: str
    time_remaining: str  # e.g. "05:40"


class SessionNoteRequest(BaseModel):
    content: str


# ============================================
# HELPER FUNCTIONS (Phases 6-8)
# ============================================

async def assessment_and_notify(session_id: str):
    """
    Generate assessment and send email notification (Phase 8).
    Called as background task when interview completes.
    """
    try:
        await generate_assessment(session_id)
        session = await get_session(session_id)
        assessment = await get_assessment(session_id)
        
        if assessment and session and session.candidate_email:
            # Parse report JSON
            try:
                report = json.loads(assessment.report_json)
                overall_score = float(report.get("overall_score", 0))
                recommendation = report.get("recommendation", "Pending")
                report_url = f"http://localhost:8000/report.html?session_id={session_id}"
                
                # Send email (Phase 8)
                html = assessment_complete_email(
                    candidate_name=session.candidate_name,
                    overall_score=overall_score,
                    recommendation=recommendation,
                    report_url=report_url,
                )
                await send_email(
                    recipient=session.candidate_email,
                    subject=f"Your AI Interview Assessment: {overall_score:.1f}/10",
                    html_content=html,
                )
            except Exception as e:
                print(f"[Email] Failed to parse assessment for {session_id}: {e}")
    except Exception as e:
        print(f"[Assessment Error] {session_id}: {e}")


# --- Health Check (Phase 7) ---
@app.get("/api/health")
async def health():
    """Health check endpoint with database verification."""
    try:
        # Try to fetch a session to verify DB connection
        test_session = await get_session("health-check-dummy")
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "db": db_status,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============================================
# INTERVIEW ROUTES (PUBLIC — No auth needed)
# Candidates don't need accounts
# ============================================

@app.post("/api/session/start")
async def start_session(
    req: StartSessionRequest,
    current_user: User | None = Depends(current_active_user_optional)
):
    """Start a new interview session (public endpoint)."""
    if not req.candidate_name.strip():
        raise HTTPException(status_code=400, detail="Candidate name is required.")

    email = req.candidate_email.strip() if req.candidate_email else None
    
    # Resolve recruiter owner and candidate user ID
    owner_id = None
    candidate_user_id = None
    if current_user:
        if getattr(current_user, "role", "recruiter") == "candidate":
            owner_id = current_user.created_by_id
            candidate_user_id = current_user.id
        else:
            owner_id = current_user.id
    elif req.token:
        bulk_link = await get_bulk_link(req.token)
        if bulk_link and not bulk_link.used_at:
            owner_id = bulk_link.created_by_id

    session_id = await create_session(
        candidate_name=req.candidate_name.strip(),
        candidate_email=email,
        owner_id=owner_id,
        candidate_user_id=candidate_user_id
    )
    
    # Mark bulk link as used if applicable
    if req.token and owner_id:
        await use_bulk_link(req.token, session_id)

    engine = create_engine(session_id, req.candidate_name.strip())

    opening_message = await engine.get_opening_message()
    await save_message(session_id, "interviewer", opening_message)
    await update_session_state(session_id, engine.exchange_count, engine.uncovered_dimensions)

    return {
        "session_id": session_id,
        "opening_message": opening_message,
    }


@app.post("/api/session/message")
@limiter.limit("10/minute")
async def send_message(request: Request, req: MessageRequest, background_tasks: BackgroundTasks):
    """Send candidate message and get interviewer response (public endpoint)."""
    session = await get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="Interview already completed.")

    if not req.candidate_message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # Save candidate message
    await save_message(req.session_id, "candidate", req.candidate_message.strip())

    # Get or recreate engine (handles reconnects)
    messages_db = await get_messages(req.session_id)
    messages = []
    for msg in messages_db:
        role = "assistant" if msg["role"] == "interviewer" else "user"
        messages.append({"role": role, "content": msg["content"]})
        
    uncovered_dimensions = None
    if session.uncovered_dimensions:
        uncovered_dimensions = json.loads(session.uncovered_dimensions)

    engine = create_engine(
        session_id=req.session_id,
        candidate_name=session.candidate_name,
        exchange_count=session.exchange_count or 0,
        uncovered_dimensions=uncovered_dimensions,
        messages=messages
    )

    result = await engine.process_candidate_answer(req.candidate_message.strip(), req.time_remaining)

    # Save interviewer response
    await save_message(req.session_id, "interviewer", result["interviewer_response"])
    await update_session_state(req.session_id, engine.exchange_count, engine.uncovered_dimensions)

    # If interview complete, trigger assessment generation in background
    if result["interview_complete"]:
        await update_session_status(req.session_id, "generating")
        background_tasks.add_task(assessment_and_notify, req.session_id)

    return result


@app.post("/api/transcribe")
@limiter.limit("5/minute")
async def transcribe_audio(request: Request, file: UploadFile = File(...)):
    """Transcribe audio via Groq Whisper (public endpoint)."""
    from groq import AsyncGroq
    from config import GROQ_API_KEY, WHISPER_MODEL

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "webm"
    filename = f"audio.{ext}"

    client = AsyncGroq(api_key=GROQ_API_KEY)
    try:
        transcription = await client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model=WHISPER_MODEL,
            response_format="json",
            language="en",
            prompt="The following is a voice response from a job candidate during a corporate screening interview. Important vocabulary: candidate, teamwork, collaboration, projects, communication, explanation, professional.",
        )
        text = transcription.text.strip() if transcription.text else ""
        return {"text": text}
    except Exception as e:
        print(f"[Transcription Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@app.websocket("/ws/transcribe/{session_id}")
async def websocket_transcribe(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time audio transcription (Phase 6)."""
    await websocket.accept()
    
    # Verify session exists
    session = await get_session(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return
    
    buffer = AudioBuffer(timeout_sec=2.0)
    transcription_task = None
    
    try:
        while True:
            data = await websocket.receive_bytes()
            
            if data == b"__END__":
                # Client signaled end of audio
                if buffer.total_size > 0:
                    final_text = await buffer.transcribe()
                    if final_text:
                        await websocket.send_json({"type": "final", "text": final_text})
                break
            
            # Add chunk to buffer
            buffer.add_chunk(data)
            
            # Transcribe if timeout elapsed
            if buffer.should_transcribe():
                text = await buffer.transcribe()
                if text:
                    await websocket.send_json({"type": "interim", "text": text})
    
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        print(f"WebSocket error for session {session_id}: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass


@app.get("/api/session/report/{session_id}")
async def get_report(
    session_id: str,
    current_user: User | None = Depends(current_active_user_optional)
):
    """Get interview report (recruiter only)."""
    if current_user and getattr(current_user, "role", None) == "candidate":
        raise HTTPException(status_code=403, detail="Candidates are not allowed to view reports.")

    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    assessment = await get_assessment(session_id)
    if not assessment:
        return {"status": "generating"}

    report_data = json.loads(assessment.report_json)
    report_data["candidate_email"] = session.candidate_email
    if session.created_at and session.completed_at:
        report_data["duration_seconds"] = int((session.completed_at - session.created_at).total_seconds())
    return {"status": "ready", "report": report_data}


@app.get("/api/session/history/{session_id}")
async def get_history(
    session_id: str,
    current_user: User = Depends(get_current_recruiter)
):
    """Get interview history (recruiter only)."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = await get_messages(session_id)
    return {
        "session": {
            "id": session.id,
            "candidate_name": session.candidate_name,
            "status": session.status,
            "created_at": session.created_at.isoformat(),
        },
        "messages": messages
    }


# ============================================
# DASHBOARD & RECRUITER ROUTES (PROTECTED)
# Requires authentication
# ============================================

@app.get("/api/dashboard")
async def dashboard(current_user: User = Depends(get_current_recruiter)):
    """Get dashboard stats and sessions list (recruiter only)."""
    owner_id = None if current_user.is_superuser else current_user.id
    sessions_list = await get_all_sessions(owner_id=owner_id)
    total = len(sessions_list)
    completed = [s for s in sessions_list if s.status == "completed" and s.overall_score is not None]
    avg_score = round(sum(s.overall_score for s in completed) / len(completed), 1) if completed else 0
    pass_rate = round(
        sum(1 for s in completed if s.recommendation == "Move to next round") / len(completed) * 100
    ) if completed else 0

    return {
        "stats": {
            "total_interviews": total,
            "avg_score": avg_score,
            "pass_rate": pass_rate,
            "this_week": len([s for s in completed if (s.created_at).date() >= (datetime.now() - timedelta(days=7)).date()])
        },
        "sessions": [
            {
                "id": s.id,
                "candidate_name": s.candidate_name,
                "candidate_email": s.candidate_email,
                "created_at": s.created_at.isoformat(),
                "status": s.status,
                "overall_score": s.overall_score,
                "recommendation": s.recommendation,
            }
            for s in sessions_list
        ],
    }


@app.get("/api/stats")
async def get_stats(current_user: User = Depends(get_current_recruiter)):
    """Get comprehensive dashboard statistics (recruiter only)."""
    owner_id = None if current_user.is_superuser else current_user.id
    sessions_list = await get_all_sessions(owner_id=owner_id, limit=10000)
    
    completed = [s for s in sessions_list if s.status == "completed" and s.overall_score is not None]
    in_progress = [s for s in sessions_list if s.status == "in_progress"]
    abandoned = [s for s in sessions_list if s.status == "abandoned"]
    
    # Score calculations
    avg_score = round(sum(s.overall_score for s in completed) / len(completed), 1) if completed else 0
    
    # Recommendation breakdown
    pass_count = sum(1 for s in completed if s.recommendation == "Move to next round")
    pass_rate = round(pass_count / len(completed) * 100) if completed else 0
    
    # This week stats
    week_ago = (datetime.utcnow() - timedelta(days=7)).date()
    this_week = [s for s in completed if s.created_at.date() >= week_ago]
    this_week_avg = round(sum(s.overall_score for s in this_week) / len(this_week), 1) if this_week else 0
    
    # Score distribution
    excellent = sum(1 for s in completed if s.overall_score >= 8)
    good = sum(1 for s in completed if 6 <= s.overall_score < 8)
    average = sum(1 for s in completed if 4 <= s.overall_score < 6)
    poor = sum(1 for s in completed if s.overall_score < 4)

    return {
        "total_interviews": len(sessions_list),
        "completed": len(completed),
        "in_progress": len(in_progress),
        "abandoned": len(abandoned),
        "avg_score": avg_score,
        "pass_rate": pass_rate,
        "this_week": {
            "count": len(this_week),
            "avg_score": this_week_avg
        },
        "score_distribution": {
            "excellent": excellent,  # 8-10
            "good": good,  # 6-8
            "average": average,  # 4-6
            "poor": poor  # < 4
        },
        "recommendation_breakdown": {
            "move_forward": pass_count,
            "reservations": sum(1 for s in completed if s.recommendation == "Consider with reservations"),
            "do_not_move": sum(1 for s in completed if s.recommendation == "Do not move forward"),
        }
    }


@app.get("/api/sessions")
async def list_sessions(
    current_user: User = Depends(get_current_recruiter),
    status: str = Query(None),
    score_min: float = Query(None),
    score_max: float = Query(None),
    recommendation: str = Query(None),
    search: str = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    """
    Get paginated, filtered sessions list (recruiter only).
    
    Query parameters:
    - status: "in_progress", "completed", "abandoned"
    - score_min: Minimum overall score (0-10)
    - score_max: Maximum overall score (0-10)
    - recommendation: "Move to next round", "Consider with reservations", "Do not move forward"
    - search: Search by candidate name or email
    - limit: Results per page (max 500)
    - offset: Pagination offset
    """
    owner_id = None if current_user.is_superuser else current_user.id
    sessions_list = await get_all_sessions(owner_id=owner_id, status=status, limit=10000)
    
    # Apply filters
    filtered = sessions_list
    
    # Score filtering
    if score_min is not None:
        filtered = [s for s in filtered if s.overall_score is not None and s.overall_score >= score_min]
    if score_max is not None:
        filtered = [s for s in filtered if s.overall_score is not None and s.overall_score <= score_max]
    
    # Recommendation filtering
    if recommendation:
        rec_lower = recommendation.lower().strip()
        filtered = [s for s in filtered if s.recommendation and s.recommendation.lower().strip() == rec_lower]
    
    # Search by name or email
    if search:
        search_lower = search.lower()
        filtered = [
            s for s in filtered
            if search_lower in (s.candidate_name or "").lower() or 
               search_lower in (s.candidate_email or "").lower()
        ]
    
    # Sort by creation date (newest first)
    filtered = sorted(filtered, key=lambda s: s.created_at, reverse=True)
    
    # Apply pagination
    paginated = filtered[offset:offset+limit]
    
    return {
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
        "sessions": [
            {
                "id": s.id,
                "candidate_name": s.candidate_name,
                "candidate_email": s.candidate_email,
                "created_at": s.created_at.isoformat(),
                "status": s.status,
                "overall_score": s.overall_score,
                "recommendation": s.recommendation,
            }
            for s in paginated
        ]
    }


@app.get("/api/sessions/export/csv")
async def export_sessions_csv(
    current_user: User = Depends(get_current_recruiter),
    status: str = Query(None),
    recommendation: str = Query(None),
):
    """
    Export sessions as CSV file with dimension scores (recruiter only - QW-5).
    Supports optional filtering by status and recommendation.
    """
    owner_id = None if current_user.is_superuser else current_user.id
    sessions_list = await get_all_sessions(owner_id=owner_id, status=status, limit=10000)
    
    # Filter by recommendation if provided
    if recommendation:
        rec_lower = recommendation.lower().strip()
        sessions_list = [s for s in sessions_list if s.recommendation and s.recommendation.lower().strip() == rec_lower]
    
    # Pre-fetch all assessments to avoid lazy-loading DetachedInstanceError
    from sqlalchemy import select
    from models import Assessment
    try:
        from backend.database import AsyncSessionLocal
    except ImportError:
        from database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Assessment))
        assessments = res.scalars().all()
        assessment_map = {a.session_id: a for a in assessments}

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "Candidate Name",
        "Candidate Email",
        "Interview Date",
        "Status",
        "Overall Score",
        "Recommendation",
        "Communication Clarity",
        "Collaboration & Teamwork",
        "Structured Explanation",
        "English Fluency",
        "Role & Culture Fit",
        "Session ID"
    ])
    
    # Rows
    for s in sessions_list:
        comm = ""
        collab = ""
        struct = ""
        fluency = ""
        fit = ""
        
        assessment = assessment_map.get(s.id)
        if assessment and assessment.report_json:
            try:
                rep = json.loads(assessment.report_json)
                dims = rep.get("dimensions", {})
                comm = dims.get("communication_clarity", {}).get("score", "")
                collab = dims.get("warmth_and_patience", {}).get("score", "")
                struct = dims.get("ability_to_simplify", {}).get("score", "")
                fluency = dims.get("english_fluency", {}).get("score", "")
                fit = dims.get("candidate_fit", {}).get("score", "")
            except Exception:
                pass
                
        writer.writerow([
            s.candidate_name or "",
            s.candidate_email or "",
            s.created_at.isoformat() if s.created_at else "",
            s.status or "",
            s.overall_score or "",
            s.recommendation or "",
            comm,
            collab,
            struct,
            fluency,
            fit,
            s.id or ""
        ])
    
    # Return as streaming response
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sessions_export.csv"}
    )


@app.get("/api/sessions/{session_id}/report")
async def get_full_report(
    session_id: str,
    current_user: User = Depends(get_current_recruiter),
):
    """Get full assessment report for a session (recruiter only)."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    assessment = await get_assessment(session_id)
    if not assessment:
        return {"status": "generating"}

    report_data = json.loads(assessment.report_json)
    if session.created_at and session.completed_at:
        report_data["duration_seconds"] = int((session.completed_at - session.created_at).total_seconds())

    return {
        "status": "ready",
        "session": {
            "id": session.id,
            "candidate_name": session.candidate_name,
            "candidate_email": session.candidate_email,
            "created_at": session.created_at.isoformat(),
        },
        "report": report_data,
    }


class ShareReportRequest(BaseModel):
    email: str


@app.post("/api/sessions/{session_id}/retry")
async def retry_session(
    session_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_recruiter),
):
    """Let recruiter send a new invite if candidate had technical issues (QW-4)."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    from sqlalchemy import select
    from models import User as DBUser
    
    # Handle both module import styles
    try:
        from backend.database import AsyncSessionLocal, create_bulk_link
    except ImportError:
        from database import AsyncSessionLocal, create_bulk_link

    candidate_email = session.candidate_email
    candidate_name = session.candidate_name

    # 1. If Candidate account exists, resend invitation
    if session.candidate_user_id:
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(DBUser).where(DBUser.id == session.candidate_user_id))
            cand_user = res.scalar_one_or_none()
            if cand_user and cand_user.temp_password:
                base_url = str(request.base_url)
                login_url = f"{base_url}candidate_login.html"
                html = candidate_invite_email(
                    candidate_name=cand_user.full_name,
                    email=cand_user.email,
                    password=cand_user.temp_password,
                    login_url=login_url
                )
                background_tasks.add_task(
                    send_email,
                    recipient=cand_user.email,
                    subject="Audisift Interview Re-invite / Retry",
                    html_content=html
                )
                return {"status": "email_queued", "type": "candidate_account"}

    # 2. If no candidate user but we have email, generate token and email it
    if candidate_email:
        token = secrets.token_urlsafe(32)
        await create_bulk_link(token, f"Retry: {candidate_name}", current_user.id)
        base_url = str(request.base_url)
        interview_url = f"{base_url}?token={token}"

        html = f"""
        <h2>Retake your Audisift Voice Interview</h2>
        <p>Hi {candidate_name},</p>
        <p>Your interviewer has requested that you retake/retry your screening interview.</p>
        <p>Please use the link below to start your new interview session:</p>
        <p><a href="{interview_url}" style="padding:10px 20px; background-color:#E52b50; color:#fff; text-decoration:none; border-radius:4px; display:inline-block; font-weight:bold;">Start Interview</a></p>
        <p>If the button doesn't work, copy and paste this link: {interview_url}</p>
        """
        background_tasks.add_task(
            send_email,
            recipient=candidate_email,
            subject="Action Required: Retry your Audisift Interview",
            html_content=html
        )
        return {"status": "email_queued", "type": "token_link", "link": interview_url}

    # 3. If no email, just generate token link for recruiter to copy
    token = secrets.token_urlsafe(32)
    await create_bulk_link(token, f"Retry: {candidate_name}", current_user.id)
    base_url = str(request.base_url)
    interview_url = f"{base_url}?token={token}"
    return {"status": "link_generated", "type": "no_email", "link": interview_url}


@app.post("/api/sessions/{session_id}/share-email")
async def share_report_email(
    session_id: str,
    req: ShareReportRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_recruiter),
):
    """Share assessment report with Hiring Manager via email (QW-6)."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    base_url = str(request.base_url)
    report_url = f"{base_url}report.html?session_id={session_id}"

    score_str = f"{session.overall_score:.1f}/10" if session.overall_score else "N/A"
    rec_str = session.recommendation or "Pending"

    html = f"""
    <h2>Audisift Candidate Assessment Report</h2>
    <p>Hi,</p>
    <p>Recruiter {current_user.full_name} ({current_user.email}) has shared a candidate assessment report with you.</p>
    <p><strong>Candidate:</strong> {session.candidate_name}</p>
    {f"<p><strong>Email:</strong> {session.candidate_email}</p>" if session.candidate_email else ""}
    <p><strong>Overall Score:</strong> {score_str}</p>
    <p><strong>Recommendation:</strong> {rec_str}</p>
    <p>Please click the link below to view the full report including the interview transcript and dimension breakdown:</p>
    <p><a href="{report_url}" style="padding:10px 20px; background-color:#E52b50; color:#fff; text-decoration:none; border-radius:4px; display:inline-block; font-weight:bold;">View Assessment Report</a></p>
    <p>If the button doesn't work, copy and paste this link: {report_url}</p>
    """

    background_tasks.add_task(
        send_email,
        recipient=req.email.strip(),
        subject=f"Audisift Report Shared: {session.candidate_name}",
        html_content=html
    )
    return {"status": "shared_email_queued"}


@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(current_superuser),  # Admin only
):
    """Delete a session (admin only)."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Delete session (cascades to messages, assessment, notes)
    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await db.delete(session)
        await db.commit()

    return {"status": "deleted"}


@app.post("/api/sessions/{session_id}/notes")
async def add_note(
    session_id: str,
    note: SessionNoteRequest,
    current_user: User = Depends(get_current_recruiter),
):
    """Add a note to a session (recruiter only)."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    await add_session_note(session_id, current_user.id, note.content)
    return {"status": "note_added"}


@app.get("/api/sessions/{session_id}/notes")
async def get_notes(
    session_id: str,
    current_user: User = Depends(get_current_recruiter),
):
    """Get all notes for a session (recruiter only)."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    notes = await get_session_notes(session_id)
    return {
        "notes": [
            {
                "id": n.id,
                "author": n.author.full_name if n.author else "Unknown",
                "content": n.content,
                "created_at": n.created_at.isoformat(),
                "updated_at": n.updated_at.isoformat(),
            }
            for n in notes
        ],
    }


# ============================================
# BULK INTERVIEW LINKS (Phase 8)
# ============================================

class BulkLinkRequest(BaseModel):
    count: int  # Number of links to generate
    label: str = "Interview Batch"  # Batch label


class BulkLinkResponse(BaseModel):
    batch_id: str
    batch_label: str
    count: int
    links: list[str]


@app.post("/api/interviews/bulk-generate")
async def bulk_generate_links(
    req: BulkLinkRequest,
    current_user: User = Depends(get_current_recruiter),
) -> BulkLinkResponse:
    """
    Generate bulk interview links for recruiter distribution (Phase 8).
    Each link is a one-time token. Recruiters share these with candidates.
    """
    if req.count < 1 or req.count > 1000:
        raise HTTPException(status_code=400, detail="Count must be between 1 and 1000")
    
    batch_id = str(uuid.uuid4())[:8]
    links = []
    
    for _ in range(req.count):
        token = secrets.token_urlsafe(32)
        await create_bulk_link(token, req.label, current_user.id)
        interview_url = f"http://localhost:8000/?token={token}"
        links.append(interview_url)
    
    # Send email with links (Phase 8)
    html = bulk_links_email(
        recipient_email=current_user.email,
        interview_links=links,
        batch_label=req.label,
    )
    await send_email(
        recipient=current_user.email,
        subject=f"AI Interview Links Generated — {req.label} ({req.count} links)",
        html_content=html,
    )
    
    return BulkLinkResponse(
        batch_id=batch_id,
        batch_label=req.label,
        count=req.count,
        links=links,
    )


@app.get("/api/interviews/bulk-links")
async def get_bulk_links(
    current_user: User = Depends(get_current_recruiter),
):
    """
    Get all bulk links created by the current user (Phase 8).
    Shows which links have been used and which are pending.
    """
    links = await get_bulk_links_for_user(current_user.id)
    return {
        "links": [
            {
                "token": link.token[:8] + "...",  # Masked for security
                "batch": link.batch_label,
                "created_at": link.created_at.isoformat(),
                "used": link.used_at is not None,
                "session_id": link.session_id,
            }
            for link in links
        ],
    }


# ============================================
# CANDIDATE MANAGEMENT (Role splitting)
# ============================================

class CandidateCreateItem(BaseModel):
    email: str
    full_name: str

class BulkCandidateCreateRequest(BaseModel):
    candidates: list[CandidateCreateItem]

class SendCandidateEmailRequest(BaseModel):
    user_ids: list[str] | None = None  # None means send to all unsent for this recruiter

import string
import random

def generate_random_password(length=8) -> str:
    chars = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choice(chars) for _ in range(length))

@app.post("/api/candidates/bulk-generate")
async def bulk_generate_candidates(
    req: BulkCandidateCreateRequest,
    current_user: User = Depends(get_current_recruiter),
    user_manager = Depends(get_user_manager)
):
    """Bulk generate candidate credentials (recruiter only)."""
    from fastapi_users.exceptions import UserAlreadyExists
    
    created_candidates = []
    
    for cand in req.candidates:
        email = cand.email.strip().lower()
        name = cand.full_name.strip()
        if not email or not name:
            continue
            
        temp_pw = generate_random_password()
        
        try:
            # We must use fastapi_users structure
            user_create = UserCreate(
                email=email,
                password=temp_pw,
                full_name=name,
                role="candidate",
                company_name=current_user.company_name
            )
            # Create user via fastapi-users manager (hashes password)
            user = await user_manager.create(user_create, safe=True)
            
            # Update temporary password, created_by_id, and mail_sent in the DB
            try:
                # Handle both module import styles (backend.main and direct main)
                from backend.database import AsyncSessionLocal
            except ImportError:
                from database import AsyncSessionLocal
            
            try:
                from backend.models import User as DBUser
            except ImportError:
                from models import User as DBUser
            
            from sqlalchemy import update as sql_update
            
            async with AsyncSessionLocal() as db:
                await db.execute(
                    sql_update(DBUser)
                    .where(DBUser.id == user.id)
                    .values(
                        temp_password=temp_pw,
                        created_by_id=current_user.id,
                        mail_sent=False
                    )
                )
                await db.commit()
                
            created_candidates.append({
                "id": user.id,
                "email": email,
                "full_name": name,
                "temp_password": temp_pw,
                "mail_sent": False,
                "status": "created"
            })
        except UserAlreadyExists:
            created_candidates.append({
                "email": email,
                "full_name": name,
                "status": "already_exists"
            })
        except Exception as e:
            created_candidates.append({
                "email": email,
                "full_name": name,
                "status": f"error: {str(e)}"
            })
            
    return {"candidates": created_candidates}

@app.get("/api/candidates")
async def get_candidates(
    current_user: User = Depends(get_current_recruiter)
):
    """List all candidate accounts generated by the current recruiter (recruiter only)."""
    candidates = await get_candidates_for_recruiter(current_user.id)
    return {
        "candidates": [
            {
                "id": c.id,
                "email": c.email,
                "full_name": c.full_name,
                "temp_password": c.temp_password,
                "mail_sent": c.mail_sent,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in candidates
        ]
    }

async def send_bulk_invitations_task(candidates_to_email: list[dict], base_url: str):
    """Background task to send credential emails to candidates and update status."""
    for c in candidates_to_email:
        email = c["email"]
        name = c["full_name"]
        temp_pw = c["temp_password"]
        user_id = c["id"]
        
        login_url = f"{base_url}candidate_login.html"
        html = candidate_invite_email(
            candidate_name=name,
            email=email,
            password=temp_pw,
            login_url=login_url
        )
        
        success = await send_email(
            recipient=email,
            subject="Invitation to Audisift Interview",
            html_content=html
        )
        
        if success:
            await update_candidate_mail_sent(user_id, True)

@app.post("/api/candidates/send-email")
async def send_emails(
    req: SendCandidateEmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_recruiter)
):
    """Send login credentials to candidates in bulk (recruiter only)."""
    candidates = await get_candidates_for_recruiter(current_user.id)
    
    candidates_to_email = []
    for c in candidates:
        # Check if we should filter by specific user ids
        if req.user_ids is not None and c.id not in req.user_ids:
            continue
        # Skip if mail already sent and user_ids is None (bulk unsent mode)
        if req.user_ids is None and c.mail_sent:
            continue
        # Skip if there's no temporary password (already changed or missing)
        if not c.temp_password:
            continue
            
        candidates_to_email.append({
            "id": c.id,
            "email": c.email,
            "full_name": c.full_name,
            "temp_password": c.temp_password
        })
        
    if not candidates_to_email:
        return {"status": "no_emails_to_send"}
        
    base_url = str(request.base_url)
    background_tasks.add_task(send_bulk_invitations_task, candidates_to_email, base_url)
    
    return {"status": "queued", "count": len(candidates_to_email)}


# ============================================
# SYSTEM OWNER ADMIN & FEEDBACK
# ============================================

class FeedbackReportRequest(BaseModel):
    reporter_name: str | None = None
    reporter_email: str | None = None
    role: str = "candidate"
    description: str

class UpdateIssueStatusRequest(BaseModel):
    status: str

@app.post("/api/feedback/report")
async def report_issue(req: FeedbackReportRequest):
    """Submit a feedback or issue report (public)."""
    if not req.description.strip():
        raise HTTPException(status_code=400, detail="Description cannot be empty.")
    
    report = await create_issue_report(
        reporter_name=req.reporter_name.strip() if req.reporter_name else None,
        reporter_email=req.reporter_email.strip() if req.reporter_email else None,
        role=req.role.strip(),
        description=req.description.strip()
    )
    return {
        "status": "submitted",
        "id": report.id
    }

@app.get("/api/admin/stats")
async def get_admin_stats(current_user: User = Depends(current_superuser)):
    """Get recruiters usage and counts (owner only)."""
    stats = await get_recruiters_usage_stats()
    return {"recruiters": stats}

@app.get("/api/admin/issues")
async def get_admin_issues(current_user: User = Depends(current_superuser)):
    """List all reported feedback/issues (owner only)."""
    issues = await get_all_issue_reports()
    return {
        "issues": [
            {
                "id": issue.id,
                "reporter_name": issue.reporter_name,
                "reporter_email": issue.reporter_email,
                "role": issue.role,
                "description": issue.description,
                "status": issue.status,
                "created_at": issue.created_at.isoformat() if issue.created_at else None
            }
            for issue in issues
        ]
    }

@app.post("/api/admin/issues/{issue_id}/status")
async def change_issue_status(issue_id: int, req: UpdateIssueStatusRequest, current_user: User = Depends(current_superuser)):
    """Update status of a feedback/issue report (owner only)."""
    if req.status not in ["open", "in_progress", "resolved"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be open, in_progress, or resolved.")
    
    await update_issue_status(issue_id, req.status)
    return {"status": "updated"}


# --- Landing Page (Onboarding) ---


# --- Serve Frontend Static Files (must be LAST) ---
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
