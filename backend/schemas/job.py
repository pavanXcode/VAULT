"""
Pydantic schemas for Tool Runner Jobs.
"""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobCreateRequest(BaseModel):
    tool_name: str = Field(..., description="Target tool: curatorkit, safetune, or auditkit")
    parameters: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Tool execution configuration parameters",
    )
    input_reference: Optional[str] = Field(
        default=None,
        description="Path or ID of input dataset/model/document",
    )
    experiment_id: Optional[int] = Field(
        default=None,
        description="Optional parent experiment ID for traceability",
    )
    timeout_seconds: Optional[float] = Field(
        default=300.0,
        ge=1.0,
        le=3600.0,
        description="Execution timeout in seconds",
    )

    @field_validator("tool_name")
    @classmethod
    def normalize_tool_name(cls, v: str) -> str:
        lowered = v.lower().strip()
        if not lowered:
            raise ValueError("tool_name cannot be empty")
        return lowered


class JobResponse(BaseModel):
    job_id: str
    experiment_id: Optional[int] = None
    tool_name: str
    status: str
    input_parameters: Dict[str, Any] = Field(default_factory=dict)
    input_reference: Optional[str] = None
    output_reference: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("input_parameters", mode="before")
    @classmethod
    def parse_input_parameters(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v or {}


class JobResultResponse(BaseModel):
    job_id: str
    tool_name: str
    status: str
    success: bool
    output_reference: Optional[str] = None
    summary: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    duration_seconds: Optional[float] = None


class JobListResponse(BaseModel):
    total: int
    items: List[JobResponse]
