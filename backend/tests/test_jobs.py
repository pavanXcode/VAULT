"""
Unit and integration tests for Job management, execution service, and API endpoints using mock runners.
"""

from datetime import datetime, timezone
from pathlib import Path
import threading
import time
from typing import Any, Dict, Optional
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.integrations.base_runner import BaseToolRunner, ToolRunResult
from backend.integrations.tool_registry import get_tool_registry
from backend.models.job import Job
from backend.services.tool_execution_service import ToolExecutionService


# Mock runners for reliable, isolated lifecycle testing
class MockSuccessRunner(BaseToolRunner):
    @property
    def tool_name(self) -> str:
        return "mock_success"

    def validate_inputs(self, parameters: Dict[str, Any], input_reference: Optional[str] = None) -> None:
        if parameters.get("invalid_param"):
            raise ValueError("Invalid parameter detected")

    def execute(
        self,
        job_id: str,
        parameters: Dict[str, Any],
        input_reference: Optional[str],
        output_dir: Path,
        cancel_event: Optional[threading.Event] = None,
    ) -> ToolRunResult:
        out_file = output_dir / "out.txt"
        out_file.write_text("success data", encoding="utf-8")
        return ToolRunResult(
            tool_name=self.tool_name,
            success=True,
            output_reference=str(out_file),
            summary={"processed": 42},
            metrics={"accuracy": 0.98},
            errors=[],
        )


class MockFailRunner(BaseToolRunner):
    @property
    def tool_name(self) -> str:
        return "mock_fail"

    def validate_inputs(self, parameters: Dict[str, Any], input_reference: Optional[str] = None) -> None:
        pass

    def execute(
        self,
        job_id: str,
        parameters: Dict[str, Any],
        input_reference: Optional[str],
        output_dir: Path,
        cancel_event: Optional[threading.Event] = None,
    ) -> ToolRunResult:
        return ToolRunResult(
            tool_name=self.tool_name,
            success=False,
            output_reference=None,
            summary={},
            metrics={},
            errors=["Mock execution deliberate failure"],
        )


class MockSlowRunner(BaseToolRunner):
    @property
    def tool_name(self) -> str:
        return "mock_slow"

    def validate_inputs(self, parameters: Dict[str, Any], input_reference: Optional[str] = None) -> None:
        pass

    def execute(
        self,
        job_id: str,
        parameters: Dict[str, Any],
        input_reference: Optional[str],
        output_dir: Path,
        cancel_event: Optional[threading.Event] = None,
    ) -> ToolRunResult:
        for _ in range(50):
            if self.is_cancelled_or_terminated(output_dir, cancel_event):
                return ToolRunResult(
                    tool_name=self.tool_name,
                    success=False,
                    errors=["Cancelled cooperatively"],
                )
            time.sleep(0.1)

        # Output artifact that must not be created if cancelled/timed out
        out_file = output_dir / "slow_final_result.json"
        out_file.write_text('{"done": true}', encoding="utf-8")
        return ToolRunResult(tool_name=self.tool_name, success=True, output_reference=str(out_file))


@pytest.fixture(autouse=True)
def setup_mock_runners():
    registry = get_tool_registry()
    registry.register("mock_success", MockSuccessRunner())
    registry.register("mock_fail", MockFailRunner())
    registry.register("mock_slow", MockSlowRunner())
    yield


