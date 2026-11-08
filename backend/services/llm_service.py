"""
Configurable local LLM client for offline-first inference.
Strictly prohibits external cloud APIs (OpenAI, Gemini, Claude, etc.) and avoids hardcoded IPs.
Provides rich contextual mock responses when local inference engines (Ollama / vLLM / llama.cpp) are not active.
"""

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import List, Optional, Tuple
from urllib.parse import urlparse
import httpx
from backend.config import get_settings
from backend.schemas.llm import LLMGenerateRequest, LLMGenerateResponse, LLMMessage

logger = logging.getLogger("vault.llm")
settings = get_settings()

PROHIBITED_CLOUD_DOMAINS = {
    "api.openai.com",
    "openai.com",
    "generativelanguage.googleapis.com",
    "googleapis.com",
    "api.anthropic.com",
    "anthropic.com",
    "api.groq.com",
    "api.cohere.ai",
    "api.together.xyz",
    "api.deepseek.com",
}


def _verify_offline_endpoint(url: str) -> None:
    """Guards against any accidental or intentional cloud API calls."""
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        for blocked in PROHIBITED_CLOUD_DOMAINS:
            if hostname == blocked or hostname.endswith("." + blocked):
                raise ValueError(
                    f"External cloud domain '{hostname}' is strictly prohibited. "
                    "VAULT is an offline-first private platform. Use a local inference engine (Ollama, vLLM, llama.cpp)."
                )
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        logger.warning(f"Failed to parse LLM endpoint URL '{url}': {exc}")


