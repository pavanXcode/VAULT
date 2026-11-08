"""
Unit and integration tests for GET /api/system/info.
"""

from fastapi.testclient import TestClient


def test_system_info_endpoint(client: TestClient):
    """Verify that GET /api/system/info returns full host specs, offline status, and tool states."""
    response = client.get("/api/system/info")
    assert response.status_code == 200

    data = response.json()
    # Check OS & hardware fields
    assert "platform" in data
    assert "os_name" in data
    assert "cpu_count" in data
    assert data["cpu_count"] >= 1
    assert "memory_total_gb" in data
    assert data["memory_total_gb"] > 0
    assert "disk_total_gb" in data

    # Check offline status
    assert data["offline_mode"] is True

    # Check VAULT tool suite detection
    assert "vault_tools" in data
    vault_tools = data["vault_tools"]
    for tool_name in ("CuratorKIT", "SafeTune", "AuditKIT"):
        assert tool_name in vault_tools
        assert "installed" in vault_tools[tool_name]
        assert "status" in vault_tools[tool_name]

    # Check local LLM config preview
    assert "llm_config" in data
    assert data["llm_config"]["offline_enforced"] is True
    assert "mode" in data["llm_config"]
    assert "endpoint" in data["llm_config"]
