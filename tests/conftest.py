import os
import pytest
import asyncio
import sys

# Set test environment variables BEFORE importing backend modules
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_screener.db"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-characters-long-required-for-jwt-needs-to-be-long"
os.environ["GROQ_API_KEY"] = "mock_groq_key_for_testing"

# Ensure workspace root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database import Base, engine

@pytest.fixture(scope="session", autouse=True)
def event_loop():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
async def setup_db():
    # Recreate tables for every test to ensure strict test isolation
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    # Remove test database file if it exists
    if os.path.exists("./test_screener.db"):
        try:
            os.remove("./test_screener.db")
        except PermissionError:
            pass

from unittest.mock import AsyncMock, patch

class MockChoice:
    def __init__(self, content):
        self.message = AsyncMock()
        self.message.content = content

class MockResponse:
    def __init__(self, content):
        self.choices = [MockChoice(content)]

@pytest.fixture(autouse=True)
def mock_groq_client():
    mock_response = MockResponse("Mocked LLM Response")
    with patch("backend.conversation.client.chat.completions.create", new_callable=AsyncMock) as mock_conv_groq, \
         patch("backend.assessment.client.chat.completions.create", new_callable=AsyncMock) as mock_assess_groq:
        mock_conv_groq.return_value = mock_response
        mock_assess_groq.return_value = mock_response
        yield mock_conv_groq, mock_assess_groq
