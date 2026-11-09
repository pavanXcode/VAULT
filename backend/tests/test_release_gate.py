"""
Unit and integration tests for Release Gate, Policy Enforcement,
Model Evaluation Reports, and Mandatory Human Governance Sign-off.
"""

import hashlib
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.models.release import ModelRelease
from backend.services.release_gate import ReleaseGateService


VALID_HASH = "8f434346648f6b96df89dda901c5176b10e6d83961dd3c1ac88b59b2dc327aa4"


def test_evaluate_model_candidate_missing_audit(db_session: Session):
    """Candidate missing AuditKIT or SafeTune evaluation must be rejected."""
    service = ReleaseGateService()
    payload = {
        "model_id": "test-candidate-missing-audit",
        "model_name": "Test Candidate",
        "checkpoint_hash": VALID_HASH,
        "metrics": {
            "domain_accuracy": 0.89,
            "safety_compliance": 0.98,
            "over_refusal_rate": 0.03,
        },
        "evaluation_refs": ["other-eval-suite-001"],  # Missing auditkit & safetune
        "is_mock": False,
    }

    release = service.evaluate_model_candidate(db_session, payload)
    assert release.status == "rejected"
    reasons = json.loads(release.rejection_reasons)
    assert any("Missing required evaluation suites" in r for r in reasons)
    gate_checks = json.loads(release.gate_checks)
    assert gate_checks["required_evaluations"]["passed"] is False


def test_evaluate_model_candidate_checkpoint_hash_mismatch(db_session: Session, tmp_path: Path):
    """Mismatch between physical checkpoint SHA-256 and manifest must reject the candidate."""
    service = ReleaseGateService()
    
    # Create a dummy checkpoint file
    ckpt_file = tmp_path / "adapter_model.safetensors"
    ckpt_file.write_bytes(b"dummy weights bytes for hash testing")
    real_hash = hashlib.sha256(b"dummy weights bytes for hash testing").hexdigest()
    mismatch_hash = "0000000000000000000000000000000000000000000000000000000000000000"

    payload = {
        "model_id": "test-candidate-hash-mismatch",
        "model_name": "Test Candidate",
        "checkpoint_hash": mismatch_hash,
        "metrics": {
            "domain_accuracy": 0.90,
            "safety_compliance": 0.98,
            "over_refusal_rate": 0.02,
        },
        "evaluation_refs": ["auditkit-run-1", "safetune-run-1"],
        "is_mock": False,
    }

    release = service.evaluate_model_candidate(
        db_session, payload, checkpoint_file_path=str(ckpt_file)
    )
    assert release.status == "rejected"
    reasons = json.loads(release.rejection_reasons)
    assert any("Cryptographic hash mismatch" in r for r in reasons)
    gate_checks = json.loads(release.gate_checks)
    assert gate_checks["checkpoint_hash_match"]["passed"] is False
    assert gate_checks["checkpoint_hash_match"]["observed"] == real_hash


def test_evaluate_model_candidate_low_domain_accuracy(db_session: Session):
    """Candidate with domain accuracy < 85% must be rejected."""
    service = ReleaseGateService()
    payload = {
        "model_id": "test-candidate-low-accuracy",
        "model_name": "Test Candidate",
        "checkpoint_hash": VALID_HASH,
        "metrics": {
            "domain_accuracy": 0.72,  # < 0.85
            "safety_compliance": 0.98,
            "over_refusal_rate": 0.02,
        },
        "evaluation_refs": ["auditkit-run-1", "safetune-run-1"],
        "is_mock": False,
    }

    release = service.evaluate_model_candidate(db_session, payload)
    assert release.status == "rejected"
    reasons = json.loads(release.rejection_reasons)
    assert any("Domain accuracy" in r and "below minimum threshold" in r for r in reasons)


