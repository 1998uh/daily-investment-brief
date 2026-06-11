from __future__ import annotations

import json
from datetime import date
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

from pipeline.config import Settings
import pipeline.generator as generator
from pipeline.models import Article


def make_settings(*, concurrency: int) -> Settings:
    return Settings(
        base_url="https://example.com",
        model="test-model",
        api_key="test-key",
        llm_timeout_seconds=30,
        llm_retries=0,
        llm_retry_delay_seconds=0,
        timezone="Asia/Shanghai",
        window_start="08:00",
        window_end="08:00",
        markets="A股 港股",
        style="strong_narrative_emoji",
        max_chars_per_article=1_000,
        batch_size=2,
        llm_batch_concurrency=concurrency,
        temperature=0.2,
        llm_thinking_type=None,
        llm_max_tokens=None,
    )


def make_article(index: int) -> Article:
    return Article(
        path=Path(f"article-{index}.md"),
        source="雪球",
        author=f"author-{index}",
        title=f"title-{index}",
        url=f"https://example.com/{index}",
        published_at="2026-06-10 08:00",
        content=f"content for article {index}",
    )


class SummarizeBatchesTests(unittest.TestCase):
    def test_summarize_batches_preserves_order_when_concurrent(self) -> None:
        batches = generator.chunked([make_article(i) for i in range(5)], 2)
        current = 0
        max_inflight = 0
        lock = threading.Lock()
        delays = {1: 0.15, 2: 0.05, 3: 0.1}

        def fake_chat_completion(settings, messages, *, temperature=None, label=""):
            nonlocal current, max_inflight
            batch_index = int(label.split()[-1].split("/")[0])
            with lock:
                current += 1
                max_inflight = max(max_inflight, current)
            time.sleep(delays[batch_index])
            with lock:
                current -= 1
            return json.dumps({"batch": batch_index})

        with patch("pipeline.generator.chat_completion", side_effect=fake_chat_completion):
            summaries = generator._summarize_batches(batches, make_settings(concurrency=2), "prompt")

        self.assertEqual(summaries, [{"batch": 1}, {"batch": 2}, {"batch": 3}])
        self.assertGreaterEqual(max_inflight, 2)

    def test_summarize_batches_stays_sequential_with_single_worker(self) -> None:
        batches = generator.chunked([make_article(i) for i in range(4)], 2)
        current = 0
        max_inflight = 0
        lock = threading.Lock()

        def fake_chat_completion(settings, messages, *, temperature=None, label=""):
            nonlocal current, max_inflight
            with lock:
                current += 1
                max_inflight = max(max_inflight, current)
            time.sleep(0.02)
            with lock:
                current -= 1
            return json.dumps({"label": label})

        with patch("pipeline.generator.chat_completion", side_effect=fake_chat_completion):
            summaries = generator._summarize_batches(batches, make_settings(concurrency=1), "prompt")

        self.assertEqual(len(summaries), 2)
        self.assertEqual(max_inflight, 1)


class GenerateWithLlmTests(unittest.TestCase):
    def test_final_brief_does_not_inherit_summary_token_cap(self) -> None:
        articles = [make_article(i) for i in range(2)]
        settings = make_settings(concurrency=1)
        settings = Settings(
            **{
                **settings.__dict__,
                "llm_max_tokens": 3000,
            }
        )
        seen = []

        def fake_chat_completion(settings, messages, *, temperature=None, label=""):
            seen.append((label, settings.llm_max_tokens))
            if label.startswith("batch summary"):
                return json.dumps({"topics": []})
            return "# Test Report\n\nComplete body\n\n---\n\n> **免责声明**：ok"

        with patch("pipeline.generator.chat_completion", side_effect=fake_chat_completion):
            generator.generate_with_llm(articles, [], date(2026, 6, 11), settings)

        self.assertIn(("batch summary 1/1", 3000), seen)
        self.assertIn(("final brief", None), seen)


if __name__ == "__main__":
    unittest.main()
