"""
Unit and integration tests for local LLM inference client and generate endpoint.
"""

import asyncio
import pytest
from fastapi.testclient import TestClient
from backend.schemas.llm import LLMGenerateRequest
from backend.services.llm_service import LocalLLMClient, _verify_offline_endpoint


def test_llm_generate_prompt_mock_mode(client: TestClient):
    """Test LLM generation using prompt in mock mode."""
    payload = {
        "prompt": "Explain how CuratorKIT generates synthetic datasets.",
        "model": "llama3:8b",
        "temperature": 0.5,
    }
    response = client.post("/api/llm/generate", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "CuratorKIT" in data["content"] or "VAULT Offline Mock" in data["content"]
    assert data["model"] == "llama3:8b"
    assert data["mode"] == "mock"
    assert data["prompt_tokens"] > 0
    assert data["completion_tokens"] > 0
    assert data["total_tokens"] == data["prompt_tokens"] + data["completion_tokens"]
    assert "latency_ms" in data


def test_llm_generate_messages_mock_mode(client: TestClient):
    """Test LLM generation using chat messages list."""
    payload = {
        "messages": [
            {"role": "system", "content": "You are an assistant for SafeTune."},
            {"role": "user", "content": "How do contrast pairs extract refusal steer directions?"},
        ],
        "model": "mistral:7b",
    }
    response = client.post("/api/llm/generate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "mock"
    assert data["model"] == "mistral:7b"
    assert "SafeTune" in data["content"] or "VAULT Offline Mock" in data["content"]


def test_llm_generate_missing_input_fails(client: TestClient):
    """Empty payload without prompt or messages returns 400 Bad Request."""
    response = client.post("/api/llm/generate", json={})
    assert response.status_code == 400
    assert "Either 'prompt' or 'messages' must be provided" in response.json()["detail"]


def test_strictly_prohibits_external_cloud_apis():
    """Verify that external cloud APIs (OpenAI, Gemini, Anthropic) are strictly rejected."""
    prohibited_urls = [
        "https://api.openai.com/v1",
        "https://generativelanguage.googleapis.com/v1beta",
        "https://api.anthropic.com/v1",
        "https://api.groq.com/openai/v1",
    ]
    for url in prohibited_urls:
        with pytest.raises(ValueError) as excinfo:
            _verify_offline_endpoint(url)
        assert "strictly prohibited" in str(excinfo.value).lower()


def test_fallback_when_local_server_unavailable():
    """Verify that when a local inference service is unreachable, client falls back cleanly to mock."""
    async def _invoke():
        # Point to an unallocated local port
        client = LocalLLMClient(endpoint="http://127.0.0.1:59981", mode="ollama")
        req = LLMGenerateRequest(prompt="Status check", model="llama3:8b")
        return await client.generate(req)

    resp = asyncio.run(_invoke())
    assert "fallback" in resp.mode.lower()
    assert resp.content is not None
    assert resp.prompt_tokens > 0
