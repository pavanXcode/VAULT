"""
Unit and integration tests for experiment tracking endpoints.
"""

from fastapi.testclient import TestClient


def test_list_experiments_initially_empty(client: TestClient):
    """Ensure experiments listing works cleanly when empty."""
    response = client.get("/api/experiments")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_create_curatorkit_experiment(client: TestClient):
    """Test creating an experiment for CuratorKIT synthetic data generation."""
    payload = {
        "name": "Synthetic Curation Batch 1",
        "description": "Grounded QA generation from ingested technical documentation",
        "tool_type": "curatorkit",
        "parameters": {
            "task": "qa_generation",
            "hallucination_gate": True,
            "min_grounding_score": 0.85,
        },
    }
    response = client.post("/api/experiments", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["id"] is not None
    assert data["name"] == payload["name"]
    assert data["tool_type"] == "curatorkit"
    assert data["status"] == "created"
    assert data["parameters"]["task"] == "qa_generation"


def test_create_safetune_and_auditkit_experiments(client: TestClient):
    """Test creating experiments for SafeTune and AuditKIT."""
    # SafeTune run
    st_payload = {
        "name": "Refusal Steer Extraction",
        "tool_type": "safetune",
        "parameters": {"method": "steer", "contrast_pairs": 50},
    }
    st_resp = client.post("/api/experiments", json=st_payload)
    assert st_resp.status_code == 201
    assert st_resp.json()["tool_type"] == "safetune"

    # AuditKIT run
    ak_payload = {
        "name": "Local Model Benchmark Run",
        "tool_type": "auditkit",
        "parameters": {"metrics": ["hallucination", "toxicity", "latency"]},
    }
    ak_resp = client.post("/api/experiments", json=ak_payload)
    assert ak_resp.status_code == 201
    assert ak_resp.json()["tool_type"] == "auditkit"


def test_create_experiment_invalid_tool_type(client: TestClient):
    """Attempting to use an unsupported tool type fails validation with 422."""
    payload = {
        "name": "Invalid Tool Run",
        "tool_type": "unsupported_cloud_tool",
    }
    response = client.post("/api/experiments", json=payload)
    assert response.status_code == 422


def test_filter_experiments_by_tool_type(client: TestClient):
    """Listing experiments supports filtering by tool_type."""
    client.post(
        "/api/experiments",
        json={"name": "Curator Exp", "tool_type": "curatorkit"},
    )
    client.post(
        "/api/experiments",
        json={"name": "Audit Exp", "tool_type": "auditkit"},
    )

    resp_curator = client.get("/api/experiments?tool_type=curatorkit")
    assert resp_curator.status_code == 200
    for exp in resp_curator.json()["items"]:
        assert exp["tool_type"] == "curatorkit"

    resp_audit = client.get("/api/experiments?tool_type=auditkit")
    assert resp_audit.status_code == 200
    for exp in resp_audit.json()["items"]:
        assert exp["tool_type"] == "auditkit"
