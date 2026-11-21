"""Pydantic models for request/response validation."""

from typing import Optional, List, Any
from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, description="Session identifier")
    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    system_prompt: Optional[str] = Field(None, description="Optional system prompt override")

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be blank")
        return v


class ResponseMetadata(BaseModel):
    resolution_source: str  # "LIVE_INFERENCE" or "LLM_CACHE"
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: Optional[str]
    fallback_attempts: int


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: ResponseMetadata


class MessageRecord(BaseModel):
    role: str
    content: str
    metadata: Optional[dict] = None


class SessionMessagesResponse(BaseModel):
    session_id: str
    messages: List[MessageRecord]


class HealthResponse(BaseModel):
    status: str
    keys_configured: int
    cache_enabled: bool
