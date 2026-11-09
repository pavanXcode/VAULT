"""
Unit and integration tests for Demo Role-Based Authentication,
Data Scoping, and Cross-Role Retrieval Prevention.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.models.record import ScientificRecord
from backend.services.auth_service import (
    DEMO_USERS,
    UserSession,
    check_record_scope,
    get_current_user,
)
from backend.services.record_service import RecordService
from backend.schemas.record import ScientificRecordInput


def test_auth_token_resolution():
    """Valid demo tokens resolve to the expected user session and roles."""
    researcher = DEMO_USERS["vault-researcher-token-2026"]
    assert researcher.role == "researcher"
    assert "REC-" in researcher.authorized_scopes

    admin = DEMO_USERS["vault-admin-token-2026"]
    assert admin.role == "admin"
    assert "*" in admin.authorized_scopes


def test_auth_invalid_token_rejected(client: TestClient):
    """An invalid API key token returns 401 Unauthorized."""
    res = client.post(
        "/api/assistant/ask",
        headers={"X-VAULT-API-Key": "invalid-hacker-token"},
        json={"query": "test query"},
    )
    assert res.status_code == 401
    assert "Invalid or unrecognized" in res.json()["detail"]


def test_record_scope_enforcement():
    """Verify backend scope filtering prevents unauthorized record access."""
    researcher_session = UserSession(
        username="Dr. Pawan Kumar",
        role="researcher",
        authorized_scopes=["REC-", "EXP-"],
    )
    admin_session = UserSession(
        username="Governance Officer",
        role="admin",
        authorized_scopes=["*"],
    )

    # Allowed for researcher
    assert check_record_scope("REC-LAB-001", researcher_session) is True
    assert check_record_scope("EXP-BIO-002", researcher_session) is True

    # Blocked for researcher
    assert check_record_scope("SECRET-PROPRIETARY-999", researcher_session) is False

    # Allowed for admin
    assert check_record_scope("SECRET-PROPRIETARY-999", admin_session) is True


@pytest.mark.anyio
async def test_cross_role_record_retrieval_blocked_in_assistant(db_session: Session):
    """Backend authorization must filter out restricted records from evidence context."""
    from backend.services.inference_service import InferenceService

    # 1. Ingest permitted and restricted records
    rec_permitted = ScientificRecordInput(
        record_id="REC-AUTHORIZED-001",
        method_id="MTH-STD-01",
        mass_mg=10.0,
        volume_l=1.0,
        reported_mg_per_l=10.0,
        threshold_mg_per_l=10.0,
        threshold_measurand="total_concentration",
        original_verdict="PASS",
    )
    rec_restricted = ScientificRecordInput(
        record_id="SECRET-CLASSIFIED-002",
        method_id="MTH-STD-01",
        mass_mg=50.0,
        volume_l=1.0,
        reported_mg_per_l=50.0,
        threshold_mg_per_l=10.0,
        threshold_measurand="total_concentration",
        original_verdict="FAIL",
    )
    RecordService.ingest_record(rec_permitted, db_session)
    RecordService.ingest_record(rec_restricted, db_session)

    service = InferenceService()

    # Researcher user session
    researcher = UserSession(
        username="Dr. Pawan Kumar",
        role="researcher",
        authorized_scopes=["REC-"],
    )

    evidence = service.retrieve_evidence(
        db=db_session,
        query="laboratory record tests",
        user=researcher,
    )

    source_ids = [e["source_id"] for e in evidence]
    assert "SECRET-CLASSIFIED-002" not in source_ids
    assert "REC-AUTHORIZED-001" in source_ids
