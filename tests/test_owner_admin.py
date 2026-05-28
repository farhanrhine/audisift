import pytest
import httpx
from backend.main import app
from backend.database import AsyncSessionLocal
from sqlalchemy import select, update
from backend.models import User

@pytest.mark.asyncio
async def test_owner_admin_endpoints():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create a superuser user
        # Let's register a user first
        admin_email = "admin_test@example.com"
        reg_payload = {
            "email": admin_email,
            "password": "AdminPassword123!",
            "full_name": "Admin User",
            "company_name": "SaaS Corp"
        }
        res = await client.post("/auth/register", json=reg_payload)
        assert res.status_code == 201
        
        # Now update this user in the database to be a superuser
        async with AsyncSessionLocal() as db_session:
            async with db_session.begin():
                stmt = update(User).where(User.email == admin_email).values(is_superuser=True)
                await db_session.execute(stmt)
        
        # Now login as this superuser
        login_payload = {
            "username": admin_email,
            "password": "AdminPassword123!"
        }
        res = await client.post("/auth/jwt/login", data=login_payload)
        assert res.status_code == 200
        admin_token = res.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 2. Register a standard recruiter user
        recruiter_email = "recruiter_test2@example.com"
        reg_rec_payload = {
            "email": recruiter_email,
            "password": "RecruiterPassword123!",
            "full_name": "Alice Recruiter",
            "company_name": "ClientCorp"
        }
        res = await client.post("/auth/register", json=reg_rec_payload)
        assert res.status_code == 201
        
        res = await client.post("/auth/jwt/login", data={"username": recruiter_email, "password": "RecruiterPassword123!"})
        assert res.status_code == 200
        recruiter_token = res.json()["access_token"]
        recruiter_headers = {"Authorization": f"Bearer {recruiter_token}"}

        # 3. Create a candidate under standard recruiter
        candidates_payload = {
            "candidates": [
                {"email": "candidate_test@example.com", "full_name": "Bob Candidate"}
            ]
        }
        res = await client.post("/api/candidates/bulk-generate", json=candidates_payload, headers=recruiter_headers)
        assert res.status_code == 200
        cand_pw = res.json()["candidates"][0]["temp_password"]

        # Log in as candidate
        res = await client.post("/auth/jwt/login", data={"username": "candidate_test@example.com", "password": cand_pw})
        assert res.status_code == 200
        candidate_token = res.json()["access_token"]
        candidate_headers = {"Authorization": f"Bearer {candidate_token}"}

        # 4. Public POST /api/feedback/report
        feedback_payload = {
            "reporter_name": "Bob Candidate",
            "reporter_email": "candidate_test@example.com",
            "role": "candidate",
            "description": "My microphone was not recognized."
        }
        res = await client.post("/api/feedback/report", json=feedback_payload)
        assert res.status_code == 200
        assert res.json()["status"] == "submitted"

        # 5. Access check: standard recruiter and candidate cannot query stats
        res = await client.get("/api/admin/stats", headers=recruiter_headers)
        assert res.status_code == 403
        
        res = await client.get("/api/admin/stats", headers=candidate_headers)
        assert res.status_code == 403

        # 6. Access check: standard recruiter and candidate cannot list issues
        res = await client.get("/api/admin/issues", headers=recruiter_headers)
        assert res.status_code == 403

        res = await client.get("/api/admin/issues", headers=candidate_headers)
        assert res.status_code == 403

        # 7. Superuser queries stats
        res = await client.get("/api/admin/stats", headers=admin_headers)
        assert res.status_code == 200
        stats = res.json()
        assert "recruiters" in stats
        # The recruiters list should include both the admin and the recruiter
        recruiters_emails = [r["email"] for r in stats["recruiters"]]
        assert recruiter_email in recruiters_emails
        
        # Check Bob Candidate was counted under Alice Recruiter
        recruiter_entry = next(r for r in stats["recruiters"] if r["email"] == recruiter_email)
        assert recruiter_entry["candidate_count"] == 1

        # 8. Superuser lists issues
        res = await client.get("/api/admin/issues", headers=admin_headers)
        assert res.status_code == 200
        issues = res.json()["issues"]
        assert len(issues) >= 1
        test_issue = next(i for i in issues if i["reporter_email"] == "candidate_test@example.com")
        assert test_issue["description"] == "My microphone was not recognized."
        assert test_issue["status"] == "open"
        issue_id = test_issue["id"]

        # 9. Access check: recruiter/candidate cannot resolve issues
        res = await client.post(f"/api/admin/issues/{issue_id}/status", json={"status": "resolved"}, headers=recruiter_headers)
        assert res.status_code == 403

        # 10. Superuser updates issue status
        res = await client.post(f"/api/admin/issues/{issue_id}/status", json={"status": "resolved"}, headers=admin_headers)
        assert res.status_code == 200
        assert res.json()["status"] == "updated"

        # Verify status updated
        res = await client.get("/api/admin/issues", headers=admin_headers)
        issues = res.json()["issues"]
        test_issue = next(i for i in issues if i["id"] == issue_id)
        assert test_issue["status"] == "resolved"
