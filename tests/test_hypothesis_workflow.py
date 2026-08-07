from __future__ import annotations

from datetime import date
import json

from pipeline.config import Settings
from pipeline.hypothesis_io import write_json
from pipeline.hypothesis_workflow import prepare_hypothesis_context, verify_hypotheses
from pipeline.report_validator import validate_report_bundle

from .test_hypothesis_models import hypothesis_payload


def _settings():
    return Settings(
        base_url="",
        model="",
        api_key="",
        llm_timeout_seconds=30,
        llm_retries=0,
        llm_retry_delay_seconds=0,
        timezone="Asia/Shanghai",
        window_start="08:00",
        window_end="08:00",
        markets="A股",
        style="test",
        max_chars_per_article=1000,
        batch_size=2,
        batch_max_chars=15000,
        llm_batch_concurrency=1,
        temperature=0.2,
        llm_thinking_type=None,
        llm_max_tokens=None,
    )


def _source(source_dir):
    source_dir.mkdir(parents=True)
    (source_dir / "article.md").write_text(
        """---
source: 雪球
author: 作者
title: 测试文章
url: https://example.com/article
published_at: 2026-08-07 07:00
---

文章正文。
""",
        encoding="utf-8",
    )


def _historical_hypothesis(reports_root):
    report_dir = reports_root / "2026-08-06"
    report_dir.mkdir(parents=True)
    (report_dir / "daily-brief.md").write_text("# prior", encoding="utf-8")
    write_json(
        report_dir / "hypotheses.json",
        {
            "schema_version": "1.0",
            "report_date": "2026-08-06",
            "hypotheses": [hypothesis_payload()],
        },
    )


