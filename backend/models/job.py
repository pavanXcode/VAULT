"""
Persistent Job ORM model for asynchronous tool executions.
Tracks execution lifecycle, parameters, references, and outcome metrics.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from backend.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id = Column(String(64), unique=True, index=True, nullable=False)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=True)
    tool_name = Column(String(50), nullable=False, index=True)
    status = Column(
        String(50),
        default="pending",
        nullable=False,
        index=True,
    )  # 'pending', 'running', 'completed', 'failed', 'cancelled', 'interrupted'
    input_parameters = Column(Text, nullable=True)  # JSON-encoded input parameters
    input_reference = Column(String(1024), nullable=True)
    output_reference = Column(String(1024), nullable=True)
    error_message = Column(Text, nullable=True)
    stdout_log = Column(Text, nullable=True)
    stderr_log = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)  # JSON-encoded summary
    metrics = Column(Text, nullable=True)  # JSON-encoded metrics dictionary
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def get_input_parameters(self) -> Dict[str, Any]:
        if self.input_parameters:
            try:
                return json.loads(self.input_parameters)
            except Exception:
                return {}
        return {}

    def get_result_summary(self) -> Dict[str, Any]:
        if self.result_summary:
            try:
                return json.loads(self.result_summary)
            except Exception:
                return {}
        return {}

    def get_metrics(self) -> Dict[str, Any]:
        if self.metrics:
            try:
                return json.loads(self.metrics)
            except Exception:
                return {}
        return {}

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "experiment_id": self.experiment_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "input_parameters": self.get_input_parameters(),
            "input_reference": self.input_reference,
            "output_reference": self.output_reference,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
