"""
Model Release and Governance ORM model.
Tracks evaluation results, frozen release gate policy checks, and mandatory human officer sign-offs.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import Column, Integer, String, Text, DateTime
from backend.database import Base


class ModelRelease(Base):
    __tablename__ = "model_releases"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    release_id = Column(String(128), unique=True, index=True, nullable=False)
    model_id = Column(String(128), index=True, nullable=False)
    model_name = Column(String(128), nullable=False)
    stage = Column(String(50), default="release", nullable=False)
    checkpoint_hash = Column(String(64), nullable=False)
    checkpoint_path = Column(String(255), nullable=True)
    config_hash = Column(String(64), nullable=True)
    dataset_manifest_hash = Column(String(64), nullable=True)
    
    # State: candidate -> approved | rejected | quarantined
    status = Column(String(50), default="candidate", index=True, nullable=False)
    
    # Policy check results and telemetry (JSON)
    gate_checks = Column(Text, nullable=True)  # Dict[str, Any]
    rejection_reasons = Column(Text, nullable=True)  # List[str]
    metrics = Column(Text, nullable=True)  # Dict[str, Any]
    evaluation_refs = Column(Text, nullable=True)  # List[str]
    
    # Human governance sign-off (Mandatory for approval)
    reviewed_by = Column(String(128), nullable=True)  # Name of human reviewer
    review_decision = Column(String(50), nullable=True)  # "approved" or "rejected"
    review_notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "release_id": self.release_id,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "stage": self.stage,
            "checkpoint_hash": self.checkpoint_hash,
            "checkpoint_path": self.checkpoint_path,
            "config_hash": self.config_hash,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "status": self.status,
            "gate_checks": json.loads(self.gate_checks) if self.gate_checks else {},
            "rejection_reasons": json.loads(self.rejection_reasons) if self.rejection_reasons else [],
            "metrics": json.loads(self.metrics) if self.metrics else {},
            "evaluation_refs": json.loads(self.evaluation_refs) if self.evaluation_refs else [],
            "reviewed_by": self.reviewed_by,
            "review_decision": self.review_decision,
            "review_notes": self.review_notes,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
