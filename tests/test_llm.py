from __future__ import annotations

import json
import unittest
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


if __name__ == "__main__":
    unittest.main()
