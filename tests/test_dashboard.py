from __future__ import annotations

from datetime import date
import json

from pipeline.dashboard import build_dashboard, build_dashboard_snapshot
from pipeline.hypothesis_io import write_json

from .test_hypothesis_models import hypothesis_payload


def _write_report(root, day: str, *, with_hypothesis: bool = False, verification=None):
    report_dir = root / "reports" / day
    report_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        report_dir / "codex-context.json",
        {
            "schema_version": "1.0",
            "report_date": day,
            "article_count": 12,
            "coverage": [
                {
                    "source": "雪球",
                    "authors_total": 1,
                    "articles_total": 8,
                    "expected_authors": 1,
                    "missing_authors": [],
                },
                {
                    "source": "微博",
                    "authors_total": 1,
                    "articles_total": 3,
                    "expected_authors": 1,
                    "missing_authors": [],
                },
                {
                    "source": "微信公众号",
                    "authors_total": 1,
                    "articles_total": 1,
                    "expected_authors": 1,
                    "missing_authors": [],
                },
            ],
        },
    )
    write_json(report_dir / "evidence.json", {"schema_version": "1.0", "report_date": day, "items": []})
    write_json(
        report_dir / "run-manifest.json",
        {"schema_version": "1.0", "report_date": day, "warnings": []},
    )
    (report_dir / "daily-brief.md").write_text("# report", encoding="utf-8")
    if with_hypothesis:
        write_json(
            report_dir / "hypotheses.json",
            {
                "schema_version": "1.0",
                "report_date": day,
                "hypotheses": [hypothesis_payload()],
            },
        )
    if verification is not None:
        write_json(
            report_dir / "verification.json",
            {"schema_version": "1.0", "report_date": day, "results": [verification]},
        )


def test_dashboard_snapshot_rebuilds_status_and_due_state(tmp_path):
    _write_report(tmp_path, "2026-08-06", with_hypothesis=True)
    _write_report(
        tmp_path,
        "2026-08-07",
        verification={
            "hypothesis_id": "H-20260806-001",
            "previous_status": "pending",
            "status": "partially_confirmed",
            "conditions": [],
            "falsification_conditions": [],
            "reason": "只满足部分条件。",
            "deterministic": True,
            "evidence_ids": [],
            "evaluated_at": "2026-08-07T09:00:00+08:00",
        },
    )

    snapshot = build_dashboard_snapshot(tmp_path / "reports", as_of=date(2026, 8, 7))

    assert snapshot["latest_report_date"] == "2026-08-07"
    assert snapshot["summary"]["active_hypotheses"] == 1
    assert snapshot["hypotheses"][0]["status"] == "partially_confirmed"
    assert snapshot["hypotheses"][0]["history"][0]["evidence_ids"] == []
    assert snapshot["latest"]["readiness"]["status"] == "ready"
    assert snapshot["reports"][-1]["article_count"] == 12


def test_dashboard_build_writes_snapshot_and_self_contained_html(tmp_path):
    _write_report(tmp_path, "2026-08-06", with_hypothesis=True)
    output_dir = tmp_path / "dashboard"

    result = build_dashboard(tmp_path / "reports", output_dir, as_of=date(2026, 8, 6))

    assert result.snapshot_path == output_dir / "snapshot.json"
    assert result.html_path == output_dir / "index.html"
    payload = json.loads(result.snapshot_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    html = result.html_path.read_text(encoding="utf-8")
    assert "window.__DASHBOARD_DATA__" in html
    assert "投资复盘看板" in html
    assert "dashboard.js" not in html