def test_create_job_success(client: TestClient):
    """Submitting a valid job returns 201 Created and immediate job_id."""
    payload = {
        "tool_name": "mock_success",
        "parameters": {"batch_size": 16},
        "input_reference": "sample_dataset.csv",
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["job_id"].startswith("job_")
    assert data["tool_name"] == "mock_success"
    assert data["status"] in ("pending", "running", "completed")
    assert data["input_parameters"] == {"batch_size": 16}


def test_create_job_invalid_tool_name(client: TestClient):
    """Submitting an unregistered tool name returns 422 Unprocessable Content."""
    payload = {
        "tool_name": "unknown_tool_xyz",
        "parameters": {},
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 422
    assert "Unsupported tool" in resp.json()["detail"]


def test_create_job_invalid_parameters(client: TestClient):
    """Input validation errors return 400 Bad Request."""
    payload = {
        "tool_name": "mock_success",
        "parameters": {"invalid_param": True},
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 400
    assert "Invalid parameter detected" in resp.json()["detail"]


def test_job_completion_and_result_retrieval(client: TestClient, db_session: Session):
    """Job executes in background, transitions to completed, and returns standardized result."""
    payload = {
        "tool_name": "mock_success",
        "parameters": {"count": 10},
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    # Poll status until completed (mock runner completes in < 0.2s)
    completed = False
    for _ in range(30):
        time.sleep(0.1)
        status_resp = client.get(f"/api/jobs/{job_id}")
        assert status_resp.status_code == 200
        if status_resp.json()["status"] == "completed":
            completed = True
            break

    assert completed, "Mock job did not complete in expected time."

    # Retrieve result contract
    res_resp = client.get(f"/api/jobs/{job_id}/result")
    assert res_resp.status_code == 200
    res_data = res_resp.json()

    assert res_data["job_id"] == job_id
    assert res_data["tool_name"] == "mock_success"
    assert res_data["status"] == "completed"
    assert res_data["success"] is True
    assert res_data["output_reference"] is not None
    assert res_data["summary"]["processed"] == 42
    assert res_data["metrics"]["accuracy"] == 0.98
    assert res_data["errors"] == []


def test_job_failure(client: TestClient):
    """Failing runners record failed status and captured error messages."""
    payload = {"tool_name": "mock_fail"}
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    failed = False
    for _ in range(30):
        time.sleep(0.1)
        status_resp = client.get(f"/api/jobs/{job_id}")
        if status_resp.json()["status"] == "failed":
            failed = True
            break

    assert failed, "Mock failure job did not reach failed state."
    result_resp = client.get(f"/api/jobs/{job_id}/result")
    assert result_resp.status_code == 200
    res_data = result_resp.json()
    assert res_data["success"] is False
    assert len(res_data["errors"]) >= 1
    assert "Mock execution deliberate failure" in res_data["errors"][0]


def test_job_timeout(client: TestClient):
    """Job exceeding specified timeout_seconds is terminated, marked failed, and prevented from modifying artifacts."""
    payload = {
        "tool_name": "mock_slow",
        "timeout_seconds": 1.0,
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    timed_out = False
    for _ in range(40):
        time.sleep(0.1)
        status_resp = client.get(f"/api/jobs/{job_id}")
        if status_resp.json()["status"] == "failed":
            timed_out = True
            break

    assert timed_out, "Job did not fail on timeout."
    status_data = client.get(f"/api/jobs/{job_id}").json()
    assert "timed out" in status_data["error_message"].lower()
    assert "running python threads cannot be forcefully terminated" in status_data["error_message"].lower()

    # Verify sentinel was written and final artifact was blocked
    job_dir = ToolExecutionService.get_job_output_dir(job_id)
    assert (job_dir / ".execution_terminated").exists()
    assert not (job_dir / "slow_final_result.json").exists()


def test_cancel_job(client: TestClient):
    """Pending or running job can be cancelled via API, placing sentinel and halting artifact generation."""
    payload = {
        "tool_name": "mock_slow",
        "timeout_seconds": 10.0,
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    # Cancel immediately
    cancel_resp = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Subsequent check
    status_resp = client.get(f"/api/jobs/{job_id}")
    assert status_resp.json()["status"] == "cancelled"

    # Wait briefly for worker thread to complete cleanup
    for _ in range(20):
        if job_id not in ToolExecutionService._active_cancel_events:
            break
        time.sleep(0.05)

    # Verify termination sentinel exists and output artifact was blocked
    job_dir = ToolExecutionService.get_job_output_dir(job_id)
    assert (job_dir / ".execution_terminated").exists()
    assert not (job_dir / "slow_final_result.json").exists()


def test_application_restart_recovery(db_session: Session):
    """Interrupted running jobs from prior session are identified and marked as interrupted."""
    orphaned_job = Job(
        job_id="job_orphaned_123",
        tool_name="mock_success",
        status="running",
        input_parameters="{}",
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(orphaned_job)
    db_session.commit()

    recovered_count = ToolExecutionService.recover_interrupted_jobs(db_session)
    assert recovered_count >= 1

    queried = db_session.query(Job).filter(Job.job_id == "job_orphaned_123").first()
    assert queried.status == "interrupted"
    assert "application shutdown" in queried.error_message


def test_list_jobs_with_filtering(client: TestClient):
    """GET /api/jobs supports filtering by tool_name and status."""
    client.post("/api/jobs", json={"tool_name": "mock_success", "parameters": {}})
    client.post("/api/jobs", json={"tool_name": "mock_fail", "parameters": {}})

    resp = client.get("/api/jobs?tool_name=mock_success")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    assert all(i["tool_name"] == "mock_success" for i in items)
