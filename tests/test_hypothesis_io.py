from __future__ import annotations

from datetime import date

from pipeline.hypothesis_io import (
    active_hypotheses,
    build_author_reliability,
    load_hypothesis_ledger,
    previous_report_date,
    write_json,
)

from .test_hypothesis_models import hypothesis_payload


def _write_hypotheses(reports_root, day="2026-08-06"):
    report_dir = reports_root / day
    report_dir.mkdir(parents=True)
    write_json(
        report_dir / "hypotheses.json",
        {
            "schema_version": "1.0",
            "report_date": day,
            "hypotheses": [hypothesis_payload()],
        },
    )
    (report_dir / "daily-brief.md").write_text("# report", encoding="utf-8")
    return report_dir


def test_previous_report_skips_missing_days_and_weekend(tmp_path):
    reports_root = tmp_path / "reports"
    _write_hypotheses(reports_root)

    assert previous_report_date(reports_root, date(2026, 8, 10)) == date(2026, 8, 6)


def test_ledger_applies_verification_history(tmp_path):
    reports_root = tmp_path / "reports"
    _write_hypotheses(reports_root)
    next_dir = reports_root / "2026-08-07"
    next_dir.mkdir()
    write_json(
        next_dir / "verification.json",
        {
            "schema_version": "1.0",
            "report_date": "2026-08-07",
            "results": [
                {
                    "hypothesis_id": "H-20260806-001",
                    "previous_status": "pending",
                    "status": "partially_confirmed",
                    "conditions": [],
                    "falsification_conditions": [],
                    "reason": "One of two required days matched.",
                    "deterministic": True,
                    "evidence_ids": ["E-20260807-001"],
                    "evaluated_at": "2026-08-07T09:00:00+08:00",
                }
            ],
        },
    )

    ledger = load_hypothesis_ledger(
        reports_root, before_date=date(2026, 8, 8)
    )

    assert ledger["H-20260806-001"].status == "partially_confirmed"
    assert ledger["H-20260806-001"].history[0]["report_date"] == "2026-08-07"


def test_active_hypotheses_keep_nonterminal_statuses(tmp_path):
    reports_root = tmp_path / "reports"
    _write_hypotheses(reports_root)

    active = active_hypotheses(reports_root, report_date=date(2026, 8, 10))

    assert [item.hypothesis.id for item in active] == ["H-20260806-001"]


def test_quality_control_can_quarantine_hypotheses_from_rollover(tmp_path):
    reports_root = tmp_path / "reports"
    report_dir = _write_hypotheses(reports_root)
    write_json(
        report_dir / "quality-control.json",
        {
            "schema_version": "1.0",
            "report_date": "2026-08-06",
            "hypothesis_rollover": False,
            "reason": "low quality source day",
        },
    )

    active = active_hypotheses(reports_root, report_date=date(2026, 8, 10))

    assert active == []


def test_author_reliability_counts_only_final_outcomes_and_splits_coauthors(tmp_path):
    reports_root = tmp_path / "reports"
    first_dir = reports_root / "2026-08-06"
    first_dir.mkdir(parents=True)
    hypotheses = [
        hypothesis_payload(
            sources=[
                {
                    "author": "甲",
                    "article_id": "A-001",
                    "url": "https://example.com/1",
                    "quote": "甲的判断。",
                }
            ]
        ),
        hypothesis_payload(
            id="H-20260806-002",
            sources=[
                {
                    "author": "甲、乙",
                    "article_id": "A-002",
                    "url": "https://example.com/2",
                    "quote": "联合判断。",
                }
            ],
        ),
        hypothesis_payload(
            id="H-20260806-003",
            sources=[
                {
                    "author": "乙",
                    "article_id": "A-003",
                    "url": "https://example.com/3",
                    "quote": "乙的判断。",
                }
            ],
        ),
    ]
    write_json(
        first_dir / "hypotheses.json",
        {"schema_version": "1.0", "report_date": "2026-08-06", "hypotheses": hypotheses},
    )
    next_dir = reports_root / "2026-08-07"
    next_dir.mkdir()
    write_json(
        next_dir / "verification.json",
        {
            "schema_version": "1.0",
            "report_date": "2026-08-07",
            "results": [
                {
                    "hypothesis_id": "H-20260806-001",
                    "previous_status": "pending",
                    "status": "confirmed",
                    "conditions": [],
                    "falsification_conditions": [],
                    "reason": "成立。",
                    "deterministic": True,
                    "evidence_ids": [],
                    "evaluated_at": "2026-08-07T09:00:00+08:00",
                },
                {
                    "hypothesis_id": "H-20260806-002",
                    "previous_status": "pending",
                    "status": "falsified",
                    "conditions": [],
                    "falsification_conditions": [],
                    "reason": "不成立。",
                    "deterministic": True,
                    "evidence_ids": [],
                    "evaluated_at": "2026-08-07T09:00:00+08:00",
                },
            ],
        },
    )

    ledger = load_hypothesis_ledger(reports_root, include_date=True)
    rows = build_author_reliability(ledger.values())

    assert rows == [
        {"author": "甲", "confirmed": 1, "falsified": 1, "resolved": 2, "win_rate": 0.5, "rank": 1},
        {"author": "乙", "confirmed": 0, "falsified": 1, "resolved": 1, "win_rate": 0.0, "rank": 2},
    ]
