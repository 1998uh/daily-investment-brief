from __future__ import annotations

import http.client
import json
import random
from dataclasses import dataclass
from urllib import error, parse, request

from .cancel import interruptible_sleep, raise_if_cancelled
from .config import Settings, normalize_llm_provider


class LLMError(RuntimeError):
    """Raised when an LLM request fails."""


RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
COMPLETE_OPENAI_REASONS = {None, "stop", "tool_calls", "function_call"}
COMPLETE_ANTHROPIC_REASONS = {None, "end_turn", "stop_sequence", "tool_use"}
COMPLETE_GEMINI_REASONS = {None, "STOP"}


@dataclass(frozen=True)
class LLMRequest:
    url: str
    headers: dict[str, str]
    payload: dict


def chat_completion(
    settings: Settings,
    messages: list[dict[str, str]],
    *,
    temperature: float | None = None,
    label: str = "LLM",
) -> str:
    raise_if_cancelled()
    if not settings.has_llm:
        raise LLMError("BRIEF_BASE_URL and BRIEF_MODEL are required")

    effective_provider = normalize_llm_provider(settings.llm_provider)
    request_kwargs = dict(
        base_url=settings.base_url,
        model=settings.model,
        api_key=settings.api_key,
        messages=messages,
        temperature=settings.temperature if temperature is None else temperature,
        max_tokens=settings.llm_max_tokens,
        thinking_type=settings.llm_thinking_type,
    )
    request_data = build_request(provider=effective_provider, **request_kwargs)
    attempts = settings.llm_retries + 1
    last_error: LLMError | None = None
    attempt = 1
    protocol_switched = False
    retry_after_seconds: float | None = None

    while attempt <= attempts:
        raise_if_cancelled()
        if label:
            protocol_label = " (Responses protocol)" if protocol_switched else ""
            print(
                f"[info] {label}: LLM request {attempt}/{attempts}{protocol_label}",
                flush=True,
            )
        try:
            req = request.Request(
                request_data.url,
                data=json.dumps(request_data.payload, ensure_ascii=False).encode("utf-8"),
                method="POST",
                headers=request_data.headers,
            )
            with request.urlopen(req, timeout=settings.llm_timeout_seconds) as response:
                body = response.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError as exc:
                if (
                    effective_provider == "openai"
                    and not protocol_switched
                    and _looks_like_html(body)
                ):
                    effective_provider = "openai-responses"
                    protocol_switched = True
                    request_data = build_request(provider=effective_provider, **request_kwargs)
                    if label:
                        print(
                            f"[warn] {label}: Chat Completions endpoint returned HTML; "
                            "switching to /responses",
                            flush=True,
                        )
                    continue
                excerpt = " ".join(body[:300].split())
                suffix = f"; response starts with: {excerpt!r}" if excerpt else ""
                raise LLMError(f"LLM returned invalid JSON: {exc}{suffix}") from exc
            content = parse_response(effective_provider, parsed)
            if label:
                print(f"[info] {label}: LLM response received", flush=True)
            return content
        except LLMError as exc:
            last_error = exc
            retryable = True
        except error.HTTPError as exc:
            detail = _read_error_body(exc)
            if (
                exc.code == 400
                and effective_provider == "openai"
                and not protocol_switched
                and requires_responses_protocol(detail)
            ):
                effective_provider = "openai-responses"
                protocol_switched = True
                request_data = build_request(provider=effective_provider, **request_kwargs)
                if label:
                    print(
                        f"[warn] {label}: model requires Responses protocol; "
                        "switching to /responses",
                        flush=True,
                    )
                continue
            last_error = LLMError(f"LLM HTTP {exc.code}: {detail[:1000]}")
            retryable = exc.code in RETRYABLE_HTTP_STATUS and not _is_access_forbidden(detail)
            retry_after_seconds = _retry_after_seconds(exc.headers.get("Retry-After"))
        except (error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, OSError) as exc:
            last_error = LLMError(f"LLM request failed: {exc}")
            retryable = True
        except (UnicodeDecodeError, KeyError, IndexError, TypeError) as exc:
            last_error = LLMError(f"Unexpected LLM response shape: {exc}")
            retryable = False

        if not retryable or attempt >= attempts:
            break

        base_delay = settings.llm_retry_delay_seconds * (2 ** (attempt - 1))
        jitter = random.uniform(0, min(base_delay * 0.25, 2.0)) if base_delay else 0
        delay = max(base_delay + jitter, retry_after_seconds or 0)
        retry_after_seconds = None
        if label:
            print(f"[warn] {label}: {last_error}; retrying in {delay:.1f}s", flush=True)
        if delay:
            interruptible_sleep(delay)
        attempt += 1

    raise last_error or LLMError("LLM request failed")


