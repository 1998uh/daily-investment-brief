from __future__ import annotations

import json
import time
from urllib import error, request

from .config import Settings


class LLMError(RuntimeError):
    """Raised when an OpenAI-compatible request fails."""


RETRYABLE_HTTP_STATUS = {408, 409, 429, 500, 502, 503, 504}


def chat_completion(
    settings: Settings,
    messages: list[dict[str, str]],
    *,
    temperature: float | None = None,
    label: str = "LLM",
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

    attempts = settings.llm_retries + 1
    last_error: LLMError | None = None
    for attempt in range(1, attempts + 1):
        if label:
            print(f"[info] {label}: LLM request {attempt}/{attempts}", flush=True)
        try:
            with request.urlopen(req, timeout=settings.llm_timeout_seconds) as response:
                body = response.read().decode("utf-8")
            parsed = json.loads(body)
            content = parsed["choices"][0]["message"]["content"].strip()
            if label:
                print(f"[info] {label}: LLM response received", flush=True)
            return content
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = LLMError(f"LLM HTTP {exc.code}: {detail[:1000]}")
            retryable = exc.code in RETRYABLE_HTTP_STATUS
        except error.URLError as exc:
            last_error = LLMError(f"LLM request failed: {exc}")
            retryable = True
        except json.JSONDecodeError as exc:
            last_error = LLMError(f"LLM returned invalid JSON: {exc}")
            retryable = True
        except (KeyError, IndexError, TypeError) as exc:
            last_error = LLMError(f"Unexpected LLM response shape: {exc}")
            retryable = False

        if not retryable or attempt >= attempts:
            break

        delay = settings.llm_retry_delay_seconds * (2 ** (attempt - 1))
        if label:
            print(f"[warn] {label}: {last_error}; retrying in {delay:.1f}s", flush=True)
        if delay:
            time.sleep(delay)

    raise last_error or LLMError("LLM request failed")
