"""
Unit and integration tests for Process Recovery, Crash Resilience,
and Database-Level Immutability Invariant Guarantees.
"""

from datetime import datetime, timezone
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.models.job import Job
from backend.models.record import ScientificRecord
from backend.services.tool_execution_service import ToolExecutionService
from backend.services.record_service import RecordService
from backend.schemas.record import ScientificRecordInput


def test_crash_recovery_marks_orphaned_jobs_interrupted(db_session: Session):
    """
    Playbook Invariant: When server restarts after a crash or kill,
    orphaned 'running' or 'pending' jobs MUST be transitioned to 'interrupted',
    never falsely marked 'succeeded' or 'completed'.
    """
    # 1. Simulate an orphaned job left in 'running' state prior to crash
    orphaned_job = Job(
        job_id="job_crashed_sim_001",
        tool_name="train_adapter",
        stage="train",
        status="running",
        worker_id="crashed-worker",
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(orphaned_job)
    db_session.commit()

    # 2. Execute startup recovery routine
    recovered_count = ToolExecutionService.recover_interrupted_jobs(db_session)
    assert recovered_count >= 1

    # 3. Verify job status
    db_session.refresh(orphaned_job)
    assert orphaned_job.status == "interrupted"
    assert "interrupted by application shutdown or server restart" in (orphaned_job.error_message or "")


def test_immutability_triggers_prevent_direct_sql_tampering(db_session: Session):
    """
    Dual-layer guarantee: Database triggers must reject raw SQL UPDATE
    and DELETE statements on records, assessments, and ground truth tables.
    """
    # 1. Ingest a record
    rec_input = ScientificRecordInput(
        record_id="REC-IMMUTABLE-SQL-01",
        method_id="MTH-STD-01",
        mass_mg=10.0,
        volume_l=1.0,
        reported_mg_per_l=10.0,
        threshold_mg_per_l=10.0,
        threshold_measurand="total_concentration",
        original_verdict="PASS",
    )
    RecordService.ingest_record(rec_input, db_session)

    # 2. Attempt raw SQL UPDATE on records table
    with pytest.raises(Exception) as excinfo:
        db_session.execute(
            text("UPDATE records SET original_verdict = 'FAIL' WHERE record_id = 'REC-IMMUTABLE-SQL-01'")
        )
        db_session.commit()
    assert "IMMUTABILITY VIOLATION" in str(excinfo.value) or "abort" in str(excinfo.value).lower()
    db_session.rollback()

    # 3. Attempt raw SQL DELETE on records table
    with pytest.raises(Exception) as excinfo:
        db_session.execute(
            text("DELETE FROM records WHERE record_id = 'REC-IMMUTABLE-SQL-01'")
        )
        db_session.commit()
    assert "IMMUTABILITY VIOLATION" in str(excinfo.value) or "abort" in str(excinfo.value).lower()
    db_session.rollback()


def test_provenance_conflict_rejection_on_altered_record(db_session: Session):
    """
    Attempting to re-ingest an existing record_id with differing measurements
    must be strictly rejected to prevent provenance tampering.
    """
    rec_original = ScientificRecordInput(
        record_id="REC-PROVENANCE-CHECK-01",
        method_id="MTH-STD-01",
        mass_mg=10.0,
        volume_l=1.0,
        reported_mg_per_l=10.0,
        threshold_mg_per_l=10.0,
        threshold_measurand="total_concentration",
        original_verdict="PASS",
    )
    RecordService.ingest_record(rec_original, db_session)

    # Identical record re-submission is idempotent
    rec_same, _ = RecordService.ingest_record(rec_original, db_session)
    assert rec_same.record_id == "REC-PROVENANCE-CHECK-01"

    # Altered record with same ID MUST fail with ValueError
    rec_tampered = ScientificRecordInput(
        record_id="REC-PROVENANCE-CHECK-01",
        method_id="MTH-STD-01",
        mass_mg=99.0,  # Altered!
        volume_l=1.0,
        reported_mg_per_l=99.0,
        threshold_mg_per_l=10.0,
        threshold_measurand="total_concentration",
        original_verdict="FAIL",
    )
    with pytest.raises(ValueError) as excinfo:
        RecordService.ingest_record(rec_tampered, db_session)
    assert "IMMUTABILITY CONFLICT" in str(excinfo.value)
