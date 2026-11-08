"""
Common schemas for health, system status, and error responses.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Service health state")
    app_name: str
    version: str
    environment: str
    offline_mode: bool
    database_connected: bool
    timestamp: datetime


class SystemInfoResponse(BaseModel):
    platform: str
    os_name: str
    os_version: str
    python_version: str
    cpu_count: int
    cpu_percent: float
    memory_total_gb: float
    memory_available_gb: float
    memory_used_percent: float
    disk_total_gb: float
    disk_free_gb: float
    disk_used_percent: float
    offline_mode: bool
    database_type: str
    database_connected: bool
    vault_tools: Dict[str, Any]
    llm_config: Dict[str, Any]


class ErrorResponse(BaseModel):
    detail: Union[str, List[Dict[str, Any]]]
    status_code: int
    timestamp: datetime