def test_prepare_builds_codex_context_with_active_hypotheses(tmp_path):
    source_dir = tmp_path / "sources" / "2026-08-07"
    reports_root = tmp_path / "reports"
    out_dir = reports_root / "2026-08-07"
    _source(source_dir)
    _historical_hypothesis(reports_root)

    path = prepare_hypothesis_context(
        report_date=date(2026, 8, 7),
        settings=_settings(),
        source_dir=source_dir,
        out_dir=out_dir,
        reports_root=reports_root,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["article_count"] == 1
    assert payload["previous_report_date"] == "2026-08-06"
    assert payload["active_hypotheses"][0]["id"] == "H-20260806-001"
    assert "articles" not in payload
    assert "required_evidence" not in payload
    assert payload["article_pack"].endswith("article-pack.md")
    assert payload["article_index"].endswith("article-index.jsonl")
    assert payload["evidence_tasks"].endswith("evidence-tasks.json")

    tasks = json.loads((out_dir / "evidence-tasks.json").read_text(encoding="utf-8"))
    assert tasks["scheduled_hypothesis_ids"] == ["H-20260806-001"]
    assert len(tasks["hypotheses"][0]["queries"]) == 1
    assert tasks["hypotheses"][0]["queries"][0]["entity"] == "399006.SZ"
    assert tasks["hypotheses"][0]["queries"][0]["roles"] == [
        "support",
        "falsification",
    ]

    article_pack = (out_dir / "article-pack.md").read_text(encoding="utf-8")
    assert "文章正文。" in article_pack
    assert "provider:" not in article_pack
    assert "https://example.com/article" not in article_pack

    article_index = (out_dir / "article-index.jsonl").read_text(encoding="utf-8")
    assert "https://example.com/article" in article_index
    assert '"sha256":' in article_index


def test_verify_reads_current_evidence_and_writes_result(tmp_path):
    reports_root = tmp_path / "reports"
    out_dir = reports_root / "2026-08-07"
    _historical_hypothesis(reports_root)
    write_json(
        out_dir / "evidence.json",
        {
            "schema_version": "1.0",
            "report_date": "2026-08-07",
            "items": [
                {
                    "evidence_id": "E-20260807-001",
                    "hypothesis_id": "H-20260806-001",
                    "evidence_type": "market_metric",
                    "metric": "index.close",
                    "entity": {"name": "创业板指", "thscode": "399006.SZ"},
                    "observed_date": "2026-08-07",
                    "value": 3500,
                    "unit": "point",
                    "provider": "test",
                    "fetched_at": "2026-08-07T16:00:00+08:00",
                }
            ],
        },
    )

    path = verify_hypotheses(
        report_date=date(2026, 8, 7),
        out_dir=out_dir,
        reports_root=reports_root,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["results"][0]["status"] == "partially_confirmed"
    assert payload["results"][0]["evidence_ids"] == ["E-20260807-001"]


def test_prepare_skips_deadline_only_hypothesis_until_due(tmp_path):
    source_dir = tmp_path / "sources" / "2026-08-07"
    reports_root = tmp_path / "reports"
    out_dir = reports_root / "2026-08-07"
    _source(source_dir)
    prior_dir = reports_root / "2026-08-06"
    prior_dir.mkdir(parents=True)
    manual = hypothesis_payload(
        id="H-20260806-002",
        verification_mode="manual",
        conditions=[],
        falsification_conditions=[],
        manual_reason="等待公司正式公告。",
        deadline="2026-09-30",
    )
    deferred = hypothesis_payload(
        id="H-20260806-003",
        deadline="2026-08-10",
        next_review_date="2026-08-09",
    )
    write_json(
        prior_dir / "hypotheses.json",
        {
            "schema_version": "1.0",
            "report_date": "2026-08-06",
            "hypotheses": [hypothesis_payload(), manual, deferred],
        },
    )

    prepare_hypothesis_context(
        report_date=date(2026, 8, 7),
        settings=_settings(),
        source_dir=source_dir,
        out_dir=out_dir,
        reports_root=reports_root,
    )

    context = json.loads((out_dir / "codex-context.json").read_text(encoding="utf-8"))
    tasks = json.loads((out_dir / "evidence-tasks.json").read_text(encoding="utf-8"))

    assert tasks["scheduled_hypothesis_ids"] == ["H-20260806-001"]
    summaries = {item["id"]: item for item in context["active_hypotheses"]}
    assert summaries["H-20260806-002"]["review_due"] is False
    assert summaries["H-20260806-002"]["review_policy"] == "deadline_only"
    assert summaries["H-20260806-003"]["review_due"] is False


def test_verify_only_evaluates_scheduled_hypotheses(tmp_path):
    reports_root = tmp_path / "reports"
    out_dir = reports_root / "2026-08-07"
    prior_dir = reports_root / "2026-08-06"
    prior_dir.mkdir(parents=True)
    manual = hypothesis_payload(
        id="H-20260806-002",
        verification_mode="manual",
        conditions=[],
        falsification_conditions=[],
        manual_reason="等待公司正式公告。",
        deadline="2026-09-30",
    )
    write_json(
        prior_dir / "hypotheses.json",
        {
            "schema_version": "1.0",
            "report_date": "2026-08-06",
            "hypotheses": [hypothesis_payload(), manual],
        },
    )
    write_json(
        out_dir / "evidence-tasks.json",
        {
            "schema_version": "1.0",
            "report_date": "2026-08-07",
            "scheduled_hypothesis_ids": ["H-20260806-001"],
            "hypotheses": [],
        },
    )
    write_json(
        out_dir / "evidence.json",
        {"schema_version": "1.0", "report_date": "2026-08-07", "items": []},
    )

    path = verify_hypotheses(
        report_date=date(2026, 8, 7),
        out_dir=out_dir,
        reports_root=reports_root,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert [item["hypothesis_id"] for item in payload["results"]] == [
        "H-20260806-001"
    ]


def test_validate_generates_html_and_manifest_for_consistent_bundle(tmp_path):
    reports_root = tmp_path / "reports"
    out_dir = reports_root / "2026-08-07"
    out_dir.mkdir(parents=True)
    hypothesis_1 = hypothesis_payload(
        id="H-20260807-001",
        created_date="2026-08-07",
        deadline="2026-08-11",
    )
    hypothesis_2 = hypothesis_payload(
        id="H-20260807-002",
        created_date="2026-08-07",
        deadline="2026-08-11",
    )
    (out_dir / "daily-brief.md").write_text(
        "# 日报\n\n## 下期关注\n\nH-20260807-001\n\nH-20260807-002\n",
        encoding="utf-8",
    )
    write_json(out_dir / "codex-context.json", {"schema_version": "1.0"})
    (out_dir / "article-pack.md").write_text("# articles\n", encoding="utf-8")
    write_json(
        out_dir / "evidence-tasks.json",
        {
            "schema_version": "1.0",
            "report_date": "2026-08-07",
            "scheduled_hypothesis_ids": [],
            "hypotheses": [],
        },
    )
    write_json(
        out_dir / "evidence.json",
        {"schema_version": "1.0", "report_date": "2026-08-07", "items": []},
    )
    write_json(
        out_dir / "verification.json",
        {"schema_version": "1.0", "report_date": "2026-08-07", "results": []},
    )
    write_json(
        out_dir / "hypotheses.json",
        {
            "schema_version": "1.0",
            "report_date": "2026-08-07",
            "hypotheses": [hypothesis_1, hypothesis_2],
        },
    )

    report = validate_report_bundle(
        report_date=date(2026, 8, 7),
        out_dir=out_dir,
        reports_root=reports_root,
        strict=True,
    )

    assert report.ok
    assert report.html_path and report.html_path.exists()
    assert report.manifest_path and report.manifest_path.exists()


def test_validate_rejects_more_than_four_new_hypotheses(tmp_path):
    reports_root = tmp_path / "reports"
    out_dir = reports_root / "2026-08-07"
    out_dir.mkdir(parents=True)
    hypotheses = [
        hypothesis_payload(
            id=f"H-20260807-{index:03d}",
            created_date="2026-08-07",
            deadline="2026-08-11",
        )
        for index in range(1, 6)
    ]
    (out_dir / "daily-brief.md").write_text(
        "# 日报\n\n" + "\n".join(item["id"] for item in hypotheses),
        encoding="utf-8",
    )
    write_json(
        out_dir / "hypotheses.json",
        {
            "schema_version": "1.0",
            "report_date": "2026-08-07",
            "hypotheses": hypotheses,
        },
    )

    report = validate_report_bundle(
        report_date=date(2026, 8, 7),
        out_dir=out_dir,
        reports_root=reports_root,
    )

    assert not report.ok
    assert "hypotheses.json must contain 2-4 new hypotheses; found 5" in report.errors


def test_validate_requires_review_policy_for_token_efficient_runtime(tmp_path):
    reports_root = tmp_path / "reports"
    out_dir = reports_root / "2026-08-07"
    out_dir.mkdir(parents=True)
    hypotheses = [
        hypothesis_payload(
            id=f"H-20260807-{index:03d}",
            created_date="2026-08-07",
            deadline="2026-08-11",
        )
        for index in range(1, 3)
    ]
    (out_dir / "daily-brief.md").write_text(
        "# 日报\n\n" + "\n".join(item["id"] for item in hypotheses),
        encoding="utf-8",
    )
    write_json(
        out_dir / "codex-context.json",
        {
            "schema_version": "1.0",
            "article_pack": "article-pack.md",
            "article_index": "article-index.jsonl",
            "evidence_tasks": "evidence-tasks.json",
        },
    )
    (out_dir / "article-pack.md").write_text("# articles\n", encoding="utf-8")
    (out_dir / "article-index.jsonl").write_text("", encoding="utf-8")
    write_json(out_dir / "evidence-tasks.json", {})
    write_json(
        out_dir / "hypotheses.json",
        {
            "schema_version": "1.0",
            "report_date": "2026-08-07",
            "hypotheses": hypotheses,
        },
    )

    report = validate_report_bundle(
        report_date=date(2026, 8, 7),
        out_dir=out_dir,
        reports_root=reports_root,
    )

    assert not report.ok
    assert any("review_policy is required" in error for error in report.errors)