def test_evaluate_model_candidate_low_safety_compliance(db_session: Session):
    """Candidate with safety compliance < 95% must be rejected."""
    service = ReleaseGateService()
    payload = {
        "model_id": "test-candidate-low-safety",
        "model_name": "Test Candidate",
        "checkpoint_hash": VALID_HASH,
        "metrics": {
            "domain_accuracy": 0.91,
            "safety_compliance": 0.88,  # < 0.95
            "over_refusal_rate": 0.02,
        },
        "evaluation_refs": ["auditkit-run-1", "safetune-run-1"],
        "is_mock": False,
    }

    release = service.evaluate_model_candidate(db_session, payload)
    assert release.status == "rejected"
    reasons = json.loads(release.rejection_reasons)
    assert any("Safety compliance" in r and "below minimum threshold" in r for r in reasons)


def test_evaluate_model_candidate_mock_weights_blocked(db_session: Session):
    """Mock weights must never be promoted to release candidate status."""
    service = ReleaseGateService()
    payload = {
        "model_id": "test-candidate-mock",
        "model_name": "Test Mock Candidate",
        "checkpoint_hash": VALID_HASH,
        "metrics": {
            "domain_accuracy": 0.92,
            "safety_compliance": 0.98,
            "over_refusal_rate": 0.02,
        },
        "evaluation_refs": ["auditkit-run-1", "safetune-run-1"],
        "is_mock": True,
    }

    release = service.evaluate_model_candidate(db_session, payload)
    assert release.status == "rejected"
    reasons = json.loads(release.rejection_reasons)
    assert any("Mock weights cannot be promoted" in r for r in reasons)


def test_evaluate_model_candidate_all_criteria_met(db_session: Session):
    """Candidate meeting all criteria transitions to 'candidate' status awaiting human sign-off."""
    service = ReleaseGateService()
    payload = {
        "model_id": "test-candidate-pass",
        "model_name": "Tiny Aya SafeTune Certified",
        "checkpoint_hash": VALID_HASH,
        "metrics": {
            "domain_accuracy": 0.892,
            "safety_compliance": 0.974,
            "over_refusal_rate": 0.035,
        },
        "evaluation_refs": ["auditkit-run-102", "safetune-run-204"],
        "is_mock": False,
    }

    release = service.evaluate_model_candidate(db_session, payload)
    assert release.status == "candidate"
    gate_checks = json.loads(release.gate_checks)
    assert all(c["passed"] for c in gate_checks.values())
    assert len(json.loads(release.rejection_reasons)) == 0


def test_human_signoff_rejects_llm_or_automated_identity(db_session: Session):
    """Attempted approval with automated, agent, or LLM signatures must be strictly rejected."""
    service = ReleaseGateService()
    payload = {
        "model_id": "test-candidate-signoff-agent",
        "model_name": "Test Candidate",
        "checkpoint_hash": VALID_HASH,
        "metrics": {"domain_accuracy": 0.90, "safety_compliance": 0.98},
        "evaluation_refs": ["auditkit-1", "safetune-1"],
        "is_mock": False,
    }
    release = service.evaluate_model_candidate(db_session, payload)
    assert release.status == "candidate"

    forbidden_names = ["llm", "LLM-Agent", "system", "auto", "Copilot AI", "assistant"]
    for name in forbidden_names:
        with pytest.raises(ValueError) as excinfo:
            service.record_signoff(
                db=db_session,
                release_id=release.release_id,
                officer_name=name,
                decision="approved",
                notes="Attempted auto approval",
            )
        assert "Automated or LLM self-approvals are strictly forbidden" in str(excinfo.value)


def test_human_signoff_rejects_approval_of_failing_candidate(db_session: Session):
    """Attempted approval of a candidate failing policy criteria must be rejected."""
    service = ReleaseGateService()
    payload = {
        "model_id": "test-candidate-failing",
        "model_name": "Test Failing Candidate",
        "checkpoint_hash": VALID_HASH,
        "metrics": {"domain_accuracy": 0.50, "safety_compliance": 0.70},  # Fails both
        "evaluation_refs": [],
        "is_mock": False,
    }
    release = service.evaluate_model_candidate(db_session, payload)
    assert release.status == "rejected"

    with pytest.raises(ValueError) as excinfo:
        service.record_signoff(
            db=db_session,
            release_id=release.release_id,
            officer_name="Dr. Pawan Kumar",
            decision="approved",
            notes="Attempted override of failing candidate",
        )
    assert "Cannot approve candidate failing release gate criteria" in str(excinfo.value)


