"""Async streaming client for the LLM providers supported by the pipeline."""
from __future__ import annotations

import json
from typing import AsyncGenerator

import httpx

from agent.config import AgentSettings
from pipeline.config import normalize_llm_provider
from pipeline.llm import LLMError, build_request, requires_responses_protocol


class LLMStreamError(RuntimeError):
    """Raised when a streaming LLM request fails."""


async def stream_chat_completion(
    settings: AgentSettings,
    messages: list[dict],
    *,
    temperature: float | None = None,
    timeout: float = 120.0,
) -> AsyncGenerator[str, None]:
    """Stream content deltas using the configured provider's native protocol."""
    if not settings.llm_base_url or not settings.llm_model:
        raise LLMStreamError(
            "LLM 未配置：需要 BRIEF_BASE_URL / BRIEF_MODEL"
        )

    effective_provider = normalize_llm_provider(settings.llm_provider)
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        for protocol_attempt in range(2):
            try:
                request_data = build_request(
                    provider=effective_provider,
                    base_url=settings.llm_base_url,
                    model=settings.llm_model,
                    api_key=settings.llm_api_key,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=None,
                    stream=True,
                )
                async with client.stream(
                    "POST",
                    request_data.url,
                    json=request_data.payload,
                    headers=request_data.headers,
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        detail = body.decode("utf-8", errors="replace")
                        if (
                            response.status_code == 400
                            and effective_provider == "openai"
                            and protocol_attempt == 0
                            and requires_responses_protocol(detail)
                        ):
                            effective_provider = "openai-responses"
                            continue
                        raise LLMStreamError(
                            f"LLM HTTP {response.status_code}: {detail[:500]}"
                        )

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        data = _parse_stream_line(effective_provider, line)
                        if data is None:
                            continue
                        if data == "[DONE]":
                            return
                        delta = _extract_stream_delta(effective_provider, data)
                        if delta:
                            yield delta
                    return
            except LLMStreamError:
                raise
            except LLMError as exc:
                raise LLMStreamError(str(exc)) from exc
            except httpx.TimeoutException as exc:
                raise LLMStreamError(f"LLM 请求超时: {exc}") from exc
            except httpx.HTTPError as exc:
                raise LLMStreamError(f"LLM 请求失败: {exc}") from exc


def _parse_stream_line(provider: str, line: str) -> dict | str | None:
    provider = normalize_llm_provider(provider)
    if line.startswith("event:"):
        return None
    if line.startswith("data:"):
        raw = line[5:].strip()
    elif provider == "ollama":
        raw = line
    else:
        return None
    if raw == "[DONE]":
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _extract_stream_delta(provider: str, data: dict) -> str:
    provider = normalize_llm_provider(provider)
    if provider == "openai":
        choices = data.get("choices", [])
        if not choices:
            return ""
        content = choices[0].get("delta", {}).get("content")
        if isinstance(content, list):
            return "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        return content or ""
    if provider == "openai-responses":
        if data.get("type") == "response.output_text.delta":
            return data.get("delta", "")
        return ""
    if provider == "anthropic":
        if data.get("type") != "content_block_delta":
            return ""
        return data.get("delta", {}).get("text", "")
    if provider == "gemini":
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        return "".join(
            part.get("text", "")
            for part in candidates[0].get("content", {}).get("parts", [])
        )
    if provider == "ollama":
        return data.get("message", {}).get("content", "")
    return ""
