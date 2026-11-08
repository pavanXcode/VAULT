"""
Scientific record ORM model with strict immutability guarantees.
Original laboratory records are preserved indefinitely under a content hash.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict
from sqlalchemy import Column, Integer, String, Text, DateTime, event
from backend.database import Base


class ScientificRecord(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    record_id = Column(String(128), unique=True, index=True, nullable=False)
    content_hash = Column(String(64), index=True, nullable=False)  # SHA-256 of canonical payload
    raw_payload = Column(Text, nullable=False)  # Canonical JSON of the original record
    method_id = Column(String(100), nullable=False)
    threshold_measurand = Column(String(100), nullable=False)
    original_verdict = Column(String(50), nullable=False)  # PASS, FAIL, NEEDS_REVIEW
    source_refs = Column(Text, nullable=True)  # JSON-encoded array of reference strings
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "record_id": self.record_id,
            "content_hash": self.content_hash,
            "raw_payload": json.loads(self.raw_payload) if self.raw_payload else {},
            "method_id": self.method_id,
            "threshold_measurand": self.threshold_measurand,
            "original_verdict": self.original_verdict,
            "source_refs": json.loads(self.source_refs) if self.source_refs else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Enforce database immutability: records can never be updated or deleted
@event.listens_for(ScientificRecord, "before_update")
def receive_before_update(mapper, connection, target):
    raise PermissionError("IMMUTABILITY VIOLATION: Scientific records are immutable and cannot be updated.")


@event.listens_for(ScientificRecord, "before_delete")
def receive_before_delete(mapper, connection, target):
    raise PermissionError("IMMUTABILITY VIOLATION: Scientific records are immutable and cannot be deleted.")
