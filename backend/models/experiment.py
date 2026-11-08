"""
Experiment ORM model for CuratorKIT, SafeTune, and AuditKIT workflows.
"""

from datetime import datetime, timezone
import json
from typing import Any, Optional
from sqlalchemy import Column, Integer, String, Text, DateTime
from backend.database import Base


class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    tool_type = Column(String(50), nullable=False)  # 'curatorkit', 'safetune', 'auditkit', 'general'
    status = Column(String(50), default="created", nullable=False)  # 'created', 'running', 'completed', 'failed'
    parameters = Column(Text, nullable=True)  # JSON-encoded configuration
    results = Column(Text, nullable=True)  # JSON-encoded execution results
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

    def get_parameters_dict(self) -> Optional[dict]:
        if self.parameters:
            try:
                return json.loads(self.parameters)
            except Exception:
                return None
        return None

    def get_results_dict(self) -> Optional[dict]:
        if self.results:
            try:
                return json.loads(self.results)
            except Exception:
                return None
        return None
