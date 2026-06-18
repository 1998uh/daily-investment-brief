"""Async streaming LLM client for OpenAI-compatible APIs (e.g. DeepSeek)."""
from __future__ import annotations

import json
from typing import AsyncGenerator

import httpx

from agent.config import AgentSettings


class LLMStreamError(RuntimeError):
    """Raised when a streaming LLM request fails."""


async def stream_chat_completion(
    settings: AgentSettings,
    messages: list[dict],
    *,
    temperature: float | None = None,
    timeout: float = 120.0,
) -> AsyncGenerator[str, None]:
    """Stream tokens from an OpenAI-compatible chat/completions endpoint.

    Yields content deltas as strings. Raises LLMStreamError on failure.
    """
    if not settings.llm_base_url or not settings.llm_model or not settings.llm_api_key:
        raise LLMStreamError(
            "LLM 未配置：需要 BRIEF_BASE_URL / BRIEF_MODEL / BRIEF_API_KEY"
        )

    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    payload: dict = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": True,
    }
    if temperature is not None:
        payload["temperature"] = temperature

    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=10.0)
    ) as client:
        try:
            async with client.stream(
                "POST", url, json=payload, headers=headers
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise LLMStreamError(
                        f"LLM HTTP {response.status_code}: "
                        f"{body.decode('utf-8', errors='replace')[:500]}"
                    )

                buffer = ""
                async for raw_bytes in response.aiter_bytes():
                    buffer += raw_bytes.decode("utf-8", errors="replace")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            return
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        choices = data.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
        except httpx.TimeoutException as exc:
            raise LLMStreamError(f"LLM 请求超时: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMStreamError(f"LLM 请求失败: {exc}") from exc
