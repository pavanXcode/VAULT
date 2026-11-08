"""
Pydantic schemas for Experiment tracking.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


ALLOWED_TOOL_TYPES = {"curatorkit", "safetune", "auditkit", "general"}


class ExperimentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Name of the experiment")
    description: Optional[str] = Field(default=None, description="Detailed experiment description")
    tool_type: str = Field(
        default="curatorkit",
        description="Target VAULT tool: curatorkit, safetune, auditkit, or general",
    )
    parameters: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Configuration parameters for the run",
    )

    @field_validator("tool_type")
    @classmethod
    def validate_tool_type(cls, v: str) -> str:
        lowered = v.lower().strip()
        if lowered not in ALLOWED_TOOL_TYPES:
            raise ValueError(f"tool_type must be one of {sorted(ALLOWED_TOOL_TYPES)}")
        return lowered


class ExperimentRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    tool_type: str
    status: str
    parameters: Optional[Dict[str, Any]] = None
    results: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("parameters", "results", mode="before")
    @classmethod
    def parse_json_fields(cls, v: Any) -> Optional[Dict[str, Any]]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v


class ExperimentListResponse(BaseModel):
    total: int
    items: List[ExperimentRead]
