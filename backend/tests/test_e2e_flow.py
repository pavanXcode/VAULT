"""
End-to-End "Golden Demo Flow" Integration Test for VAULT.
Validates the complete required hackathon user path:
Upload -> Verify (Vijay Rule Engine) -> Train Worker (Rohit Adapter) ->
Audit & SafeTune Checks -> Release Gate Human Sign-off ->
Approved Inference with Evidence Citations -> Live Review / Retrospective Warnings.
"""

import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.models.record import ScientificRecord
from backend.models.assessment import ScientificAssessment
from backend.models.release import ModelRelease


def test_vault_golden_demo_flow(client: TestClient, db_session: Session):
    """
    Executes the complete end-to-end golden flow across all subsystems.
    """
    # =========================================================================
    # Step 1: Ingest Raw Laboratory Record with Flawed Calculation
    # =========================================================================
    # 15.0 mg / 0.5 L = 30.0 mg/L. Reported: 3.0 mg/L marked PASS. Threshold: 10.0 mg/L.
    rec_payload = {
        "record_id": "REC-GOLDEN-2026-001",
        "method_id": "MTH-STD-01",
        "mass_mg": 15.0,
        "volume_l": 0.5,
        "reported_mg_per_l": 3.0,
        "threshold_mg_per_l": 10.0,
        "threshold_measurand": "total_concentration",
        "original_verdict": "PASS",
        "calibration_valid_until": "2030-01-01",
        "source_refs": ["SOP-LAB-101", "CAL-BAL-04"],
    }

    ingest_res = client.post("/api/records/ingest", json=rec_payload)
    assert ingest_res.status_code == 201
    ingest_data = ingest_res.json()
    assert ingest_data["assessment"]["status"] == "flagged"
    assert len(ingest_data["assessment"]["issues"]) >= 2  # Arithmetic error + regulatory threshold
    assert ingest_data["assessment"]["derived"]["calculated_mg_per_l"] == 30.0
    original_hash = ingest_data["record"]["content_hash"]
    assert len(original_hash) == 64

    # Verify immutability in database
    db_rec = db_session.query(ScientificRecord).filter_by(record_id="REC-GOLDEN-2026-001").first()
    assert db_rec is not None
    assert db_rec.content_hash == original_hash

    # =========================================================================
    # Step 2: Submit Pipeline Job (Model Fine-Tuning Stage)
    # =========================================================================
    job_payload = {
        "tool_name": "train_adapter",
        "stage": "train",
        "parameters": {
            "model": "tiny-aya-gated-m2",
            "dataset": "data/synthetic/records.jsonl",
            "epochs": 3,
            "learning_rate": 2e-4,
        },
        "input_artifact_ids": ["ds-manifest-sha256-golden"],
        "max_retries": 3,
    }

    job_res = client.post("/api/jobs", json=job_payload)
    assert job_res.status_code == 201
    job_info = job_res.json()
    job_id = job_info["job_id"]
    assert job_info["stage"] == "train"
    assert job_info["config_hash"] is not None

    # Poll job result (bounded)
    time.sleep(0.3)
    result_res = client.get(f"/api/jobs/{job_id}/result")
    assert result_res.status_code == 200

    # =========================================================================
    # Step 3: Evaluate Candidate Model (M2 Evidence-Gated LoRA)
    # =========================================================================
    eval_payload = {
        "model_id": "M2-gated-lora",
        "model_name": "Tiny Aya Evidence-Gated LoRA",
        "stage": "release",
        "checkpoint_hash": "37799d61ce1f5511ed72adf5ff8fa94689c9018fc1e8a1ea17a76d24e44be8c4",
        "metrics": {
            "domain_accuracy": 0.884,  # > 0.85
            "safety_compliance": 0.971,  # > 0.95
            "over_refusal_rate": 0.000,  # <= 0.10
            "sample_size": 250,
        },
        "evaluation_refs": ["auditkit-m2-golden-run", "safetune-m2-golden-run"],
        "is_mock": False,
    }

    eval_res = client.post("/api/models/M2-gated-lora/evaluate", json=eval_payload)
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["status"] == "candidate"
    release_id = eval_data["release_id"]

    # =========================================================================
    # Step 4: Release Gate Human Sign-Off (Governance Invariant)
    # =========================================================================
    # 4a. Automated self-approval MUST be rejected
    auto_res = client.post(
        "/api/models/M2-gated-lora/release-decision",
        json={
            "release_id": release_id,
            "officer_name": "LLM Copilot",
            "decision": "approved",
            "notes": "Automated pipeline sign-off attempt",
        },
    )
    assert auto_res.status_code == 422
    assert "Automated or LLM self-approvals are strictly forbidden" in auto_res.json()["detail"]

    # 4b. Legitimate named human officer sign-off succeeds
    human_res = client.post(
        "/api/models/M2-gated-lora/release-decision",
        json={
            "release_id": release_id,
            "officer_name": "Dr. Pawan Kumar",
            "decision": "approved",
            "notes": "Certified Scintest domain accuracy 88.4% and zero over-refusal.",
        },
    )
    assert human_res.status_code == 200
    human_data = human_res.json()
    assert human_data["status"] == "approved"
    assert human_data["reviewed_by"] == "Dr. Pawan Kumar"

    # Verify active serving pointer is now M2-gated-lora
    active_res = client.get("/api/models/releases/active")
    assert active_res.status_code == 200
    active_data = active_res.json()
    assert active_data["serving_permitted"] is True
    assert active_data["active_release"]["model_id"] == "M2-gated-lora"

    # =========================================================================
    # Step 5: Evidence-Grounded Research Assistant Chat
    # =========================================================================
    chat_res = client.post(
        "/api/assistant/ask",
        json={
            "query": "Explain why experiment REC-GOLDEN-2026-001 was flagged",
            "include_scientific_memory": True,
            "record_scope": ["REC-GOLDEN-2026-001"],
        },
    )
    assert chat_res.status_code == 200
    chat_data = chat_res.json()

    # Verify grounded citations and approved model identity
    assert "M2-gated-lora" in chat_data["model_version"]
    assert "REC-GOLDEN-2026-001" in chat_data["reply"]
    assert "[SOURCE:REC-GOLDEN-2026-001]" in chat_data["reply"]
    assert "FLAGGED" in chat_data["reply"]
    assert "30.0 mg/L" in chat_data["reply"]

    # =========================================================================
    # Step 6: Retrospective Review & Immutability Verification
    # =========================================================================
    # Verify original record payload and SHA-256 remain unchanged
    history_res = client.get("/api/records/REC-GOLDEN-2026-001/history")
    assert history_res.status_code == 200
    history_data = history_res.json()
    assert history_data["record"]["content_hash"] == original_hash
    assert history_data["latest_status"] == "flagged"
    assert history_data["total_assessments"] >= 1
    assert history_data["has_flags"] is True
