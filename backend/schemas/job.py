"""
Pydantic schemas for Tool Runner Jobs.
"""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobCreateRequest(BaseModel):
    tool_name: str = Field(..., description="Target tool or action: curatorkit, safetune, auditkit, train_adapter, verify")
    stage: Optional[str] = Field(
        default="train",
        description="Pipeline stage: ingest, verify, curate, baseline, train, harden, audit, release, serve",
    )
    parameters: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Tool execution configuration parameters",
    )
    input_reference: Optional[str] = Field(
        default=None,
        description="Path or ID of input dataset/model/document",
    )
    input_artifact_ids: Optional[List[str]] = Field(
        default_factory=list,
        description="Manifest hashes of input artifacts",
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
    max_retries: Optional[int] = Field(
        default=3,
        ge=0,
        le=5,
        description="Bounded retry limit",
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
    stage: str = Field(default="train", description="Lifecycle stage")
    status: str
    config_hash: Optional[str] = None
    input_artifact_ids: List[str] = Field(default_factory=list)
    output_artifact_ids: List[str] = Field(default_factory=list)
    input_parameters: Dict[str, Any] = Field(default_factory=dict)
    input_reference: Optional[str] = None
    output_reference: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    stage_timing: Dict[str, Any] = Field(default_factory=dict)
    worker_id: Optional[str] = None
    is_mock: bool = False
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

    @field_validator("input_artifact_ids", "output_artifact_ids", mode="before")
    @classmethod
    def parse_artifact_ids(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v or []

    @field_validator("stage_timing", mode="before")
    @classmethod
    def parse_stage_timing(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v or {}


class JobResultResponse(BaseModel):
    job_id: str
    tool_name: str
    stage: str = "train"
    status: str
    success: bool
    config_hash: Optional[str] = None
    input_artifact_ids: List[str] = Field(default_factory=list)
    output_artifact_ids: List[str] = Field(default_factory=list)
    output_reference: Optional[str] = None
    summary: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    retry_count: int = 0
    worker_id: Optional[str] = None
    is_mock: bool = False
    duration_seconds: Optional[float] = None


class JobEvent(BaseModel):
    timestamp: str
    stage: str
    status: str
    message: str
    worker_id: Optional[str] = None


class JobListResponse(BaseModel):
    total: int
    items: List[JobResponse]