def build_request(
    *,
    provider: str,
    base_url: str,
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
    temperature: float | None,
    max_tokens: int | None,
    thinking_type: str | None = None,
    stream: bool = False,
) -> LLMRequest:
    provider = normalize_llm_provider(provider)
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
    }

    if provider == "openai":
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload: dict = {"model": model, "messages": messages, "stream": stream}
        if temperature is not None:
            payload["temperature"] = temperature
        if thinking_type:
            payload["thinking"] = {"type": thinking_type}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        return LLMRequest(
            url=_endpoint(base_url, "/chat/completions"), headers=headers, payload=payload
        )

    if provider == "openai-responses":
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        instructions, input_messages = _split_system_messages(messages)
        if instructions:
            input_messages = _merge_responses_instructions(instructions, input_messages)
        payload = {"model": model, "input": input_messages, "stream": stream}
        if max_tokens:
            payload["max_output_tokens"] = max_tokens
        return LLMRequest(url=_endpoint(base_url, "/responses"), headers=headers, payload=payload)

    if provider == "anthropic":
        headers["anthropic-version"] = "2023-06-01"
        if api_key:
            headers["x-api-key"] = api_key
        system, provider_messages = _split_system_messages(messages)
        payload = {
            "model": model,
            "messages": provider_messages,
            "max_tokens": max_tokens or 8192,
            "stream": stream,
        }
        if system:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature
        return LLMRequest(url=_endpoint(base_url, "/messages"), headers=headers, payload=payload)

    if provider == "gemini":
        if api_key:
            headers["x-goog-api-key"] = api_key
        system, provider_messages = _split_system_messages(messages)
        contents = [
            {
                "role": "model" if message["role"] == "assistant" else "user",
                "parts": [{"text": message["content"]}],
            }
            for message in provider_messages
        ]
        payload = {"contents": contents, "generationConfig": {}}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if temperature is not None:
            payload["generationConfig"]["temperature"] = temperature
        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens
        action = "streamGenerateContent?alt=sse" if stream else "generateContent"
        model_name = model.removeprefix("models/")
        return LLMRequest(
            url=_endpoint(base_url, f"/models/{parse.quote(model_name, safe='')}:" + action),
            headers=headers,
            payload=payload,
        )

    if provider == "ollama":
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "options": {},
        }
        if temperature is not None:
            payload["options"]["temperature"] = temperature
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        return LLMRequest(url=_endpoint(base_url, "/api/chat"), headers=headers, payload=payload)

    raise LLMError(
        f"Unsupported BRIEF_LLM_PROVIDER={provider!r}; use openai, openai-responses, "
        "anthropic, gemini, or ollama"
    )


