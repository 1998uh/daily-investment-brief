from __future__ import annotations

from datetime import date

from pipeline.hypothesis_io import (
    active_hypotheses,
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
