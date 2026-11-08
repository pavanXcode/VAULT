"""
Unit and integration tests for GET /api/health.
"""

from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient):
    """Verify that GET /api/health returns 200 and accurate health metrics."""
    response = client.get("/api/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "app_name" in data
    assert "version" in data
    assert data["offline_mode"] is True
    assert "database_connected" in data
    assert "timestamp" in data


def test_root_endpoint(client: TestClient):
    """Verify that root endpoint / returns online service status and metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["offline_mode"] is True
    assert data["api_prefix"] == "/api"


def test_ui_dashboard_endpoint(client: TestClient):
    """Verify that the frontend UI is properly served at /ui."""
    response = client.get("/ui")
    assert response.status_code == 200
    assert "VAULT" in response.text
    assert "Research Assistant" in response.text
