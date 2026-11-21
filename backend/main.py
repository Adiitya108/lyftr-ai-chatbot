"""
FastAPI application entry-point for Lyftr AI backend.
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from cache import setup_cache, is_cache_enabled
from database import init_db, save_message, get_session_messages, session_exists, get_history_messages
from llm_client import chat_completion, API_KEYS
from models import (
    ChatRequest,
    ChatResponse,
    ResponseMetadata,
    SessionMessagesResponse,
    HealthResponse,
)

# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_cache()
    await init_db()
    yield
    # Shutdown (nothing to clean up for SQLite)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Lyftr AI Backend", version="1.0.0", lifespan=lifespan)

# CORS
_origins_raw = os.getenv("ALLOWED_ORIGINS", "*")
_origins = [o.strip() for o in _origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        keys_configured=len(API_KEYS),
        cache_enabled=is_cache_enabled(),
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure"),
) -> ChatResponse:
    """
    Send a message in a session and receive an LLM reply.
    """
    # Build message list for LLM: system prompt + history + new user message
    llm_messages = []

    if request.system_prompt:
        llm_messages.append({"role": "system", "content": request.system_prompt})

    # Retrieve conversation history from DB
    history = await get_history_messages(request.session_id)
    llm_messages.extend(history)

    # Append the new user message
    llm_messages.append({"role": "user", "content": request.message})

    # Call LLM (may raise HTTPException 503 if all providers unavailable)
    reply, meta = await chat_completion(
        messages=llm_messages,
        simulate_header=x_simulate_failure,
    )

    # Persist user message
    await save_message(
        session_id=request.session_id,
        role="user",
        content=request.message,
    )

    # Persist assistant reply with metadata
    assistant_meta = {
        "resolution_source": meta["resolution_source"],
        "input_tokens": meta["input_tokens"],
        "output_tokens": meta["output_tokens"],
    }
    await save_message(
        session_id=request.session_id,
        role="assistant",
        content=reply,
        metadata=assistant_meta,
    )

    return ChatResponse(
        session_id=request.session_id,
        reply=reply,
        metadata=ResponseMetadata(**meta),
    )


@app.get("/sessions/{session_id}/messages", response_model=SessionMessagesResponse)
async def get_messages(session_id: str) -> SessionMessagesResponse:
    messages = await get_session_messages(session_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionMessagesResponse(session_id=session_id, messages=messages)
