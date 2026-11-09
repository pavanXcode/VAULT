"""
Job management API endpoints for asynchronous tool executions.
"""

from datetime import datetime, timezone
import json
from typing import Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.integrations import get_tool_registry
from backend.models.job import Job
from backend.schemas.job import (
    JobCreateRequest,
    JobListResponse,
    JobResponse,
    JobResultResponse,
)
from backend.services.tool_execution_service import ToolExecutionService

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new tool execution job",
)
def create_job(
    payload: JobCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Submits a new long-running job for CuratorKIT, SafeTune, or AuditKIT.
    Validates input arguments and returns the job ID immediately while
    executing asynchronously in the background.
    """
    registry = get_tool_registry()
    runner = registry.get(payload.tool_name)
    if not runner:
        allowed = registry.list_tools()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported tool '{payload.tool_name}'. Registered tools: {allowed}",
        )

    # Validate tool inputs before accepting
    try:
        runner.validate_inputs(payload.parameters or {}, payload.input_reference)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid job parameters: {str(val_err)}",
        )

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    import hashlib
    config_hash = hashlib.sha256(
        json.dumps(payload.parameters or {}, sort_keys=True).encode("utf-8")
    ).hexdigest()

    job = Job(
        job_id=job_id,
        experiment_id=payload.experiment_id,
        tool_name=payload.tool_name,
        stage=payload.stage or "train",
        status="pending",
        config_hash=config_hash,
        input_artifact_ids=json.dumps(payload.input_artifact_ids or []),
        output_artifact_ids=json.dumps([]),
        input_parameters=json.dumps(payload.parameters or {}),
        input_reference=payload.input_reference,
        max_retries=payload.max_retries or 3,
        created_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Dispatch to background worker
    ToolExecutionService.submit_job(
        job_id=job_id,
        tool_name=payload.tool_name,
        parameters=payload.parameters or {},
        input_reference=payload.input_reference,
        timeout_seconds=payload.timeout_seconds or 300.0,
    )

    return JobResponse.model_validate(job)


@router.get(
    "",
    response_model=JobListResponse,
    summary="List tool execution jobs",
)
def list_jobs(
    skip: int = Query(default=0, ge=0, description="Pagination offset"),
    limit: int = Query(default=100, ge=1, le=500, description="Items per page"),
    tool_name: Optional[str] = Query(default=None, description="Filter by tool name"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter by status"),
    db: Session = Depends(get_db),
):
    """
    Retrieves paginated list of all submitted jobs and their current execution statuses.
    """
    query = db.query(Job)
    if tool_name:
        query = query.filter(Job.tool_name == tool_name.lower())
    if status_filter:
        query = query.filter(Job.status == status_filter.lower())

    total = query.count()
    jobs = query.order_by(Job.created_at.desc()).offset(skip).limit(limit).all()

    return JobListResponse(
        total=total,
        items=[JobResponse.model_validate(j) for j in jobs],
    )


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job status by ID",
)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    Fetches live execution status and details of a single job by its ID.
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return JobResponse.model_validate(job)


@router.get(
    "/{job_id}/result",
    response_model=JobResultResponse,
    summary="Get standardized job result and metrics",
)
def get_job_result(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    Fetches the standardized output contract of a finished job.
    Includes summary, output references, errors, and metrics.
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    duration = None
    if job.started_at and job.completed_at:
        st = job.started_at
        if st.tzinfo is None:
            st = st.replace(tzinfo=timezone.utc)
        ct = job.completed_at
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=timezone.utc)
        duration = round((ct - st).total_seconds(), 3)

    errors = [job.error_message] if job.error_message else []

    return JobResultResponse(
        job_id=job.job_id,
        tool_name=job.tool_name,
        stage=job.stage or "train",
        status=job.status,
        success=(job.status in ("completed", "succeeded", "not_tested")),
        config_hash=job.config_hash,
        input_artifact_ids=job.get_input_artifact_ids(),
        output_artifact_ids=job.get_output_artifact_ids(),
        output_reference=job.output_reference,
        summary=job.get_result_summary(),
        metrics=job.get_metrics(),
        errors=errors,
        retry_count=job.retry_count,
        worker_id=job.worker_id,
        is_mock=job.is_mock,
        duration_seconds=duration,
    )


@router.post(
    "/{job_id}/retry",
    response_model=JobResponse,
    summary="Retry a failed or interrupted job",
)
def retry_job(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    Retries an existing failed, cancelled, or interrupted job within bounded limits (max 3).
    """
    try:
        retried_job = ToolExecutionService.retry_job(job_id, db)
        return JobResponse.model_validate(retried_job)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )


@router.get(
    "/{job_id}/events",
    summary="Get chronological stage events for a job",
)
def get_job_events(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    Returns chronological timeline events and stage transitions for a job.
    """
    try:
        return ToolExecutionService.get_job_events(job_id, db)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post(
    "/{job_id}/cancel",
    response_model=JobResponse,
    summary="Cancel a running or pending job",
)
def cancel_job(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    Cancels a currently pending or running job.
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    if job.status in ("completed", "failed", "cancelled", "interrupted"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job with terminal status '{job.status}'.",
        )

    success = ToolExecutionService.cancel_job(job_id, db)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel job.",
        )

    db.refresh(job)
    return JobResponse.model_validate(job)
