"""
Pydantic schemas for the local offline LLM service.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: str = Field(..., description="Role: 'system', 'user', or 'assistant'")
    content: str = Field(..., description="Message text content")


class LLMGenerateRequest(BaseModel):
    prompt: Optional[str] = Field(default=None, description="Direct text prompt (convenience)")
    messages: Optional[List[LLMMessage]] = Field(
        default=None,
        description="Chat history messages list for conversation format",
    )
    model: Optional[str] = Field(default=None, description="Local model identifier")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(default=512, ge=1, le=8192, description="Maximum generation token count")
    system_prompt: Optional[str] = Field(default=None, description="Optional overriding system instruction")
    stop: Optional[List[str]] = Field(default=None, description="Optional stop sequences")


class LLMGenerateResponse(BaseModel):
    content: str = Field(..., description="Generated text completion")
    model: str = Field(..., description="Model identifier used")
    prompt_tokens: int = Field(..., description="Estimated or reported prompt token count")
    completion_tokens: int = Field(..., description="Estimated or reported completion token count")
    total_tokens: int = Field(..., description="Total tokens consumed")
    mode: str = Field(..., description="Inference engine mode ('mock', 'ollama', 'local_api')")
    finish_reason: str = Field(default="stop", description="Generation completion reason")
    latency_ms: float = Field(..., description="Round-trip latency in milliseconds")
    created_at: datetime = Field(..., description="Response generation timestamp")
