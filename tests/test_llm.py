from __future__ import annotations

import json
import http.client
import unittest
from io import BytesIO
from urllib import error
from unittest.mock import patch

from pipeline.config import Settings
import pipeline.llm as llm


def make_settings(**overrides) -> Settings:
    values = dict(
        base_url="https://example.com",
        model="test-model",
        api_key="test-key",
        llm_timeout_seconds=30,
        llm_retries=0,
        llm_retry_delay_seconds=0,
        timezone="Asia/Shanghai",
        window_start="08:00",
        window_end="08:00",
        markets="A股,港股",
        style="strong_narrative_emoji",
        max_chars_per_article=1_000,
        batch_size=2,
        batch_max_chars=15_000,
        llm_batch_concurrency=1,
        temperature=0.2,
        llm_thinking_type=None,
        llm_max_tokens=None,
    )
    values.update(overrides)
    return Settings(**values)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class ChatCompletionTests(unittest.TestCase):
    def test_chat_completion_wraps_timeout_error(self) -> None:
        with patch("pipeline.llm.request.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaisesRegex(llm.LLMError, "timed out"):
                llm.chat_completion(make_settings(), [{"role": "user", "content": "hello"}], label="")

    def test_chat_completion_sends_optional_request_fields(self) -> None:
        captured_request = None

        def fake_urlopen(req, timeout):
            nonlocal captured_request
            captured_request = req
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "ok",
                            }
                        }
                    ]
                }
            )

        settings = make_settings(llm_thinking_type="disabled", llm_max_tokens=3000)
        with patch("pipeline.llm.request.urlopen", side_effect=fake_urlopen):
            result = llm.chat_completion(settings, [{"role": "user", "content": "hello"}], label="")

        self.assertEqual(result, "ok")
        self.assertIsNotNone(captured_request)
        payload = json.loads(captured_request.data.decode("utf-8"))
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["max_tokens"], 3000)

    def test_chat_completion_rejects_truncated_response(self) -> None:
        def fake_urlopen(req, timeout):
            return FakeResponse(
                {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {
                                "content": "partial report",
                            },
                        }
                    ]
                }
            )

        with patch("pipeline.llm.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaisesRegex(llm.LLMError, "finish_reason=length"):
                llm.chat_completion(make_settings(), [{"role": "user", "content": "hello"}], label="")

    def test_chat_completion_retries_truncated_response(self) -> None:
        responses = [
            {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {
                            "content": "partial report",
                        },
                    }
                ]
            },
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "complete report",
                        },
                    }
                ]
            },
        ]

        def fake_urlopen(req, timeout):
            return FakeResponse(responses.pop(0))

        with patch("pipeline.llm.request.urlopen", side_effect=fake_urlopen):
            result = llm.chat_completion(
                make_settings(llm_retries=1),
                [{"role": "user", "content": "hello"}],
                label="",
            )

        self.assertEqual(result, "complete report")
        self.assertEqual(responses, [])

    def test_chat_completion_retries_incomplete_chunked_response(self) -> None:
        responses = [
            http.client.IncompleteRead(b'{"choices": ['),
            FakeResponse(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "recovered"},
                        }
                    ]
                }
            ),
        ]

        with patch("pipeline.llm.request.urlopen", side_effect=responses):
            result = llm.chat_completion(
                make_settings(llm_retries=1),
                [{"role": "user", "content": "hello"}],
                label="",
            )

        self.assertEqual(result, "recovered")

    def test_access_forbidden_502_is_not_retried(self) -> None:
        def fake_urlopen(req, timeout):
            raise error.HTTPError(
                req.full_url,
                502,
                "Bad Gateway",
                {},
                BytesIO(
                    b'{"error":{"message":"Upstream access forbidden, please contact administrator"}}'
                ),
            )

        with patch("pipeline.llm.request.urlopen", side_effect=fake_urlopen) as mocked:
            with self.assertRaisesRegex(llm.LLMError, "access forbidden"):
                llm.chat_completion(
                    make_settings(llm_retries=4),
                    [{"role": "user", "content": "hello"}],
                    label="",
                )

        self.assertEqual(mocked.call_count, 1)

    def test_openai_compatible_relay_accepts_full_endpoint(self) -> None:
        request_data = llm.build_request(
            provider="openai-compatible",
            base_url="https://relay.example/v1/chat/completions",
            model="relay-model",
            api_key="relay-key",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.2,
            max_tokens=None,
        )

        self.assertEqual(request_data.url, "https://relay.example/v1/chat/completions")
        self.assertEqual(request_data.headers["Authorization"], "Bearer relay-key")

    def test_responses_request_replaces_full_chat_completions_endpoint(self) -> None:
        request_data = llm.build_request(
            provider="openai-responses",
            base_url="https://relay.example/v1/chat/completions",
            model="responses-model",
            api_key="relay-key",
            messages=[
                {"role": "system", "content": "system rules"},
                {"role": "user", "content": "hello"},
            ],
            temperature=0.2,
            max_tokens=3000,
        )

        self.assertEqual(request_data.url, "https://relay.example/v1/responses")
        self.assertEqual(
            request_data.payload["input"][0]["content"], "system rules\n\nhello"
        )
        self.assertNotIn("instructions", request_data.payload)
        self.assertEqual(request_data.payload["max_output_tokens"], 3000)
        self.assertNotIn("temperature", request_data.payload)

    def test_responses_response_extracts_output_text(self) -> None:
        content = llm.parse_response(
            "openai-responses",
            {
                "status": "completed",
                "output": [
                    {"type": "reasoning", "summary": []},
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "response text"}],
                    },
                ],
            },
        )

        self.assertEqual(content, "response text")

    def test_openai_relay_auto_switches_to_responses_protocol(self) -> None:
        captured_urls = []

        def fake_urlopen(req, timeout):
            captured_urls.append(req.full_url)
            if len(captured_urls) == 1:
                raise error.HTTPError(
                    req.full_url,
                    400,
                    "Bad Request",
                    {},
                    BytesIO(
                        b'{"error":{"message":"MODEL_CARD_API_PROTOCOL_MISMATCH: '
                        b'model must use responses protocol"}}'
                    ),
                )
            return FakeResponse(
                {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "switched"}],
                        }
                    ],
                }
            )

        with patch("pipeline.llm.request.urlopen", side_effect=fake_urlopen):
            result = llm.chat_completion(
                make_settings(base_url="https://relay.example/v1"),
                [{"role": "user", "content": "hello"}],
                label="",
            )

        self.assertEqual(result, "switched")
        self.assertEqual(
            captured_urls,
            [
                "https://relay.example/v1/chat/completions",
                "https://relay.example/v1/responses",
            ],
        )

    def test_openai_relay_auto_switches_when_chat_endpoint_returns_html(self) -> None:
        responses = [
            b"<!doctype html><html><title>Relay console</title></html>",
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "switched"}],
                    }
                ],
            },
        ]
        captured_urls = []

        def fake_urlopen(req, timeout):
            captured_urls.append(req.full_url)
            response = responses.pop(0)
            if isinstance(response, bytes):
                fake = FakeResponse({})
                fake.read = lambda: response
                return fake
            return FakeResponse(response)

        with patch("pipeline.llm.request.urlopen", side_effect=fake_urlopen):
            result = llm.chat_completion(
                make_settings(base_url="https://relay.example/v1"),
                [{"role": "user", "content": "hello"}],
                label="",
            )

        self.assertEqual(result, "switched")
        self.assertEqual(
            captured_urls,
            [
                "https://relay.example/v1/chat/completions",
                "https://relay.example/v1/responses",
            ],
        )

    def test_anthropic_native_request_and_response(self) -> None:
        request_data = llm.build_request(
            provider="anthropic",
            base_url="https://api.anthropic.com/v1",
            model="claude-test",
            api_key="anthropic-key",
            messages=[
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "hello"},
            ],
            temperature=0.2,
            max_tokens=2000,
        )

        self.assertEqual(request_data.url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(request_data.headers["x-api-key"], "anthropic-key")
        self.assertEqual(request_data.payload["system"], "system prompt")
        self.assertEqual(
            llm.parse_response(
                "anthropic",
                {
                    "stop_reason": "end_turn",
                    "content": [{"type": "text", "text": "Claude response"}],
                },
            ),
            "Claude response",
        )

    def test_gemini_native_request_and_response(self) -> None:
        request_data = llm.build_request(
            provider="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            model="gemini-test",
            api_key="gemini-key",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.2,
            max_tokens=2000,
        )

        self.assertEqual(
            request_data.url,
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent",
        )
        self.assertEqual(request_data.headers["x-goog-api-key"], "gemini-key")
        self.assertEqual(
            llm.parse_response(
                "gemini",
                {
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": "Gemini response"}]},
                        }
                    ]
                },
            ),
            "Gemini response",
        )

    def test_ollama_does_not_require_api_key(self) -> None:
        settings = make_settings(
            llm_provider="ollama",
            base_url="http://localhost:11434",
            api_key="",
        )
        self.assertTrue(settings.has_llm)

        request_data = llm.build_request(
            provider="ollama",
            base_url=settings.base_url,
            model="qwen3",
            api_key="",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.2,
            max_tokens=None,
        )
        self.assertEqual(request_data.url, "http://localhost:11434/api/chat")
        self.assertNotIn("Authorization", request_data.headers)


if __name__ == "__main__":
    unittest.main()
