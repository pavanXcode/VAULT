"""
Tool Execution Service managing asynchronous job dispatch, background workers,
timeout handling, logging, and restart recovery.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
import io
import json
import logging
from pathlib import Path
import sys
import threading
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from backend.config import get_settings
from backend.database import SessionLocal
from backend.integrations import ToolRunResult, get_tool_registry
from backend.models.job import Job

logger = logging.getLogger("vault.jobs")
settings = get_settings()


class ToolExecutionService:
    _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="vault-worker")
    _active_cancel_events: Dict[str, threading.Event] = {}
    _lock = threading.Lock()
    session_factory: Optional[Any] = None

    @classmethod
    def get_job_output_dir(cls, job_id: str) -> Path:
        """Generates and creates a sanitized output directory for a specific job."""
        jobs_root = Path(settings.upload_dir).parent / "jobs"
        job_dir = jobs_root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    @classmethod
    def recover_interrupted_jobs(cls, db: Session) -> int:
        """
        Scans database on startup for jobs stuck in 'running' or 'pending' state
        from a previous crashed or terminated session, and marks them as interrupted.
        """
        interrupted_count = 0
        stuck_jobs = (
            db.query(Job)
            .filter(Job.status.in_(["running", "pending"]))
            .all()
        )

        for job in stuck_jobs:
            job.status = "interrupted"
            job.error_message = "Job was interrupted by application shutdown or server restart."
            job.completed_at = datetime.now(timezone.utc)
            interrupted_count += 1

        if interrupted_count > 0:
            db.commit()
            logger.warning(
                f"Recovered {interrupted_count} interrupted jobs from previous application session."
            )

        return interrupted_count

    @classmethod
    def cancel_job(cls, job_id: str, db: Session) -> bool:
        """Cancels a pending or running job and places termination sentinel."""
        with cls._lock:
            event = cls._active_cancel_events.get(job_id)
            if event:
                event.set()

        job_dir = cls.get_job_output_dir(job_id)
        sentinel = job_dir / ".execution_terminated"
        try:
            sentinel.write_text(
                json.dumps({
                    "status": "cancelled",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Could not write termination sentinel: {e}")

        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            return False

        if job.status in ("completed", "failed", "cancelled", "interrupted"):
            return False

        job.status = "cancelled"
        job.error_message = "Job execution cancelled by user request."
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return True

    @classmethod
    def submit_job(
        cls,
        job_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        input_reference: Optional[str],
        timeout_seconds: float = 300.0,
    ) -> None:
        """Submits a job to the managed ThreadPoolExecutor."""
        cancel_event = threading.Event()
        with cls._lock:
            cls._active_cancel_events[job_id] = cancel_event

        cls._executor.submit(
            cls._worker_target,
            job_id,
            tool_name,
            parameters,
            input_reference,
            timeout_seconds,
            cancel_event,
        )

    @classmethod
    def _worker_target(
        cls,
        job_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        input_reference: Optional[str],
        timeout_seconds: float,
        cancel_event: threading.Event,
    ) -> None:
        """Background thread target executing the runner within an isolated database session."""
        db: Session = cls.session_factory() if cls.session_factory else SessionLocal()
        job_dir = cls.get_job_output_dir(job_id)
        log_file = job_dir / "job.log"

        try:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if not job:
                logger.error(f"Worker could not find Job {job_id} in database.")
                return

            # Check if job was already cancelled before thread dispatch
            if cancel_event.is_set() or job.status == "cancelled":
                logger.info(f"Job {job_id} was cancelled before worker execution started.")
                return

            # Transition to running
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            db.commit()

            # Retrieve runner
            registry = get_tool_registry()
            runner = registry.get(tool_name)
            if not runner:
                job.status = "failed"
                job.error_message = f"Tool '{tool_name}' is not registered or installed in VAULT."
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
                return

            # Execute with timeout
            inner_executor = ThreadPoolExecutor(max_workers=1)
            future = inner_executor.submit(
                runner.execute,
                job_id,
                parameters,
                input_reference,
                job_dir,
                cancel_event,
            )

            try:
                result: ToolRunResult = future.result(timeout=timeout_seconds)
            except FuturesTimeoutError:
                cancel_event.set()
                inner_executor.shutdown(wait=False, cancel_futures=True)

                # Write termination sentinel into job_dir to block any subsequent artifact writes
                sentinel = job_dir / ".execution_terminated"
                try:
                    sentinel.write_text(
                        json.dumps({
                            "status": "timed_out",
                            "timeout_seconds": timeout_seconds,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }),
                        encoding="utf-8",
                    )
                except Exception as e:
                    logger.warning(f"Could not write termination sentinel on timeout: {e}")

                job.status = "failed"
                job.error_message = (
                    f"Tool execution timed out after {timeout_seconds} seconds. "
                    "Cooperative cancellation was signaled to runner. "
                    "(Note: running Python threads cannot be forcefully terminated by OS; "
                    "further artifact modification is halted)."
                )
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
                return
            finally:
                inner_executor.shutdown(wait=False)

            # Check for cancellation or termination during execution
            if cancel_event.is_set() or (job_dir / ".execution_terminated").exists():
                job.status = "cancelled"
                job.error_message = "Job execution cancelled by user request."
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
                return

            # Record outcome
            job_completed_time = datetime.now(timezone.utc)
            st = job.started_at
            if st and st.tzinfo is None:
                st = st.replace(tzinfo=timezone.utc)
            duration_s = round((job_completed_time - st).total_seconds(), 2) if st else 0.0

            # Compute and store stage timing
            current_stage = job.stage or getattr(result, "stage", "train")
            stage_timings = job.get_stage_timing()
            stage_timings[current_stage] = {
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job_completed_time.isoformat(),
                "duration_seconds": duration_s,
            }
            job.stage_timing = json.dumps(stage_timings)
            job.worker_id = getattr(result, "worker_id", job.worker_id)
            job.is_mock = getattr(result, "is_mock", False)
            if hasattr(result, "output_artifact_ids") and result.output_artifact_ids:
                job.output_artifact_ids = json.dumps(result.output_artifact_ids)
            if hasattr(result, "config_hash") and result.config_hash:
                job.config_hash = result.config_hash

            if result.success:
                res_status = getattr(result, "status", "completed")
                job.status = res_status if res_status in ("not_tested", "quarantined", "succeeded") else "completed"
                job.output_reference = result.output_reference
                job.result_summary = json.dumps(result.summary)
                job.metrics = json.dumps(result.metrics)
                job.error_message = None
            else:
                job.status = "failed"
                job.output_reference = result.output_reference
                job.result_summary = json.dumps(result.summary)
                job.error_message = (
                    "\n".join(result.errors) if result.errors else "Tool execution failed."
                )

            job.completed_at = job_completed_time
            db.commit()

        except Exception as exc:
            # If application is shutting down or test runner cleared tables
            if "no such table" in str(exc).lower() or "has been deleted" in str(exc).lower():
                return
            logger.error(f"Unexpected error executing Job {job_id}: {exc}", exc_info=True)
            try:
                db.rollback()
                job = db.query(Job).filter(Job.job_id == job_id).first()
                if job:
                    job.status = "failed"
                    job.error_message = f"Internal execution error: {str(exc)}"
                    job.completed_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception as db_exc:
                if "no such table" not in str(db_exc).lower():
                    logger.error(f"Failed to record failure for Job {job_id}: {db_exc}")

        finally:
            with cls._lock:
                cls._active_cancel_events.pop(job_id, None)
            db.close()

    @classmethod
    def retry_job(cls, job_id: str, db: Session, timeout_seconds: float = 300.0) -> Job:
        """
        Retries a failed, cancelled, or interrupted job within bounded retry limits (max 3).
        Honest lifecycle: resets status to 'queued', increments retry_count, and re-executes.
        """
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise KeyError(f"Job '{job_id}' not found.")

        if job.status not in ("failed", "cancelled", "interrupted"):
            raise ValueError(
                f"Cannot retry job in '{job.status}' status. Only failed, cancelled, or interrupted jobs can be retried."
            )

        if job.retry_count >= job.max_retries:
            raise ValueError(
                f"Bounded retry limit reached: job '{job_id}' has already been retried {job.retry_count}/{job.max_retries} times."
            )

        job.retry_count += 1
        job.status = "queued"
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        db.commit()
        db.refresh(job)

        # Clear termination sentinel if exists
        job_dir = cls.get_job_output_dir(job_id)
        sentinel = job_dir / ".execution_terminated"
        if sentinel.exists():
            try:
                sentinel.unlink()
            except Exception:
                pass

        cls.submit_job(
            job_id=job.job_id,
            tool_name=job.tool_name,
            parameters=job.get_input_parameters(),
            input_reference=job.input_reference,
            timeout_seconds=timeout_seconds,
        )
        return job

    @classmethod
    def get_job_events(cls, job_id: str, db: Session) -> List[Dict[str, Any]]:
        """Returns structured chronological lifecycle and stage events for a job."""
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise KeyError(f"Job '{job_id}' not found.")

        events = []
        if job.created_at:
            events.append({
                "timestamp": job.created_at.isoformat(),
                "stage": job.stage or "ingest",
                "status": "queued",
                "message": f"Job {job.job_id} submitted and placed in execution queue.",
                "worker_id": job.worker_id,
            })

        if job.started_at:
            events.append({
                "timestamp": job.started_at.isoformat(),
                "stage": job.stage or "train",
                "status": "running",
                "message": f"Worker picked up job {job.job_id} for stage '{job.stage or 'train'}'.",
                "worker_id": job.worker_id,
            })

        stage_timings = job.get_stage_timing()
        for stage_name, timing in stage_timings.items():
            if timing.get("completed_at"):
                events.append({
                    "timestamp": timing["completed_at"],
                    "stage": stage_name,
                    "status": job.status,
                    "message": f"Stage '{stage_name}' completed in {timing.get('duration_seconds', 0)}s.",
                    "worker_id": job.worker_id,
                })

        if job.completed_at and job.status != "running":
            events.append({
                "timestamp": job.completed_at.isoformat(),
                "stage": job.stage or "serve",
                "status": job.status,
                "message": (
                    f"Job reached terminal state '{job.status}'. Error: {job.error_message}"
                    if job.error_message
                    else f"Job reached terminal state '{job.status}'."
                ),
                "worker_id": job.worker_id,
            })

        return events
