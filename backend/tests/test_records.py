"""
Unit and integration tests for Scientific Records, Append-Only Assessments,
and the Four Mandatory Scientific Verification Scenarios (Playbook Section 3).
"""

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.models.record import ScientificRecord
from backend.models.assessment import ScientificAssessment
from backend.services.record_service import RecordService, compute_record_hash
from backend.schemas.record import ScientificRecordInput


def test_scenario_1_arithmetic_mismatch_marked_pass(client: TestClient):
    """
    Scenario 1 (Mandatory): Recorded mass 15 mg, volume 0.5 L, reported 3 mg/L, threshold 10 mg/L.
    True concentration is 30 mg/L. The engine must compute 30 mg/L, flag the arithmetic discrepancy,
    flag the threshold violation (claimed PASS despite true concentration > threshold), and show assumptions.
    """
    payload = {
        "record_id": "REC-SCENARIO-1",
        "mass_mg": 15.0,
        "volume_l": 0.5,
        "reported_mg_per_l": 3.0,
        "threshold_mg_per_l": 10.0,
        "method_id": "MTH-STD-01",
        "threshold_measurand": "total_concentration",
        "original_verdict": "PASS",
        "calibration_valid_until": "2030-01-01",
        "source_refs": ["SOP-ENV-101"],
    }

    response = client.post("/api/records/review", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "flagged"
    assert data["original_verdict"] == "PASS"
    assert len(data["issues"]) >= 2  # Arithmetic mismatch + threshold violation
    assert data["derived"]["calculated_mg_per_l"] == 30.0

    # Ensure evidence captures the exact calculated and reported numbers
    arithmetic_evidence = [e for e in data["evidence"] if e.get("rule") == "arithmetic_concentration"]
    assert len(arithmetic_evidence) == 1
    assert arithmetic_evidence[0]["expected"] == 30.0
    assert arithmetic_evidence[0]["actual"] == 3.0

    threshold_evidence = [e for e in data["evidence"] if e.get("rule") == "regulatory_threshold"]
    assert len(threshold_evidence) == 1
    assert threshold_evidence[0]["actual"] == 30.0


def test_scenario_2_valid_alternative_method_fraction(client: TestClient):
    """
    Scenario 3 (Mandatory): Valid alternative method calculating available fraction.
    An explicitly documented available-fraction calculation returns a different quantity
    from total concentration. The engine must verify the stated factor and NOT falsely reject it.
    """
    payload = {
        "record_id": "REC-SCENARIO-3-ALT",
        "mass_mg": 10.0,
        "volume_l": 1.0,
        "reported_mg_per_l": 10.0,
        "threshold_mg_per_l": 5.0,  # Total concentration (10) would exceed threshold (5)
        "method_id": "MTH-ALT-BIOAVAIL-01",
        "threshold_measurand": "available_fraction",
        "available_fraction": 0.3,  # Available concentration = 10 * 0.3 = 3.0 < 5.0
        "original_verdict": "PASS",
        "calibration_valid_until": "2030-01-01",
        "source_refs": ["SOP-ALT-BIO-02"],
    }

    response = client.post("/api/records/review", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "checks_passed"
    assert data["derived"]["available_mg_per_l"] == 3.0
    assert data["derived"]["exceeds_threshold"] is False
    assert len(data["issues"]) == 0


def test_scenario_3_unknown_method_abstention(client: TestClient):
    """
    Scenario 4 (Mandatory): Unknown new method.
    Preserve the claim and formula, mark needs_review when assumptions cannot be established.
    NEVER call it false solely for being unfamiliar.
    """
    payload = {
        "record_id": "REC-SCENARIO-4-UNK",
        "mass_mg": 5.0,
        "volume_l": 1.0,
        "reported_mg_per_l": 5.0,
        "threshold_mg_per_l": 10.0,
        "method_id": "MTH-UNK-EXPERIMENTAL-X99",
        "threshold_measurand": "total_concentration",
        "original_verdict": "PASS",
        "calibration_valid_until": "2030-01-01",
    }

    response = client.post("/api/records/review", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "needs_review"
    assert any("requires expert scientific review" in issue for issue in data["issues"])


def test_scenario_4_expired_instrument_calibration(client: TestClient):
    """Verify that measurements referencing expired calibration dates are flagged."""
    payload = {
        "record_id": "REC-EXPIRED-CAL",
        "mass_mg": 5.0,
        "volume_l": 1.0,
        "reported_mg_per_l": 5.0,
        "threshold_mg_per_l": 10.0,
        "method_id": "MTH-STD-01",
        "threshold_measurand": "total_concentration",
        "original_verdict": "PASS",
        "calibration_valid_until": "2020-01-01",  # Expired
    }

    response = client.post("/api/records/review", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "flagged"
    assert any("expired on 2020-01-01" in issue for issue in data["issues"])


def test_ingest_and_chronological_assessment_history(client: TestClient, db_session: Session):
    """
    Scenario 2 (Mandatory): Contradictory later record / Retrospective audit.
    Ingests an experiment, appends a retrospective audit finding to the ledger,
    and proves that the original record and hash remain completely unmodified.
    """
    payload = {
        "record_id": "REC-AUDIT-TARGET",
        "mass_mg": 2.0,
        "volume_l": 1.0,
        "reported_mg_per_l": 2.0,
        "threshold_mg_per_l": 10.0,
        "method_id": "MTH-STD-01",
        "threshold_measurand": "total_concentration",
        "original_verdict": "PASS",
        "calibration_valid_until": "2030-01-01",
    }

    # Step 1: Ingest record
    ingest_resp = client.post("/api/records/ingest", json=payload)
    assert ingest_resp.status_code == 201
    data = ingest_resp.json()

    orig_hash = data["record"]["content_hash"]
    first_finding_id = data["assessment"]["finding_id"]
    assert data["assessment"]["status"] == "checks_passed"

    # Step 2: Append a retrospective audit finding undermining the experiment
    audit_finding = RecordService.append_finding(
        record_id="REC-AUDIT-TARGET",
        status="flagged",
        issues=["Retrospective calibration audit revealed scale drift on INST-BAL-04 on run date."],
        evidence=[{"rule": "retrospective_audit", "instrument": "INST-BAL-04", "drift_detected": True}],
        supersedes_id=first_finding_id,
        db=db_session,
    )
    assert audit_finding.status == "flagged"
    assert audit_finding.supersedes_id == first_finding_id

    # Step 3: Fetch record history
    hist_resp = client.get("/api/records/REC-AUDIT-TARGET/history")
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()

    # Invariants:
    # 1. Original record is unchanged and hash is stable
    assert hist_data["record"]["content_hash"] == orig_hash
    assert hist_data["record"]["original_verdict"] == "PASS"

    # 2. Both assessments exist in chronological order
    assert hist_data["total_assessments"] == 2
    assert hist_data["assessments"][0]["finding_id"] == first_finding_id
    assert hist_data["assessments"][0]["status"] == "checks_passed"
    assert hist_data["assessments"][1]["finding_id"] == audit_finding.finding_id
    assert hist_data["assessments"][1]["status"] == "flagged"

    # 3. Overall history reflects flags
    assert hist_data["has_flags"] is True
    assert hist_data["latest_status"] == "flagged"


def test_ingest_duplicate_differing_payload_rejected(client: TestClient):
    """Protects against silent modification: Re-uploading with different values fails with 409 Conflict."""
    payload1 = {
        "record_id": "REC-CONFLICT-CHECK",
        "mass_mg": 2.0,
        "volume_l": 1.0,
        "reported_mg_per_l": 2.0,
        "threshold_mg_per_l": 10.0,
        "method_id": "MTH-STD-01",
        "threshold_measurand": "total_concentration",
        "original_verdict": "PASS",
    }
    resp1 = client.post("/api/records/ingest", json=payload1)
    assert resp1.status_code == 201

    # Modify mass from 2.0 to 99.0 under the same record_id
    payload2 = dict(payload1)
    payload2["mass_mg"] = 99.0

    resp2 = client.post("/api/records/ingest", json=payload2)
    assert resp2.status_code == 409
    assert "IMMUTABILITY CONFLICT" in resp2.json()["detail"]


def test_assistant_review_record_live_warning(client: TestClient):
    """Live assistant experiment review catches arithmetic errors and returns warnings without mutating originals."""
    payload = {
        "record_id": "REC-ASSISTANT-TEST",
        "mass_mg": 20.0,
        "volume_l": 0.5,
        "reported_mg_per_l": 4.0,  # Actually 40.0
        "threshold_mg_per_l": 10.0,
        "method_id": "MTH-STD-01",
        "threshold_measurand": "total_concentration",
        "original_verdict": "PASS",
    }

    response = client.post("/api/assistant/review-record", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["record_id"] == "REC-ASSISTANT-TEST"
    assert data["verification_status"] == "flagged"
    assert "Discrepancies detected" in data["warning_message"]
    assert data["original_verdict"] == "PASS"


def test_database_trigger_immutability(db_session: Session):
    """Guarantees that direct SQL UPDATE or DELETE on records/assessments is blocked by database triggers."""
    rec_input = ScientificRecordInput(
        record_id="REC-DB-TRIGGER-TEST",
        mass_mg=1.0,
        volume_l=1.0,
        reported_mg_per_l=1.0,
        threshold_mg_per_l=5.0,
        method_id="MTH-STD-01",
        threshold_measurand="total_concentration",
        original_verdict="PASS",
    )
    rec, assessment = RecordService.ingest_record(rec_input, db_session)

    # Attempt direct SQL UPDATE on records table
    with pytest.raises(Exception) as exc_info:
        db_session.execute(
            text("UPDATE records SET original_verdict = 'FAIL' WHERE record_id = 'REC-DB-TRIGGER-TEST'")
        )
        db_session.commit()
    assert "IMMUTABILITY VIOLATION" in str(exc_info.value)
    db_session.rollback()

    # Attempt direct SQL DELETE on records table
    with pytest.raises(Exception) as exc_info:
        db_session.execute(
            text("DELETE FROM records WHERE record_id = 'REC-DB-TRIGGER-TEST'")
        )
        db_session.commit()
    assert "IMMUTABILITY VIOLATION" in str(exc_info.value)
    db_session.rollback()

    # Attempt direct SQL UPDATE on assessments table
    with pytest.raises(Exception) as exc_info:
        db_session.execute(
            text(f"UPDATE assessments SET status = 'checks_passed' WHERE finding_id = '{assessment.finding_id}'")
        )
        db_session.commit()
    assert "IMMUTABILITY VIOLATION" in str(exc_info.value)
    db_session.rollback()
