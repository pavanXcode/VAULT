"""
Scientific Record and Scientific Memory API Endpoints.
Guarantees:
- Original records are immutable.
- Assessments and reviewer findings are append-only.
- The research assistant uses the exact same verification logic as pre-training curation.
"""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.record import ScientificRecord
from backend.schemas.record import ScientificRecordInput, ScientificRecordResponse
from backend.schemas.assessment import ScientificAssessmentResponse, RecordHistoryResponse
from backend.services.record_service import RecordService

router = APIRouter(prefix="/records", tags=["Scientific Records"])


@router.post(
    "/review",
    response_model=ScientificAssessmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Non-persistent scientific record verification",
)
def review_record(record: ScientificRecordInput):
    """
    Evaluates a candidate scientific laboratory record without persisting to database:
    - Mass and volume arithmetic checks
    - Regulatory threshold compliance
    - Methodology-specific rule checks (alternative methods, unknown methods)
    - Instrument calibration expiration
    """
    return RecordService.review_record(record)


@router.post(
    "/ingest",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Ingest record with immutable storage and append-only assessment",
)
def ingest_record(
    record: ScientificRecordInput,
    db: Session = Depends(get_db),
):
    """
    Persists a scientific record and creates its initial verification assessment:
    - Original record raw payload and SHA-256 hash are immutably stored.
    - Re-submissions with differing content are rejected to protect provenance.
    - An initial assessment finding event is recorded in the ledger.
    """
    try:
        record_model, assessment = RecordService.ingest_record(record, db)
        return {
            "record": record_model.to_dict(),
            "assessment": assessment.model_dump(),
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.get(
    "/{record_id}/history",
    response_model=RecordHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve record with chronological append-only finding ledger",
)
def get_record_history(
    record_id: str,
    db: Session = Depends(get_db),
):
    """
    Returns the unchanged original record alongside all chronological verification
    assessments, retrospective audits, and reviewer notes.
    """
    try:
        return RecordService.get_record_history(record_id, db)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get(
    "",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="List all immutable laboratory records in scientific memory",
)
def list_records(
    db: Session = Depends(get_db),
):
    """Lists all stored scientific records with their content hashes and original verdicts."""
    records = db.query(ScientificRecord).order_by(ScientificRecord.id.desc()).all()
    return [r.to_dict() for r in records]
