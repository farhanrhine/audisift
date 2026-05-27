import asyncio
import sentry_sdk
import csv
import io
import uuid
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timedelta

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
    )
    from backend.conversation import create_engine
    from backend.assessment import generate_assessment
    from backend.transcription import AudioBuffer
    from backend.email import send_email, assessment_complete_email, bulk_links_email
    from backend.auth import (
        fastapi_users, 
        current_active_user, 
        current_superuser, 
        auth_backend,
        UserRead,
        UserCreate,
        UserUpdate,
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
    )
    from conversation import create_engine
    from assessment import generate_assessment
    from email import send_email, assessment_complete_email, bulk_links_email
    from auth import (
        fastapi_users, 
        current_active_user, 
        current_superuser, 
        auth_backend,
        UserRead,
        UserCreate,
        UserUpdate,
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


app = FastAPI(title="AI Candidate Screener", lifespan=lifespan)

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
async def start_session(req: StartSessionRequest):
    """Start a new interview session (public endpoint)."""
    if not req.candidate_name.strip():
        raise HTTPException(status_code=400, detail="Candidate name is required.")

    session_id = await create_session(req.candidate_name.strip())
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
async def get_report(session_id: str):
    """Get interview report (public endpoint)."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    assessment = await get_assessment(session_id)
    if not assessment:
        return {"status": "generating"}

    return {"status": "ready", "report": json.loads(assessment.report_json)}


@app.get("/api/session/history/{session_id}")
async def get_history(session_id: str):
    """Get interview history (public endpoint)."""
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
async def dashboard(current_user: User = Depends(current_active_user)):
    """Get dashboard stats and sessions list (recruiter only)."""
    sessions_list = await get_all_sessions()
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
async def get_stats(current_user: User = Depends(current_active_user)):
    """Get comprehensive dashboard statistics (recruiter only)."""
    sessions_list = await get_all_sessions(limit=10000)
    
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
    current_user: User = Depends(current_active_user),
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
    sessions_list = await get_all_sessions(status=status, limit=10000)
    
    # Apply filters
    filtered = sessions_list
    
    # Score filtering
    if score_min is not None:
        filtered = [s for s in filtered if s.overall_score is not None and s.overall_score >= score_min]
    if score_max is not None:
        filtered = [s for s in filtered if s.overall_score is not None and s.overall_score <= score_max]
    
    # Recommendation filtering
    if recommendation:
        filtered = [s for s in filtered if s.recommendation == recommendation]
    
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
    current_user: User = Depends(current_active_user),
    status: str = Query(None),
    recommendation: str = Query(None),
):
    """
    Export sessions as CSV file (recruiter only).
    Supports optional filtering by status and recommendation.
    """
    sessions_list = await get_all_sessions(status=status, limit=10000)
    
    # Filter by recommendation if provided
    if recommendation:
        sessions_list = [s for s in sessions_list if s.recommendation == recommendation]
    
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
        "Session ID"
    ])
    
    # Rows
    for s in sessions_list:
        writer.writerow([
            s.candidate_name or "",
            s.candidate_email or "",
            s.created_at.isoformat() if s.created_at else "",
            s.status or "",
            s.overall_score or "",
            s.recommendation or "",
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
    current_user: User = Depends(current_active_user),
):
    """Get full assessment report for a session (recruiter only)."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    assessment = await get_assessment(session_id)
    if not assessment:
        return {"status": "generating"}

    return {
        "status": "ready",
        "session": {
            "id": session.id,
            "candidate_name": session.candidate_name,
            "candidate_email": session.candidate_email,
            "created_at": session.created_at.isoformat(),
        },
        "report": json.loads(assessment.report_json),
    }


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
    current_user: User = Depends(current_active_user),
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
    current_user: User = Depends(current_active_user),
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
    current_user: User = Depends(current_active_user),
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
    current_user: User = Depends(current_active_user),
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


# --- Serve Frontend Static Files (must be LAST) ---
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
