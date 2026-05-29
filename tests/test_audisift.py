import pytest
import json
import httpx
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta

from backend.main import app
from backend.database import (
    create_session,
    get_session,
    save_message,
    get_messages,
    update_session_status,
    update_session_state,
    get_all_sessions,
    save_assessment,
    get_assessment,
)
from backend.conversation import InterviewEngine, create_engine
from backend.assessment import generate_assessment

# Mock choices structure for Groq responses
class MockChoice:
    def __init__(self, content):
        self.message = AsyncMock()
        self.message.content = content

class MockResponse:
    def __init__(self, content):
        self.choices = [MockChoice(content)]

# -------------------------------------------------------------
# DATABASE OPERATIONS TESTS
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_database_operations():
    # 1. Create a session
    session_id = await create_session("Alice Test", "alice@example.com")
    assert session_id is not None
    
    session = await get_session(session_id)
    assert session is not None
    assert session.candidate_name == "Alice Test"
    assert session.candidate_email == "alice@example.com"
    assert session.status == "in_progress"
    
    # 2. Save and get messages
    await save_message(session_id, "interviewer", "Hello Alice")
    await save_message(session_id, "candidate", "Hello Sarah")
    
    msgs = await get_messages(session_id)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "interviewer"
    assert msgs[0]["content"] == "Hello Alice"
    assert msgs[1]["role"] == "candidate"
    assert msgs[1]["content"] == "Hello Sarah"
    
    # 3. Update status
    await update_session_status(session_id, "completed")
    session = await get_session(session_id)
    assert session.status == "completed"
    
    # 4. Save assessment
    report_data = {
        "overall_score": 8.0,
        "recommendation": "Move to next round",
        "dimensions": {
            "communication_clarity": {"score": 8, "confidence": "high"}
        }
    }
    await save_assessment(session_id, json.dumps(report_data), "Move to next round", 8.0)
    
    assessment = await get_assessment(session_id)
    assert assessment is not None
    assert assessment.overall_score == 8.0
    assert assessment.recommendation == "Move to next round"
    
    # 5. Verify denormalization on Session table
    session = await get_session(session_id)
    assert session.overall_score == 8.0
    assert session.recommendation == "Move to next round"

# -------------------------------------------------------------
# INTERVIEW ENGINE & STATE TRANSITION TESTS
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_interview_engine_basic_flow():
    session_id = await create_session("Bob Test", "bob@example.com")
    
    # Create engine
    engine = create_engine(session_id, "Bob Test")
    
    # 1. Test get opening message
    mock_opening = "Hello Bob, welcome to the interview."
    with patch("backend.conversation.client.chat.completions.create", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = MockResponse(mock_opening)
        opening = await engine.get_opening_message()
        assert opening == mock_opening
        
    # 2. Test response generation for repeat request
    repeat_ans = "Can you repeat the question?"
    # Repeat should not call LLM - it is pure-code/deterministic
    res = await engine.process_candidate_answer(repeat_ans)
    assert "asking:" in res["interviewer_response"]
    assert res["interview_complete"] is False

    # 3. Test short response triggers follow-up
    short_ans = "Yes."
    mock_followup = "Can you please elaborate on that?"
    with patch("backend.conversation.client.chat.completions.create", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = MockResponse(mock_followup)
        res = await engine.process_candidate_answer(short_ans)
        assert res["interviewer_response"] == mock_followup
        assert res["interview_complete"] is False
        assert engine.state["follow_up_count"] == 1

# -------------------------------------------------------------
# ASSESSMENT GENERATION TESTS
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_assessment_generation():
    session_id = await create_session("Charlie Test", "charlie@example.com")
    await save_message(session_id, "interviewer", "What draws you to this corporate role?")
    # Provide a long response so we don't hit zero data or low confidence
    candidate_answer = ("I love collaborating with teams because I want to solve complex business challenges "
                        "and make a big difference in organizational efficiency. Explaining technology allows me to "
                        "break down complex topics into simple analogies so non-technical stakeholders can understand easily. "
                        "I believe in patience, active listening, and working together to resolve conflicts. "
                        "I try to structure my explanations clearly, using simple examples.")
    await save_message(session_id, "candidate", candidate_answer)
    
    mock_llm_json = {
        "dimensions": {
            "communication_clarity": {
                "score": 9.0,
                "confidence": "high",
                "justification": "Charlie is very articulate and clear.",
                "evidence_quote": "I try to structure my explanations clearly."
            },
            "warmth_and_patience": {
                "score": 8.0,
                "confidence": "high",
                "justification": "Demonstrates warmth and ability to collaborate with teams.",
                "evidence_quote": "patience, active listening, and working together to resolve conflicts"
            },
            "ability_to_simplify": {
                "score": 8.0,
                "confidence": "high",
                "justification": "Uses simple analogies.",
                "evidence_quote": "break down complex topics into simple analogies"
            },
            "english_fluency": {
                "score": 9.0,
                "confidence": "high",
                "justification": "Fluent English speaker.",
                "evidence_quote": "I want to solve complex business challenges"
            },
            "candidate_fit": {
                "score": 8.5,
                "confidence": "high",
                "justification": "Good fit for the corporate role.",
                "evidence_quote": "explaining technology allows me to break down"
            }
        },
        "summary": "Charlie is an excellent corporate candidate.",
        "flags": []
    }
    
    with patch("backend.assessment.client.chat.completions.create", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = MockResponse(json.dumps(mock_llm_json))
        report = await generate_assessment(session_id)
        
        # Verify clamped scores, recomputed overall score, and recommendation
        assert report["candidate_name"] == "Charlie Test"
        assert report["overall_score"] == 8.5  # average of 9, 8, 8, 9, 8.5 = 8.5
        assert report["recommendation"] == "Move to next round"
        
        # Verify db persistence
        db_assessment = await get_assessment(session_id)
        assert db_assessment is not None
        report_saved = json.loads(db_assessment.report_json)
        assert report_saved["overall_score"] == 8.5

# -------------------------------------------------------------
# FASTAPI ENDPOINTS & AUTHENTICATION TESTS
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_fastapi_endpoints_and_auth():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Try to access protected dashboard without authentication
        res = await client.get("/api/dashboard")
        assert res.status_code == 401
        
        # 2. Register a recruiter account
        reg_payload = {
            "email": "recruiter@example.com",
            "password": "SecurePassword123!",
            "full_name": "Alice Recruiter"
        }
        res = await client.post("/auth/register", json=reg_payload)
        assert res.status_code == 201
        
        # 3. Login as recruiter to get Bearer token
        login_payload = {
            "username": "recruiter@example.com",
            "password": "SecurePassword123!"
        }
        res = await client.post("/auth/jwt/login", data=login_payload)
        assert res.status_code == 200
        token_data = res.json()
        assert "access_token" in token_data
        token = token_data["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        
        # 4. Start candidate session with recruiter headers (simulating a candidate starting an interview under this recruiter)
        res = await client.post("/api/session/start", json={"candidate_name": "Dave Test"}, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert "session_id" in data
        assert "opening_message" in data
        session_id = data["session_id"]
        
        # 5. Access dashboard with the auth headers
        res = await client.get("/api/dashboard", headers=auth_headers)
        assert res.status_code == 200
        dash_data = res.json()
        assert "stats" in dash_data
        assert "sessions" in dash_data
        
        # Check sessions list is present
        assert len(dash_data["sessions"]) >= 1