def parse_response(provider: str, parsed: dict) -> str:
    provider = normalize_llm_provider(provider)
    if provider == "openai":
        choice = parsed["choices"][0]
        finish_reason = choice.get("finish_reason")
        if finish_reason not in COMPLETE_OPENAI_REASONS:
            raise LLMError(f"LLM returned incomplete response: finish_reason={finish_reason}")
        content = choice["message"]["content"]
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        return content.strip()

    if provider == "openai-responses":
        status = parsed.get("status")
        if status not in {None, "completed"}:
            detail = parsed.get("incomplete_details") or parsed.get("error") or status
            raise LLMError(f"LLM returned incomplete response: {detail}")
        if isinstance(parsed.get("output_text"), str):
            return parsed["output_text"].strip()
        text = "".join(
            part.get("text", "")
            for item in parsed["output"]
            if item.get("type") == "message"
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        ).strip()
        if not text:
            raise LLMError("Unexpected LLM response shape: no output_text content")
        return text

    if provider == "anthropic":
        stop_reason = parsed.get("stop_reason")
        if stop_reason not in COMPLETE_ANTHROPIC_REASONS:
            raise LLMError(f"LLM returned incomplete response: stop_reason={stop_reason}")
        return "".join(
            block.get("text", "")
            for block in parsed["content"]
            if block.get("type") == "text"
        ).strip()

    if provider == "gemini":
        candidate = parsed["candidates"][0]
        finish_reason = candidate.get("finishReason")
        if finish_reason not in COMPLETE_GEMINI_REASONS:
            raise LLMError(f"LLM returned incomplete response: finishReason={finish_reason}")
        return "".join(
            part.get("text", "") for part in candidate["content"]["parts"]
        ).strip()

    if provider == "ollama":
        done_reason = parsed.get("done_reason")
        if parsed.get("done") is False or done_reason not in {None, "stop"}:
            raise LLMError(f"LLM returned incomplete response: done_reason={done_reason}")
        return parsed["message"]["content"].strip()

    raise LLMError(f"Unsupported LLM provider: {provider}")


def _endpoint(base_url: str, suffix: str) -> str:
    base_parts = parse.urlsplit(base_url.rstrip("/"))
    suffix_parts = parse.urlsplit(suffix)
    base_path = base_parts.path.rstrip("/")
    known_endpoints = ("/chat/completions", "/responses", "/messages", "/api/chat")
    if base_path.endswith(suffix_parts.path):
        path = base_path
    else:
        for endpoint in known_endpoints:
            if base_path.endswith(endpoint):
                base_path = base_path[: -len(endpoint)].rstrip("/")
                break
        path = base_path + suffix_parts.path
    query_items = parse.parse_qsl(base_parts.query, keep_blank_values=True)
    query_items.extend(parse.parse_qsl(suffix_parts.query, keep_blank_values=True))
    return parse.urlunsplit(
        (
            base_parts.scheme,
            base_parts.netloc,
            path,
            parse.urlencode(query_items),
            base_parts.fragment,
        )
    )


def _split_system_messages(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    system = "\n\n".join(
        message["content"] for message in messages if message["role"] == "system"
    )
    provider_messages = [message for message in messages if message["role"] != "system"]
    return system, provider_messages


def _merge_responses_instructions(
    instructions: str,
    messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Keep compatibility with relays that only accept user input items."""
    merged = [dict(message) for message in messages]
    for index, message in enumerate(merged):
        if message.get("role") == "user":
            merged[index]["content"] = instructions + "\n\n" + message["content"]
            return merged
    return [{"role": "user", "content": instructions}, *merged]


def _read_error_body(exc: error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except (OSError, http.client.HTTPException):
        return str(exc.reason)


def requires_responses_protocol(detail: str) -> bool:
    lowered = detail.lower()
    return "model_card_api_protocol_mismatch" in lowered or (
        "responses" in lowered and ("protocol" in lowered or "协议" in detail)
    )


def _looks_like_html(body: str) -> bool:
    prefix = body.lstrip()[:100].lower()
    return prefix.startswith("<!doctype html") or prefix.startswith("<html")


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _is_access_forbidden(detail: str) -> bool:
    lowered = detail.lower()
    return "access forbidden" in lowered or "contact administrator" in lowered
