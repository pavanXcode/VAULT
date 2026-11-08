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
):
    """
    Queries the VAULT research assistant.
    Grounds answers in immutable scientific records and append-only findings.
    """
    citations: List[Dict[str, Any]] = []
    context_blocks: List[str] = []

    if payload.include_scientific_memory:
        query = db.query(ScientificRecord)
        if payload.record_scope:
            query = query.filter(ScientificRecord.record_id.in_(payload.record_scope))
        records = query.order_by(ScientificRecord.id.desc()).limit(10).all()

        for r in records:
            history = RecordService.get_record_history(r.record_id, db)
            citations.append({
                "record_id": r.record_id,
                "content_hash": r.content_hash,
                "method_id": r.method_id,
                "original_verdict": r.original_verdict,
                "latest_status": history.latest_status,
                "issues_count": len(history.assessments[-1].issues) if history.assessments else 0,
            })
            context_blocks.append(
                f"[Record {r.record_id} | Hash: {r.content_hash[:8]} | Method: {r.method_id} | Original Verdict: {r.original_verdict} | Latest Status: {history.latest_status}]"
            )

    # Build prompt with grounded context
    context_str = "\n".join(context_blocks) if context_blocks else "No records currently in memory."
    prompt = (
        f"You are the VAULT Scientific Research Assistant. Answer the researcher's query using the verified records below.\n\n"
        f"Verified Scientific Records:\n{context_str}\n\n"
        f"Researcher Query: {payload.query}\n\n"
        f"Answer with explicit citations to record IDs and their verification status:"
    )

    llm_req = LLMGenerateRequest(prompt=prompt, max_tokens=300)
    llm_client = LocalLLMClient()
    llm_resp = await llm_client.generate(llm_req)

    from datetime import datetime, timezone
    return AssistantAskResponse(
        reply=llm_resp.content,
        evidence_citations=citations,
        model_version=f"{llm_resp.model} ({llm_resp.mode})",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
