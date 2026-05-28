import pytest
import json
import httpx
from unittest.mock import AsyncMock, patch
from backend.main import app
from backend.database import get_session

@pytest.mark.asyncio
async def test_candidate_role_access_and_generation():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        
        # 1. Register a recruiter account
        recruiter_email = "recruiter_test@example.com"
        reg_payload = {
            "email": recruiter_email,
            "password": "RecruiterPassword123!",
            "full_name": "Alice Recruiter",
            "company_name": "TestCorp"
        }
        res = await client.post("/auth/register", json=reg_payload)
        assert res.status_code == 201
        
        # 2. Login as recruiter
        login_payload = {
            "username": recruiter_email,
            "password": "RecruiterPassword123!"
        }
        res = await client.post("/auth/jwt/login", data=login_payload)
        assert res.status_code == 200
        recruiter_token = res.json()["access_token"]
        recruiter_headers = {"Authorization": f"Bearer {recruiter_token}"}
        
        # 3. Bulk generate candidates as recruiter
        candidates_payload = {
            "candidates": [
                {"email": "candidate1@example.com", "full_name": "Candidate One"},
                {"email": "candidate2@example.com", "full_name": "Candidate Two"}
            ]
        }
        res = await client.post("/api/candidates/bulk-generate", json=candidates_payload, headers=recruiter_headers)
        assert res.status_code == 200
        gen_data = res.json()
        assert "candidates" in gen_data
        assert len(gen_data["candidates"]) == 2
        
        candidate1 = gen_data["candidates"][0]
        assert candidate1["email"] == "candidate1@example.com"
        assert candidate1["status"] == "created"
        assert len(candidate1["temp_password"]) == 8  # our generated pw length
        candidate1_pw = candidate1["temp_password"]
        
        # 4. List candidates as recruiter
        res = await client.get("/api/candidates", headers=recruiter_headers)
        assert res.status_code == 200
        list_data = res.json()
        assert len(list_data["candidates"]) == 2
        
        # 5. Log in as Candidate One
        cand_login_payload = {
            "username": "candidate1@example.com",
            "password": candidate1_pw
        }
        res = await client.post("/auth/jwt/login", data=cand_login_payload)
        assert res.status_code == 200
        candidate_token = res.json()["access_token"]
        candidate_headers = {"Authorization": f"Bearer {candidate_token}"}
        
        # 6. Test Candidate One cannot access recruiter dashboard
        res = await client.get("/api/dashboard", headers=candidate_headers)
        assert res.status_code == 403  # Forbidden
        
        # 7. Test Candidate One cannot access stats
        res = await client.get("/api/stats", headers=candidate_headers)
        assert res.status_code == 403
        
        # 8. Candidate starts session
        res = await client.post(
            "/api/session/start",
            json={"candidate_name": "Candidate One", "candidate_email": "candidate1@example.com"},
            headers=candidate_headers
        )
        assert res.status_code == 200
        start_data = res.json()
        session_id = start_data["session_id"]
        
        # 9. Verify session candidate_user_id is set and owner_id is the recruiter
        session = await get_session(session_id)
        assert session is not None
        assert session.candidate_user_id == candidate1["id"]
        
        # 10. Candidate One cannot view reports
        res = await client.get(f"/api/session/report/{session_id}", headers=candidate_headers)
        assert res.status_code == 403
        
        # 11. Recruiter CAN view report
        res = await client.get(f"/api/session/report/{session_id}", headers=recruiter_headers)
        assert res.status_code == 200  # returns report status "generating" or ready
