from __future__ import annotations

import json
from datetime import date
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from pipeline.config import Settings
import pipeline.generator as generator
from pipeline.ingest import build_coverage, expected_authors_from_accounts
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


def make_article(index: int, *, source: str = "雪球", author: str | None = None) -> Article:
    return Article(
        path=Path(f"article-{index}.md"),
        source=source,
        author=author if author is not None else f"author-{index}",
        title=f"title-{index}",
        url=f"https://example.com/{index}",
        published_at="2026-06-10 08:00",
        content=f"content for article {index}",
    )


class CoverageTests(unittest.TestCase):
    def test_build_coverage_without_expected_is_backward_compatible(self) -> None:
        rows = build_coverage([make_article(1, source="雪球", author="甲")])
        xq = next(r for r in rows if r.source == "雪球")
        self.assertEqual(xq.articles_total, 1)
        self.assertEqual(xq.authors_total, 1)
        self.assertEqual(xq.expected_authors, 0)
        self.assertEqual(xq.missing_authors, [])

    def test_build_coverage_with_expected_marks_missing(self) -> None:
        expected = {"雪球": ["甲", "乙", "丙"], "微博": ["丁"]}
        rows = build_coverage(
            [make_article(1, source="雪球", author="甲")],
            expected,
        )
        xq = next(r for r in rows if r.source == "雪球")
        self.assertEqual(xq.expected_authors, 3)
        self.assertEqual(xq.authors_total, 1)
        self.assertEqual(sorted(xq.missing_authors), ["丙", "乙"])

        wb = next(r for r in rows if r.source == "微博")
        self.assertEqual(wb.articles_total, 0)
        self.assertEqual(wb.expected_authors, 1)
        self.assertEqual(wb.missing_authors, ["丁"])

    def test_expected_authors_from_accounts_skips_disabled(self) -> None:
        config = {
            "xueqiu": [
                {"name": "甲", "enabled": True},
                {"name": "乙", "enabled": False},
            ],
            "weibo": [{"name": "丙", "enabled": True}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "accounts.json"
            path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            expected = expected_authors_from_accounts(path)
        self.assertEqual(expected.get("雪球"), ["甲"])
        self.assertEqual(expected.get("微博"), ["丙"])


class FallbackRenderTests(unittest.TestCase):
    def _settings_no_llm(self) -> Settings:
        s = make_settings(concurrency=1)
        return Settings(**{**s.__dict__, "base_url": "", "model": "", "api_key": ""})

    def test_fallback_contains_next_focus_and_coverage_columns(self) -> None:
        import datetime as _dt

        articles = [make_article(i, source="雪球", author=f"作者{i}") for i in range(3)]
        coverage = build_coverage(articles, {"雪球": ["作者0", "作者1", "作者X"]})
        markdown = generator.generate_fallback(
            articles, coverage, _dt.date(2026, 6, 11), self._settings_no_llm()
        )
        self.assertIn("🎯 下期关注", markdown)
        self.assertIn("已覆盖/配置", markdown)
        # 静默账号 作者X 应出现在覆盖表的静默账号列
        self.assertIn("作者X", markdown)


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
