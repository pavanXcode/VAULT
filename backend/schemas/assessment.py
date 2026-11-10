"""
Pydantic schemas for Scientific Assessment finding events and history.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    rule: str
    expected: Any = None
    actual: Any = None
    notes: Optional[str] = None


class ScientificAssessmentResponse(BaseModel):
    finding_id: str = Field(..., description="Unique assessment finding identifier")
    record_id: str = Field(..., description="Target record identifier")
    source_hash: str = Field(..., description="SHA-256 digest of original raw record")
    verifier_version: str = Field(default="vault_verifier_v1.0")
    status: str = Field(..., description="checks_passed, flagged, or needs_review")
    issues: List[str] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    derived: Dict[str, Any] = Field(default_factory=dict)
    original_verdict: str = Field(..., description="Preserved original verdict")
    review_state: str = Field(default="automated")
    supersedes_id: Optional[str] = None
    timestamp: Optional[str] = None
    teacher_decision: Optional[Dict[str, Any]] = Field(default=None, description="Teacher LLM classification and threat analysis")
    policy_enforcement: Optional[Dict[str, Any]] = Field(default=None, description="Python deterministic security enforcement result")


class RecordHistoryResponse(BaseModel):
    record: Dict[str, Any] = Field(..., description="Original immutable record details")
    assessments: List[ScientificAssessmentResponse] = Field(
        default_factory=list,
        description="Chronological append-only assessment events",
    )
    total_assessments: int
    latest_status: Optional[str] = None
    has_flags: bool = False
