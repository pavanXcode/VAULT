"""
Experiment tracking and execution endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.schemas.experiment import (
    ExperimentCreate,
    ExperimentListResponse,
    ExperimentRead,
)
from backend.services.experiment_service import ExperimentService

router = APIRouter(prefix="/experiments", tags=["Experiments"])


@router.get("", response_model=ExperimentListResponse, summary="List experiments")
def list_experiments(
    skip: int = Query(default=0, ge=0, description="Offset"),
    limit: int = Query(default=100, ge=1, le=500, description="Page limit"),
    tool_type: Optional[str] = Query(default=None, description="Filter by tool (curatorkit, safetune, auditkit)"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter by status"),
    db: Session = Depends(get_db),
):
    """
    Returns list of experiments recorded in VAULT with execution statuses and parameters.
    """
    experiments, total = ExperimentService.list_experiments(
        db, skip=skip, limit=limit, tool_type=tool_type, status=status_filter
    )
    return ExperimentListResponse(
        total=total,
        items=[ExperimentRead.model_validate(e) for e in experiments],
    )


@router.post(
    "",
    response_model=ExperimentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new experiment",
)
def create_experiment(
    payload: ExperimentCreate,
    db: Session = Depends(get_db),
):
    """
    Registers a new training, evaluation, curation, or safety experiment run.
    """
    exp = ExperimentService.create_experiment(payload, db)
    return ExperimentRead.model_validate(exp)
