from __future__ import annotations

import json
from urllib import error, request

from .config import Settings


class LLMError(RuntimeError):
    """Raised when an OpenAI-compatible request fails."""


def chat_completion(
    settings: Settings,
    messages: list[dict[str, str]],
    *,
    temperature: float | None = None,
) -> str:
    if not settings.has_llm:
        raise LLMError("BRIEF_BASE_URL, BRIEF_MODEL, and BRIEF_API_KEY are required")

    payload = {
        "model": settings.model,
        "messages": messages,
        "temperature": settings.temperature if temperature is None else temperature,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        f"{settings.base_url}/chat/completions",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with request.urlopen(req, timeout=120) as response:
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMError(f"LLM HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc

    parsed = json.loads(body)
    try:
        return parsed["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected LLM response: {body[:1000]}") from exc
