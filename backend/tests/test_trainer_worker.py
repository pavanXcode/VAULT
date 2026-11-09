"""
Unit and integration tests for Trainer Worker Adapter (Rohit GPU/LoRA integration),
bounded job retries, stage timing, and job event timelines.
"""

from pathlib import Path
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.models.job import Job
from backend.integrations.trainer_worker import TrainerWorkerRunner
from backend.services.tool_execution_service import ToolExecutionService


def test_trainer_worker_input_validation():
    """Verify input validation for training adapter: requires dataset, validates models."""
    runner = TrainerWorkerRunner()

    # Missing dataset fails
    with pytest.raises(ValueError) as exc:
        runner.validate_inputs({})
    assert "requires a dataset" in str(exc.value)

    # Invalid model target fails
    with pytest.raises(ValueError) as exc:
        runner.validate_inputs({"dataset": "data.jsonl", "model": "invalid-gpt-99"})
    assert "Unknown model target" in str(exc.value)

    # Valid model targets pass
    runner.validate_inputs({"dataset": "data.jsonl", "model": "tiny-aya-global"})
    runner.validate_inputs({"dataset": "data.jsonl", "model": "tiny-aya-lora-m1"})
    runner.validate_inputs({"dataset": "data.jsonl", "model": "tiny-aya-safetune-m3"})


def test_trainer_worker_truthful_mock_fallback(tmp_path: Path):
    """
    Playbook Invariant: When model training weights are still being built by Rohit,
    the worker must report honest 'not_tested' status and marked 'is_mock=True'.
    It must NEVER fabricate fake accuracy numbers or claim trained success.
    """
    runner = TrainerWorkerRunner()
    result = runner.execute(
        job_id="job_test_trainer_001",
        parameters={"dataset": "synth_train.jsonl", "model": "tiny-aya-lora-m1"},
        input_reference=None,
        output_dir=tmp_path,
    )

    assert result.success is True
    assert result.status == "not_tested"
    assert result.is_mock is True
    assert result.worker_id == "pawan-mock-adapter"
    assert "not_tested" in result.summary.get("status", "")
    assert "[MOCK]" in result.summary.get("notice", "")
    assert (tmp_path / "model_run.json").exists()


def test_api_submit_training_job_and_retrieve_result(client: TestClient, db_session: Session):
    """Submit a real train_adapter job through the API and verify standardized contracts."""
    payload = {
        "tool_name": "train_adapter",
        "stage": "train",
        "parameters": {
            "model": "tiny-aya-global",
            "dataset": "data/synthetic/records.jsonl",
            "epochs": 3,
            "learning_rate": 2e-4,
        },
        "input_artifact_ids": ["ds-manifest-sha256-test"],
        "max_retries": 3,
    }

    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 201
    job_data = response.json()

    job_id = job_data["job_id"]
    assert job_data["stage"] == "train"
    assert job_data["tool_name"] == "train_adapter"
    assert job_data["config_hash"] is not None

    # Wait briefly for thread execution
    time.sleep(0.4)

    # Fetch result
    res_resp = client.get(f"/api/jobs/{job_id}/result")
    assert res_resp.status_code == 200
    res_data = res_resp.json()

    assert res_data["status"] == "not_tested"
    assert res_data["is_mock"] is True
    assert res_data["stage"] == "train"
    assert res_data["config_hash"] is not None


def test_bounded_retry_mechanism(client: TestClient, db_session: Session):
    """
    Verify bounded retries:
    1. Retrying failed/interrupted job increments retry_count
    2. Retries cannot exceed max_retries (max 3)
    3. Running jobs cannot be retried
    """
    # Create and manually fail a job
    job = Job(
        job_id="job_retry_test_01",
        tool_name="train_adapter",
        stage="train",
        status="failed",
        error_message="Simulated GPU driver crash",
        input_parameters='{"model": "tiny-aya-global", "dataset": "test.jsonl"}',
        retry_count=0,
        max_retries=2,  # Bounded to 2
    )
    db_session.add(job)
    db_session.commit()

    # Retry 1: succeeds
    resp1 = client.post("/api/jobs/job_retry_test_01/retry")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["retry_count"] == 1
    assert data1["status"] in ("queued", "running", "not_tested", "completed")

    time.sleep(0.2)
    # Fail again
    db_session.query(Job).filter_by(job_id="job_retry_test_01").update({"status": "failed"})
    db_session.commit()

    # Retry 2: succeeds (retry_count becomes 2)
    resp2 = client.post("/api/jobs/job_retry_test_01/retry")
    assert resp2.status_code == 200
    assert resp2.json()["retry_count"] == 2

    time.sleep(0.2)
    # Fail again
    db_session.query(Job).filter_by(job_id="job_retry_test_01").update({"status": "failed"})
    db_session.commit()

    # Retry 3: exceeds max_retries=2 -> must fail with 400 Bad Request
    resp3 = client.post("/api/jobs/job_retry_test_01/retry")
    assert resp3.status_code == 400
    assert "Bounded retry limit reached" in resp3.json()["detail"]


def test_job_events_timeline(client: TestClient, db_session: Session):
    """Verify that chronological stage events are retrievable for a job."""
    payload = {
        "tool_name": "train_adapter",
        "stage": "train",
        "parameters": {"model": "tiny-aya-global", "dataset": "test.jsonl"},
    }
    create_resp = client.post("/api/jobs", json=payload)
    job_id = create_resp.json()["job_id"]

    time.sleep(0.3)

    events_resp = client.get(f"/api/jobs/{job_id}/events")
    assert events_resp.status_code == 200
    events = events_resp.json()

    assert len(events) >= 2
    stages_seen = [e["stage"] for e in events]
    assert "train" in stages_seen