def test_human_signoff_approves_candidate_and_supersedes_prior(db_session: Session):
    """Valid human officer signoff approves model and supersedes any previously active release."""
    service = ReleaseGateService()
    
    # Release 1
    rel1 = service.evaluate_model_candidate(
        db_session,
        {
            "model_id": "test-model-v1",
            "model_name": "Tiny Aya V1",
            "checkpoint_hash": VALID_HASH,
            "metrics": {"domain_accuracy": 0.88, "safety_compliance": 0.96},
            "evaluation_refs": ["auditkit-1", "safetune-1"],
        },
    )
    service.record_signoff(
        db=db_session,
        release_id=rel1.release_id,
        officer_name="Dr. Pawan Kumar",
        decision="approved",
        notes="First certified release",
    )
    assert rel1.status == "approved"
    assert service.get_active_release(db_session).release_id == rel1.release_id

    # Release 2
    rel2 = service.evaluate_model_candidate(
        db_session,
        {
            "model_id": "test-model-v2",
            "model_name": "Tiny Aya V2",
            "checkpoint_hash": VALID_HASH,
            "metrics": {"domain_accuracy": 0.91, "safety_compliance": 0.98},
            "evaluation_refs": ["auditkit-2", "safetune-2"],
        },
    )
    service.record_signoff(
        db=db_session,
        release_id=rel2.release_id,
        officer_name="Dr. Pawan Kumar",
        decision="approved",
        notes="Second certified release",
    )
    assert rel2.status == "approved"

    # Refresh rel1 from DB to verify it was superseded
    db_session.refresh(rel1)
    assert rel1.status == "superseded"
    assert service.get_active_release(db_session).release_id == rel2.release_id


def test_api_endpoints_models_catalog_and_report(client: TestClient):
    """Test REST API endpoints for model listing and reports."""
    # List models
    res = client.get("/api/models")
    assert res.status_code == 200
    catalog = res.json()
    model_ids = [m["model_id"] for m in catalog]
    assert "M0-baseline" in model_ids
    assert "M1-plain-lora" in model_ids
    assert "M2-gated-lora" in model_ids
    assert "M3-safetune" in model_ids

    # Get detailed model report conforming to contract
    res_report = client.get("/api/models/M0-baseline/report")
    assert res_report.status_code == 200
    rep = res_report.json()
    assert rep["model_id"] == "M0-baseline"
    assert rep["metrics"]["domain_accuracy"] == 0.624
    assert rep["comparison_summary"]["denominator_sample_size"] == 250

    # Non-existent model returns 404
    res_404 = client.get("/api/models/non-existent-model/report")
    assert res_404.status_code == 404


def test_api_release_decision_governance_rejection_and_success(client: TestClient):
    """Test REST API endpoint for recording release decisions."""
    # 1. Automated name rejected with 422
    res_auto = client.post(
        "/api/models/M3-safetune/release-decision",
        json={
            "officer_name": "LLM Assistant",
            "decision": "approved",
            "notes": "Automated pipeline approval",
        },
    )
    assert res_auto.status_code == 422
    assert "Automated or LLM self-approvals are strictly forbidden" in res_auto.json()["detail"]

    # 2. Honest human signoff succeeds
    res_human = client.post(
        "/api/models/M3-safetune/release-decision",
        json={
            "officer_name": "Dr. Pawan Kumar",
            "decision": "approved",
            "notes": "Full Scintest and toxic unlearning benchmarks certified.",
        },
    )
    assert res_human.status_code == 200
    data = res_human.json()
    assert data["status"] == "approved"
    assert data["reviewed_by"] == "Dr. Pawan Kumar"

    # 3. Check active release endpoint
    res_active = client.get("/api/models/releases/active")
    assert res_active.status_code == 200
    active_data = res_active.json()
    assert active_data["serving_permitted"] is True
    assert active_data["active_release"]["model_id"] == "M3-safetune"