def _estimate_tokens(text: str) -> int:
    """Simple heuristic offline token estimator (~4 chars per token)."""
    return max(1, len(text.strip()) // 4)


def _generate_mock_completion(prompt_text: str, model_name: str) -> str:
    """Generates informative contextual offline mock responses aligned with VAULT kits."""
    lower_prompt = prompt_text.lower()

    if "curatorkit" in lower_prompt or "synthetic" in lower_prompt or "dataset" in lower_prompt:
        return (
            f"[VAULT Offline Mock - {model_name}]\n"
            "CuratorKIT Synthetic Sample Generated:\n"
            "Question: What are the primary quality gates in CuratorKIT?\n"
            "Answer: CuratorKIT implements grounded hallucination gates, reward and diversity gates, "
            "adaptive recovery probes, and secrets/PII filtering with full provenance manifests."
        )
    elif "safetune" in lower_prompt or "safety" in lower_prompt or "steer" in lower_prompt:
        return (
            f"[VAULT Offline Mock - {model_name}]\n"
            "SafeTune Diagnostic Steer Analysis:\n"
            "Refusal vector extracted. Model compliance verified with zero external data leakage."
        )
    elif "auditkit" in lower_prompt or "eval" in lower_prompt or "benchmark" in lower_prompt:
        return (
            f"[VAULT Offline Mock - {model_name}]\n"
            "AuditKIT Evaluation Metric Report:\n"
            "Evaluation complete. Run SHA-256 fingerprint verified. Pass rate: 100%."
        )
    else:
        return (
            f"[VAULT Offline Mock - {model_name}]\n"
            f"Response to input query: '{prompt_text.strip()[:80]}...'\n"
            "Local inference completed offline. No data departed local perimeter."
        )


class LocalLLMClient:
    """Configurable client communicating exclusively with local inference backends."""

    def __init__(self, endpoint: Optional[str] = None, mode: Optional[str] = None):
        self.endpoint = endpoint or settings.llm_endpoint
        self.mode = mode or settings.llm_mode
        self.timeout = settings.llm_timeout_seconds
        _verify_offline_endpoint(self.endpoint)

    def _extract_prompt(self, request: LLMGenerateRequest) -> str:
        """Extracts text prompt from direct prompt or chat messages."""
        if request.prompt:
            return request.prompt

        if request.messages:
            lines = []
            if request.system_prompt:
                lines.append(f"System: {request.system_prompt}")
            for m in request.messages:
                lines.append(f"{m.role.capitalize()}: {m.content}")
            return "\n".join(lines)

        return "VAULT offline status check"

    def is_available(self) -> bool:
        """Pings local endpoint to check if an offline daemon is actively running."""
        if self.mode == "mock":
            return True
        try:
            with httpx.Client(timeout=1.0) as c:
                res = c.get(self.endpoint)
                return res.status_code < 500
        except Exception:
            return False

    def generate_sync(self, request: LLMGenerateRequest) -> LLMGenerateResponse:
        """Synchronous generation execution wrapper."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(self.generate(request))).result()
        return asyncio.run(self.generate(request))

    async def generate(self, request: LLMGenerateRequest) -> LLMGenerateResponse:
        """
        Executes generation using the configured mode.
        If local server is unavailable, automatically falls back to mock response.
        """
        start_time = time.perf_counter()
        prompt_text = self._extract_prompt(request)
        model_name = request.model or settings.llm_model
        prompt_tokens = _estimate_tokens(prompt_text)

        _verify_offline_endpoint(self.endpoint)

        if self.mode == "mock":
            content = _generate_mock_completion(prompt_text, model_name)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            completion_tokens = _estimate_tokens(content)

            return LLMGenerateResponse(
                content=content,
                model=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                mode="mock",
                finish_reason="stop",
                latency_ms=latency_ms,
                created_at=datetime.now(timezone.utc),
            )

        elif self.mode == "ollama":
            url = f"{self.endpoint.rstrip('/')}/api/generate"
            payload = {
                "model": model_name,
                "prompt": prompt_text,
                "stream": False,
                "options": {
                    "temperature": request.temperature,
                    "num_predict": request.max_tokens,
                },
            }
            if request.system_prompt:
                payload["system"] = request.system_prompt

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    content = data.get("response", "")
                    prompt_tokens = data.get("prompt_eval_count", prompt_tokens)
                    completion_tokens = data.get("eval_count", _estimate_tokens(content))
                    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

                    return LLMGenerateResponse(
                        content=content,
                        model=model_name,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=prompt_tokens + completion_tokens,
                        mode="ollama",
                        finish_reason="stop",
                        latency_ms=latency_ms,
                        created_at=datetime.now(timezone.utc),
                    )
            except Exception as exc:
                logger.warning(
                    f"Ollama local inference failed at {url} ({exc}). Falling back to local mock response."
                )
                content = (
                    f"[Offline Fallback - Ollama connection at {self.endpoint} unavailable]\n"
                    + _generate_mock_completion(prompt_text, model_name)
                )
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                completion_tokens = _estimate_tokens(content)

                return LLMGenerateResponse(
                    content=content,
                    model=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    mode="mock (fallback: local server unreachable)",
                    finish_reason="stop",
                    latency_ms=latency_ms,
                    created_at=datetime.now(timezone.utc),
                )

        elif self.mode == "local_api":
            # OpenAI-compatible API endpoint (vLLM / llama.cpp) running on localhost
            url = f"{self.endpoint.rstrip('/')}/v1/chat/completions"
            messages = []
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            if request.messages:
                messages.extend([m.model_dump() for m in request.messages])
            else:
                messages.append({"role": "user", "content": prompt_text})

            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    choices = data.get("choices", [])
                    content = choices[0]["message"]["content"] if choices else ""
                    usage = data.get("usage", {})
                    p_tokens = usage.get("prompt_tokens", prompt_tokens)
                    c_tokens = usage.get("completion_tokens", _estimate_tokens(content))
                    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

                    return LLMGenerateResponse(
                        content=content,
                        model=model_name,
                        prompt_tokens=p_tokens,
                        completion_tokens=c_tokens,
                        total_tokens=p_tokens + c_tokens,
                        mode="local_api",
                        finish_reason=choices[0].get("finish_reason", "stop") if choices else "stop",
                        latency_ms=latency_ms,
                        created_at=datetime.now(timezone.utc),
                    )
            except Exception as exc:
                logger.warning(
                    f"Local API inference failed at {url} ({exc}). Falling back to local mock response."
                )
                content = (
                    f"[Offline Fallback - Local API connection at {self.endpoint} unavailable]\n"
                    + _generate_mock_completion(prompt_text, model_name)
                )
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                completion_tokens = _estimate_tokens(content)

                return LLMGenerateResponse(
                    content=content,
                    model=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    mode="mock (fallback: local server unreachable)",
                    finish_reason="stop",
                    latency_ms=latency_ms,
                    created_at=datetime.now(timezone.utc),
                )

        else:
            raise ValueError(f"Unsupported LLM mode '{self.mode}'. Use 'mock', 'ollama', or 'local_api'.")
