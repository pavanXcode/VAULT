"""
Persistent Job ORM model for asynchronous tool executions.
Tracks execution lifecycle, parameters, references, and outcome metrics.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from backend.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id = Column(String(64), unique=True, index=True, nullable=False)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=True)
    tool_name = Column(String(50), nullable=False, index=True)
    stage = Column(
        String(50),
        default="train",
        nullable=False,
        index=True,
    )  # 'ingest', 'verify', 'curate', 'baseline', 'train', 'harden', 'audit', 'release', 'serve'
    status = Column(
        String(50),
        default="queued",
        nullable=False,
        index=True,
    )  # 'queued'/'pending', 'running', 'succeeded'/'completed', 'failed', 'cancelled', 'not_tested', 'quarantined', 'interrupted'
    config_hash = Column(String(64), nullable=True)  # SHA-256 of parameters
    input_artifact_ids = Column(Text, nullable=True)  # JSON-encoded list of input artifact IDs
    output_artifact_ids = Column(Text, nullable=True)  # JSON-encoded list of output artifact IDs
    input_parameters = Column(Text, nullable=True)  # JSON-encoded input parameters
    input_reference = Column(String(1024), nullable=True)
    output_reference = Column(String(1024), nullable=True)
    error_message = Column(Text, nullable=True)
    stdout_log = Column(Text, nullable=True)
    stderr_log = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)  # JSON-encoded summary
    metrics = Column(Text, nullable=True)  # JSON-encoded metrics dictionary
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    stage_timing = Column(Text, nullable=True)  # JSON-encoded dict of per-stage timings
    worker_id = Column(String(128), default="local-cpu-worker", nullable=True)
    is_mock = Column(Boolean, default=False, nullable=False)
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

    def get_input_artifact_ids(self) -> List[str]:
        if self.input_artifact_ids:
            try:
                return json.loads(self.input_artifact_ids)
            except Exception:
                return []
        return []

    def get_output_artifact_ids(self) -> List[str]:
        if self.output_artifact_ids:
            try:
                return json.loads(self.output_artifact_ids)
            except Exception:
                return []
        return []

    def get_stage_timing(self) -> Dict[str, Any]:
        if self.stage_timing:
            try:
                return json.loads(self.stage_timing)
            except Exception:
                return {}
        return {}

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "experiment_id": self.experiment_id,
            "tool_name": self.tool_name,
            "stage": self.stage,
            "status": self.status,
            "config_hash": self.config_hash,
            "input_artifact_ids": self.get_input_artifact_ids(),
            "output_artifact_ids": self.get_output_artifact_ids(),
            "input_parameters": self.get_input_parameters(),
            "input_reference": self.input_reference,
            "output_reference": self.output_reference,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "stage_timing": self.get_stage_timing(),
            "worker_id": self.worker_id,
            "is_mock": self.is_mock,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
