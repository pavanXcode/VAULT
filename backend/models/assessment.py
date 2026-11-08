"""
Scientific assessment ORM model for append-only verification finding events.
Every inspection generates a new finding event with supporting evidence.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict
from sqlalchemy import Column, Integer, String, Text, DateTime, event
from backend.database import Base


class ScientificAssessment(Base):
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    finding_id = Column(String(128), unique=True, index=True, nullable=False)
    record_id = Column(String(128), index=True, nullable=False)
    source_hash = Column(String(64), index=True, nullable=False)
    verifier_version = Column(String(50), default="vault_verifier_v1.0", nullable=False)
    status = Column(String(50), nullable=False)  # checks_passed, flagged, needs_review
    issues = Column(Text, nullable=False)  # JSON-encoded array of issue strings
    evidence = Column(Text, nullable=False)  # JSON-encoded array of evidence dicts
    derived = Column(Text, nullable=True)  # JSON-encoded dict of calculated values
    original_verdict = Column(String(50), nullable=False)
    review_state = Column(String(50), default="automated", nullable=False)
    supersedes_id = Column(String(128), nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "finding_id": self.finding_id,
            "record_id": self.record_id,
            "source_hash": self.source_hash,
            "verifier_version": self.verifier_version,
            "status": self.status,
            "issues": json.loads(self.issues) if self.issues else [],
            "evidence": json.loads(self.evidence) if self.evidence else [],
            "derived": json.loads(self.derived) if self.derived else {},
            "original_verdict": self.original_verdict,
            "review_state": self.review_state,
            "supersedes_id": self.supersedes_id,
            "timestamp": self.created_at.isoformat() if self.created_at else None,
        }


# Immutability: Assessments are append-only. No UPDATE or DELETE allowed.
@event.listens_for(ScientificAssessment, "before_update")
def receive_before_update(mapper, connection, target):
    raise PermissionError("IMMUTABILITY VIOLATION: Scientific assessments are append-only and cannot be updated.")


@event.listens_for(ScientificAssessment, "before_delete")
def receive_before_delete(mapper, connection, target):
    raise PermissionError("IMMUTABILITY VIOLATION: Scientific assessments are append-only and cannot be deleted.")
