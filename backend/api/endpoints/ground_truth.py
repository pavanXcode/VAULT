"""
Ground truth dataset validation endpoints.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.schemas.ground_truth import (
    GroundTruthValidationRequest,
    GroundTruthValidationResponse,
)
from backend.services.ground_truth_service import GroundTruthService

router = APIRouter(prefix="/ground-truth", tags=["Ground Truth"])


@router.post(
    "/validate",
    response_model=GroundTruthValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate ground truth evaluation dataset",
)
def validate_ground_truth(
    payload: GroundTruthValidationRequest,
    db: Session = Depends(get_db),
):
    """
    Validates a ground truth dataset against quality gates:
    - Empty prompt/answer detection
    - Length constraints
    - Duplicate detection
    - Source context grounding / hallucination checks
    - Aggregate statistics
    """
    return GroundTruthService.validate_dataset(payload, db)
