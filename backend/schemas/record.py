"""
Pydantic schemas for Scientific Record input and retrieval.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ScientificRecordInput(BaseModel):
    record_id: str = Field(..., description="Unique record identifier")
    mass_mg: float = Field(..., description="Substance mass in milligrams")
    volume_l: float = Field(..., description="Volume in liters")
    reported_mg_per_l: float = Field(..., description="Reported concentration in mg/L")
    threshold_mg_per_l: float = Field(..., description="Regulatory threshold in mg/L")
    method_id: str = Field(..., description="Methodology identifier (e.g. MTH-STD-01, MTH-ALT-02)")
    threshold_measurand: str = Field(..., description="Measurand name (e.g. total_concentration)")
    original_verdict: str = Field(..., description="Researcher verdict: PASS, FAIL, or NEEDS_REVIEW")
    available_fraction: Optional[float] = Field(None, description="Available fraction coefficient if applicable")
    calibration_date: Optional[str] = Field(None, description="Date of instrument calibration")
    calibration_valid_until: Optional[str] = Field(None, description="Calibration expiration date")
    source_refs: Optional[List[str]] = Field(default_factory=list, description="Source references")

    model_config = {
        "json_schema_extra": {
            "example": {
                "record_id": "REC-LAB-2026-001",
                "mass_mg": 15.0,
                "volume_l": 0.5,
                "reported_mg_per_l": 3.0,
                "threshold_mg_per_l": 10.0,
                "method_id": "MTH-STD-01",
                "threshold_measurand": "total_concentration",
                "original_verdict": "PASS",
                "calibration_valid_until": "2026-12-31",
                "source_refs": ["SOP-ENV-001", "INST-BAL-04"],
            }
        }
    }


class ScientificRecordResponse(BaseModel):
    id: int
    record_id: str
    content_hash: str
    raw_payload: Dict[str, Any]
    method_id: str
    threshold_measurand: str
    original_verdict: str
    source_refs: List[str]
    created_at: Optional[str] = None
