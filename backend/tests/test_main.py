"""
Pytest test suite for Lyftr AI backend.

Run with:
    pytest tests/test_main.py -v

All LiteLLM calls are mocked so no real API keys are needed.
"""

import json
import os
import sys
import types
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock

# ---------------------------------------------------------------------------
# Put the backend root on the path so imports resolve
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use an in-memory SQLite DB for tests
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_app.db")
os.environ.setdefault("LLM_API_KEYS", "test-key-1,test-key-2")
os.environ.setdefault("ENABLE_FAILURE_SIMULATION", "true")

import httpx
from httpx import AsyncClient, ASGITransport

from main import app

# ---------------------------------------------------------------------------
# Helpers – build a fake LiteLLM response
# ---------------------------------------------------------------------------

def _fake_litellm_response(content: str = "Mocked reply") -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    usage = MagicMock()
    usage.prompt_tokens = 42
    usage.completion_tokens = 9
    response.usage = usage
    response._hidden_params = {"cache_hit": False, "model_id": "key_1"}
    return response


def _fake_cached_response(content: str = "Cached reply") -> MagicMock:
    response = _fake_litellm_response(content)
    response._hidden_params = {"cache_hit": True, "model_id": ""}
    return response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_db_path(tmp_path):
    """Each test gets a fresh temporary database."""
    db_file = str(tmp_path / "test.db")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"
    # Reset the DB_PATH inside the database module
    import database
    database.DB_PATH = db_file
    yield
    # Clean up
    if os.path.exists(db_file):
        os.remove(db_file)


@pytest_asyncio.fixture
async def client():
    """Async HTTP client wired to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health(client):
    """1. GET /health returns 200 with correct fields."""
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "keys_configured" in body
    assert "cache_enabled" in body
    assert isinstance(body["keys_configured"], int)
    assert isinstance(body["cache_enabled"], bool)


@pytest.mark.asyncio
async def test_chat_valid(client):
    """2. POST /chat with valid request returns 200 with all required fields."""
    mock_response = _fake_litellm_response("The capital of France is Paris.")

    with patch("llm_client.Router.acompletion", new_callable=AsyncMock, return_value=mock_response):
        response = await client.post(
            "/chat",
            json={
                "session_id": "s-test-1",
                "message": "What is the capital of France?",
                "system_prompt": "You are a helpful assistant.",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "s-test-1"
    assert "reply" in body
    assert "metadata" in body

    meta = body["metadata"]
    for field in ("resolution_source", "model", "latency_ms", "input_tokens", "output_tokens", "fallback_attempts"):
        assert field in meta, f"Missing metadata field: {field}"


@pytest.mark.asyncio
async def test_chat_missing_message(client):
    """3. POST /chat with missing message returns 422."""
    response = await client.post(
        "/chat",
        json={"session_id": "s-test-2"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_message_too_long(client):
    """4. POST /chat with message over 4000 chars returns 422."""
    response = await client.post(
        "/chat",
        json={
            "session_id": "s-test-3",
            "message": "x" * 4001,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_session_messages(client):
    """5. GET /sessions/{session_id}/messages returns session history."""
    mock_response = _fake_litellm_response("Hello there!")

    with patch("llm_client.Router.acompletion", new_callable=AsyncMock, return_value=mock_response):
        post_resp = await client.post(
            "/chat",
            json={"session_id": "s-history", "message": "Hi"},
        )
    assert post_resp.status_code == 200

    get_resp = await client.get("/sessions/s-history/messages")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["session_id"] == "s-history"
    assert isinstance(body["messages"], list)
    assert len(body["messages"]) >= 2  # user + assistant

    roles = [m["role"] for m in body["messages"]]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_get_nonexistent_session(client):
    """6. GET /sessions/nonexistent returns 404."""
    response = await client.get("/sessions/nonexistent-session-xyz")
    assert response.status_code == 404
    assert response.json()["detail"] == "session not found"


@pytest.mark.asyncio
async def test_simulate_single_key_failure(client):
    """7. X-Simulate-Failure: key_1=429 → still succeeds using key_2."""
    mock_response = _fake_litellm_response("Success via key_2")

    # Patch litellm.acompletion which is used in simulation mode
    with patch("llm_client.litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
        response = await client.post(
            "/chat",
            json={"session_id": "s-sim-1", "message": "Hello"},
            headers={"X-Simulate-Failure": "key_1=429"},
        )

    assert response.status_code == 200
    body = response.json()
    meta = body["metadata"]
    # key_1 failed → key_2 used → fallback_attempts == 1
    assert meta["fallback_attempts"] == 1
    assert meta["key_id"] == "key_2"


@pytest.mark.asyncio
async def test_simulate_all_keys_fail(client):
    """8. X-Simulate-Failure: *=429 → returns 503."""
    response = await client.post(
        "/chat",
        json={"session_id": "s-sim-2", "message": "Hello"},
        headers={"X-Simulate-Failure": "*=429"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "all providers unavailable"
