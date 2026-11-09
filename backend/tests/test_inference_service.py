"""
Unit and integration tests for Approved Model Inference Service,
Evidence Grounding, Citation Allowlisting, and Release Gate Enforcement.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.models.record import ScientificRecord
from backend.models.assessment import ScientificAssessment
from backend.models.release import ModelRelease
from backend.services.inference_service import InferenceService
from backend.services.release_gate import ReleaseGateService
from backend.services.record_service import RecordService, compute_record_hash
from backend.schemas.record import ScientificRecordInput


def test_inference_blocked_when_no_model_approved(db_session: Session):
    """Inference must be strictly blocked if no model has been approved by a human officer."""
    # Ensure no release is marked approved
    db_session.query(ModelRelease).filter(ModelRelease.status == "approved").update({"status": "superseded"})
    db_session.commit()

    service = InferenceService()
    auth = service.check_serving_authorized(db_session)
    assert auth["authorized"] is False
    assert "SERVING BLOCKED" in auth["message"]


@pytest.mark.anyio
async def test_inference_allowed_and_grounded_when_model_approved(db_session: Session):
    """When a model is officially approved, inference runs and grounds response in verified evidence."""
    # 1. Ingest a scientific record
    record_input = ScientificRecordInput(
        record_id="REC-TEST-INF-001",
        method_id="MTH-STD-01",
        mass_mg=15.0,
        volume_l=0.5,
        reported_mg_per_l=3.0,
        threshold_mg_per_l=10.0,
        threshold_measurand="total_concentration",
        original_verdict="PASS",
    )
    rec, assessment = RecordService.ingest_record(record_input, db_session)
    assert assessment.status == "flagged"

    # 2. Approve M2-gated-lora
    gate = ReleaseGateService()
    rel = gate.evaluate_model_candidate(
        db_session,
        {
            "model_id": "M2-gated-lora",
            "model_name": "Tiny Aya Evidence-Gated LoRA",
            "checkpoint_hash": "37799d61ce1f5511ed72adf5ff8fa94689c9018fc1e8a1ea17a76d24e44be8c4",
            "metrics": {
                "domain_accuracy": 0.884,
                "safety_compliance": 0.971,
                "over_refusal_rate": 0.000,
            },
            "evaluation_refs": ["auditkit-m2-run-001", "safetune-m2-run-001"],
        },
    )
    gate.record_signoff(
        db_session,
        release_id=rel.release_id,
        officer_name="Dr. Pawan Kumar",
        decision="approved",
        notes="Empirically verified best candidate on Scintest benchmark.",
    )

    # 3. Query Inference Service
    service = InferenceService()
    resp = await service.generate_response(
        db=db_session,
        question="Why was experiment REC-TEST-INF-001 flagged by the verifier?",
        record_id="REC-TEST-INF-001",
    )

    assert resp["success"] is True
    assert resp["model_id"] == "M2-gated-lora"
    assert resp["reviewed_by"] == "Dr. Pawan Kumar"
    assert "REC-TEST-INF-001" in resp["cited_source_ids"]
    assert "[SOURCE:REC-TEST-INF-001]" in resp["answer"]
    assert "FLAGGED" in resp["answer"]


def test_api_assistant_ask_endpoint(client: TestClient, db_session: Session):
    """Test the /api/assistant/ask REST endpoint."""
    # 1. Ingest test record
    record_input = ScientificRecordInput(
        record_id="REC-API-ASSIST-01",
        method_id="MTH-STD-01",
        mass_mg=20.0,
        volume_l=1.0,
        reported_mg_per_l=20.0,
        threshold_mg_per_l=15.0,
        threshold_measurand="total_concentration",
        original_verdict="FAIL",
    )
    RecordService.ingest_record(record_input, db_session)

    # 2. Approve model candidate
    gate = ReleaseGateService()
    rel = gate.evaluate_model_candidate(
        db_session,
        {
            "model_id": "M2-gated-lora",
            "model_name": "Tiny Aya Evidence-Gated LoRA",
            "checkpoint_hash": "37799d61ce1f5511ed72adf5ff8fa94689c9018fc1e8a1ea17a76d24e44be8c4",
            "metrics": {
                "domain_accuracy": 0.884,
                "safety_compliance": 0.971,
                "over_refusal_rate": 0.000,
            },
            "evaluation_refs": ["auditkit-1", "safetune-1"],
        },
    )
    gate.record_signoff(
        db_session,
        release_id=rel.release_id,
        officer_name="Dr. Pawan Kumar",
        decision="approved",
        notes="Official signoff for testing.",
    )

    # 3. Request via client
    res = client.post(
        "/api/assistant/ask",
        json={
            "query": "Review REC-API-ASSIST-01 findings",
            "include_scientific_memory": True,
            "record_scope": ["REC-API-ASSIST-01"],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "M2-gated-lora" in data["model_version"]
    assert "REC-API-ASSIST-01" in data["reply"]
