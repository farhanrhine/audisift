import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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
)
from conversation import create_engine
from assessment import generate_assessment


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="AI Tutor Screener", lifespan=lifespan)


# --- Request / Response Models ---
class StartSessionRequest(BaseModel):
    candidate_name: str


class MessageRequest(BaseModel):
    session_id: str
    candidate_message: str
    time_remaining: str  # e.g. "05:40"


# --- API Routes (all under /api) ---

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Transcribe audio via Groq Whisper large-v3-turbo.
    Accepts multipart/form-data with an audio file (webm/mp4/wav/ogg etc.)
    Returns: {"text": "transcribed text"}
    """
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
            prompt="The following is a voice response from a teaching candidate during a qualitative screening interview. Important vocabulary: teaching, education, curriculum, pedagogy, students, learning, instruction.",
        )
        text = transcription.text.strip() if transcription.text else ""
        return {"text": text}
    except Exception as e:
        print(f"[Transcription Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@app.post("/api/session/start")
async def start_session(req: StartSessionRequest):
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
async def send_message(req: MessageRequest, background_tasks: BackgroundTasks):
    session = await get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session["status"] == "completed":
        raise HTTPException(status_code=400, detail="Interview already completed.")

    if not req.candidate_message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # Save candidate message
    await save_message(req.session_id, "candidate", req.candidate_message.strip())

    # Get or recreate engine (handles reconnects) safely
    messages_db = await get_messages(req.session_id)
    messages = []
    for msg in messages_db:
        role = "assistant" if msg["role"] == "interviewer" else "user"
        messages.append({"role": role, "content": msg["content"]})
        
    import json
    raw_dim = session.get("uncovered_dimensions")
    uncovered_dimensions = json.loads(raw_dim) if raw_dim else None

    engine = create_engine(
        session_id=req.session_id,
        candidate_name=session["candidate_name"],
        exchange_count=session.get("exchange_count", 0) or 0,
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
        background_tasks.add_task(generate_assessment, req.session_id)

    return result


@app.get("/api/session/report/{session_id}")
async def get_report(session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    assessment = await get_assessment(session_id)
    if not assessment:
        return {"status": "generating"}

    return {"status": "ready", "report": assessment["report"]}


@app.get("/api/session/history/{session_id}")
async def get_history(session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = await get_messages(session_id)
    return {"session": session, "messages": messages}


@app.get("/api/dashboard")
async def dashboard():
    sessions = await get_all_sessions()
    total = len(sessions)
    completed = [s for s in sessions if s["status"] == "completed" and s["overall_score"] is not None]
    avg_score = round(sum(s["overall_score"] for s in completed) / len(completed), 1) if completed else 0
    pass_rate = round(
        sum(1 for s in completed if s["recommendation"] == "Move to next round") / len(completed) * 100
    ) if completed else 0

    return {
        "stats": {
            "total_interviews": total,
            "avg_score": avg_score,
            "pass_rate": pass_rate,
        },
        "sessions": sessions,
    }


# --- Serve Frontend Static Files (must be LAST) ---
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
