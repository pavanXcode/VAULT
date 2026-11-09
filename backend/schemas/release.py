"""
Pydantic schemas for Model Runs, Evaluations, and Human Release Gate Decisions.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ModelMetricsSchema(BaseModel):
    train_loss: Optional[float] = None
    eval_loss: Optional[float] = None
    domain_accuracy: Optional[float] = None
    safety_compliance: Optional[float] = None
    over_refusal_rate: Optional[float] = None
    sample_size: Optional[int] = None


class ModelCandidatePayload(BaseModel):
    model_id: str = Field(..., description="Model identifier (e.g. M3-safetune)")
    model_name: str = Field(..., description="Full model name (e.g. Tiny Aya SafeTune Hardened)")
    stage: str = Field(default="release", description="Pipeline stage")
    dataset_manifest_hash: Optional[str] = Field(default=None, description="SHA-256 hash of dataset manifest")
    config_hash: Optional[str] = Field(default=None, description="SHA-256 hash of hyperparameters config")
    checkpoint_hash: str = Field(..., description="SHA-256 hash of checkpoint weights")
    checkpoint_path: Optional[str] = Field(default=None, description="File path to checkpoint")
    metrics: Optional[ModelMetricsSchema] = None
    evaluation_refs: List[str] = Field(default_factory=list, description="IDs of AuditKIT/SafeTune runs")
    is_mock: bool = Field(default=False, description="Whether output is from a mock worker")


class ReleaseSignoffRequest(BaseModel):
    release_id: Optional[str] = Field(default=None, description="Release ID to sign off. If null, signs off latest candidate.")
    officer_name: str = Field(..., description="Full legal/staff name of human officer. Automated/LLM names rejected.")
    decision: str = Field(..., description="'approved' or 'rejected'")
    notes: Optional[str] = Field(default="", description="Justification and notes for the decision")


class ModelReportResponse(BaseModel):
    model_id: str
    model_name: str
    description: Optional[str] = None
    stage: str
    dataset_manifest_hash: Optional[str] = None
    config_hash: Optional[str] = None
    checkpoint_hash: Optional[str] = None
    checkpoint_path: Optional[str] = None
    metrics: Dict[str, Any]
    evaluation_refs: List[str]
    is_mock: bool
    status: str
    latest_release_id: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    gate_checks: Optional[Dict[str, Any]] = None
    rejection_reasons: Optional[List[str]] = None
    comparison_summary: Optional[Dict[str, Any]] = None
