"""
Research Assistant and Live Experiment Review API.
Directly invokes the SAME scientific verifier used across data curation.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.record import ScientificRecord
from backend.schemas.record import ScientificRecordInput
from backend.schemas.assessment import ScientificAssessmentResponse
from backend.schemas.llm import LLMGenerateRequest
from backend.services.record_service import RecordService
from backend.services.llm_service import LocalLLMClient
from backend.services.auth_service import UserSession, get_current_user

router = APIRouter(prefix="/assistant", tags=["Research Assistant"])


class AssistantAskRequest(BaseModel):
    query: str = Field(..., description="Researcher query")
    include_scientific_memory: bool = Field(default=True, description="Retrieve verified records for context")
    record_scope: Optional[List[str]] = Field(default=None, description="Optional filter of record IDs to scope")


class AssistantAskResponse(BaseModel):
    reply: str
    evidence_citations: List[Dict[str, Any]]
    model_version: str
    timestamp: str


@router.post(
    "/review-record",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Live research record review by assistant",
)
def assistant_review_record(
    record: ScientificRecordInput,
    db: Session = Depends(get_db),
):
    """
    Submits a new candidate or flawed experiment through the assistant:
    - Uses the exact same scientific verification engine as data curation.
    - Saves the raw record and registers the assessment.
    - Returns structured warnings, discrepancy details, and unchanged raw data.
    """
    try:
        record_model, assessment = RecordService.ingest_record(record, db)
        return {
            "record_id": record_model.record_id,
            "source_hash": record_model.content_hash,
            "verification_status": assessment.status,
            "issues": assessment.issues,
            "evidence": assessment.evidence,
            "derived": assessment.derived,
            "original_verdict": record_model.original_verdict,
            "finding_id": assessment.finding_id,
            "warning_message": (
                f"Discrepancies detected in record {record_model.record_id}: {'; '.join(assessment.issues)}"
                if assessment.issues
                else f"Record {record_model.record_id} passed all automated verification checks."
            ),
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.post(
    "/ask",
    response_model=AssistantAskResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask research assistant with scientific memory citations",
)
async def assistant_ask(
    payload: AssistantAskRequest,
    db: Session = Depends(get_db),
    user: UserSession = Depends(get_current_user),
):
    """
    Queries the VAULT research assistant.
    Grounds answers in immutable scientific records and append-only findings.
    Enforces role-based authorization and data scoping.
    """
    citations: List[Dict[str, Any]] = []
    context_blocks: List[str] = []

    # Ingest query via InferenceService with Release Gate Governance
    from backend.services.inference_service import inference_service

    inf_resp = await inference_service.generate_response(
        db=db,
        question=payload.query,
        record_id=payload.record_scope[0] if payload.record_scope else None,
        caller_id=f"user:{user.username}",
        user=user,
    )

    from datetime import datetime, timezone
    return AssistantAskResponse(
        reply=inf_resp.get("answer", ""),
        evidence_citations=inf_resp.get("evidence", citations),
        model_version=f"{inf_resp.get('model_id') or 'Unapproved'} (Release: {inf_resp.get('release_id') or 'None'})",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
