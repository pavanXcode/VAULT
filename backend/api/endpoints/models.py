"""
API endpoints for Model Runs, Evaluation Reports, and Release Gate Governance.
Enforces frozen evaluation policy, cryptographic checkpoint verification,
and mandatory named human officer sign-off before model promotion.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.release import ModelRelease
from backend.schemas.release import (
    ModelCandidatePayload,
    ReleaseSignoffRequest,
    ModelReportResponse,
)
from backend.services.release_gate import release_gate_service

logger = logging.getLogger("vault.api.models")
router = APIRouter(prefix="/models", tags=["Models & Release Gate"])


@router.get("", response_model=List[Dict[str, Any]])
def list_models(db: Session = Depends(get_db)):
    """
    Returns the M0-M3 model catalog with evaluation status, sample sizes,
    and release gate states. Never fabricates metrics.
    """
    try:
        return release_gate_service.get_model_catalog(db)
    except Exception as exc:
        logger.error(f"Failed to list model catalog: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve model catalog: {str(exc)}",
        )


@router.get("/releases", response_model=List[Dict[str, Any]])
def list_releases(
    model_id: Optional[str] = Query(None, description="Filter by model ID"),
    db: Session = Depends(get_db),
):
    """Lists recorded release evaluations and human decisions."""
    try:
        query = db.query(ModelRelease)
        if model_id:
            query = query.filter(ModelRelease.model_id == model_id)
        releases = query.order_by(ModelRelease.id.desc()).all()
        return [r.to_dict() for r in releases]
    except Exception as exc:
        logger.error(f"Failed to list releases: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query releases: {str(exc)}",
        )


@router.get("/releases/active")
def get_active_release(db: Session = Depends(get_db)):
    """Returns the currently active approved model release for inference."""
    active = release_gate_service.get_active_release(db)
    if not active:
        return {
            "active_release": None,
            "serving_permitted": False,
            "message": "No model release is currently approved by a human officer.",
        }
    return {
        "active_release": active.to_dict(),
        "serving_permitted": True,
        "message": f"Model '{active.model_id}' is approved for inference serving.",
    }


@router.get("/{model_id}/report", response_model=ModelReportResponse)
def get_model_report(model_id: str, db: Session = Depends(get_db)):
    """
    Returns detailed model run evaluation report conforming to contracts/model_run.schema.json,
    including gate checks, provenance, sample sizes, and comparison data.
    """
    catalog = release_gate_service.get_model_catalog(db)
    model_entry = next((m for m in catalog if m["model_id"].lower() == model_id.lower()), None)
    
    if not model_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' not found in catalog (available: {[m['model_id'] for m in catalog]}).",
        )

    # Fetch latest release entry if present in DB
    latest_release = (
        db.query(ModelRelease)
        .filter(ModelRelease.model_id == model_entry["model_id"])
        .order_by(ModelRelease.id.desc())
        .first()
    )

    gate_checks = json.loads(latest_release.gate_checks) if latest_release and latest_release.gate_checks else None
    rejection_reasons = (
        json.loads(latest_release.rejection_reasons) if latest_release and latest_release.rejection_reasons else None
    )

    # Build comparison summary comparing with M0 baseline
    m0 = next((m for m in catalog if m["model_id"] == "M0-baseline"), None)
    m0_acc = (m0.get("metrics") or {}).get("domain_accuracy", 0.624) if m0 else 0.624
    curr_acc = (model_entry.get("metrics") or {}).get("domain_accuracy")
    delta_acc = round(curr_acc - m0_acc, 4) if curr_acc is not None else None

    comparison_summary = {
        "baseline_model_id": "M0-baseline",
        "domain_accuracy_delta": delta_acc,
        "benchmark_dataset": "Scintest-Lab-v1.0 (Synthetic)",
        "denominator_sample_size": (model_entry.get("metrics") or {}).get("sample_size", 250),
    }

    return ModelReportResponse(
        model_id=model_entry["model_id"],
        model_name=model_entry["model_name"],
        description=model_entry.get("description"),
        stage=model_entry.get("stage", "train"),
        checkpoint_hash=model_entry.get("checkpoint_hash"),
        checkpoint_path=f"checkpoints/{model_entry['model_id']}/adapter_model.safetensors"
        if model_entry.get("checkpoint_hash")
        else None,
        metrics=model_entry.get("metrics") or {},
        evaluation_refs=model_entry.get("evaluation_refs") or [],
        is_mock=model_entry.get("status") == "mock",
        status=latest_release.status if latest_release else model_entry.get("status", "candidate"),
        latest_release_id=latest_release.release_id if latest_release else None,
        reviewed_by=latest_release.reviewed_by if latest_release else None,
        reviewed_at=latest_release.reviewed_at.isoformat() if latest_release and latest_release.reviewed_at else None,
        gate_checks=gate_checks,
        rejection_reasons=rejection_reasons,
        comparison_summary=comparison_summary,
    )


@router.post("/{model_id}/evaluate", response_model=Dict[str, Any])
def evaluate_model_release(
    model_id: str,
    payload: Optional[ModelCandidatePayload] = None,
    db: Session = Depends(get_db),
):
    """
    Evaluates a candidate model against frozen release gate criteria.
    Updates or inserts a ModelRelease record in 'candidate' or 'rejected' state.
    """
    catalog = release_gate_service.get_model_catalog(db)
    model_entry = next((m for m in catalog if m["model_id"].lower() == model_id.lower()), None)
    
    if not model_entry and not payload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' not found in catalog and no payload provided.",
        )

    # Use provided payload or fall back to catalog defaults
    if payload:
        data = payload.dict()
    else:
        data = {
            "model_id": model_entry["model_id"],
            "model_name": model_entry["model_name"],
            "stage": model_entry.get("stage", "release"),
            "checkpoint_hash": model_entry.get("checkpoint_hash") or "",
            "metrics": model_entry.get("metrics") or {},
            "evaluation_refs": model_entry.get("evaluation_refs") or [],
            "is_mock": False,
        }

    try:
        release = release_gate_service.evaluate_model_candidate(
            db=db,
            model_payload=data,
            checkpoint_file_path=data.get("checkpoint_path"),
        )
        return release.to_dict()
    except Exception as exc:
        logger.error(f"Gate evaluation error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Evaluation failed: {str(exc)}",
        )


@router.post("/{model_id}/release-decision", response_model=Dict[str, Any])
def record_release_decision(
    model_id: str,
    signoff: ReleaseSignoffRequest,
    db: Session = Depends(get_db),
):
    """
    Records a human officer's release sign-off decision (Approved / Rejected).
    Enforces governance rules:
    - Automated / LLM identities are strictly rejected.
    - Approvals for models that fail gate checks are rejected.
    """
    # Find release record to sign off
    release = None
    if signoff.release_id:
        release = db.query(ModelRelease).filter(ModelRelease.release_id == signoff.release_id).first()
    else:
        # Get latest candidate for this model
        release = (
            db.query(ModelRelease)
            .filter(ModelRelease.model_id.ilike(model_id))
            .order_by(ModelRelease.id.desc())
            .first()
        )

    # If no release candidate exists yet, run evaluation first
    if not release:
        catalog = release_gate_service.get_model_catalog(db)
        model_entry = next((m for m in catalog if m["model_id"].lower() == model_id.lower()), None)
        if not model_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model '{model_id}' not found.",
            )
        data = {
            "model_id": model_entry["model_id"],
            "model_name": model_entry["model_name"],
            "checkpoint_hash": model_entry.get("checkpoint_hash") or "",
            "metrics": model_entry.get("metrics") or {},
            "evaluation_refs": model_entry.get("evaluation_refs") or [],
        }
        release = release_gate_service.evaluate_model_candidate(db, data)

    try:
        updated = release_gate_service.record_signoff(
            db=db,
            release_id=release.release_id,
            officer_name=signoff.officer_name,
            decision=signoff.decision,
            notes=signoff.notes or "",
        )
        return updated.to_dict()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(f"Error recording signoff: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record sign-off: {str(exc)}",
        )
