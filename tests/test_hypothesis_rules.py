from __future__ import annotations

from datetime import date

from pipeline.hypothesis_io import TrackedHypothesis
from pipeline.hypothesis_models import Hypothesis
from pipeline.hypothesis_rules import evaluate_hypothesis

from .test_hypothesis_models import hypothesis_payload


def _market_evidence(evidence_id, observed_date, value, *, entity="399006.SZ", metric="index.close", unit="point"):
    return {
        "evidence_id": evidence_id,
        "hypothesis_id": "H-20260806-001",
        "evidence_type": "market_metric",
        "metric": metric,
        "entity": {"name": entity, "thscode": entity},
        "observed_date": observed_date,
        "value": value,
        "unit": unit,
        "provider": "test",
        "fetched_at": observed_date + "T16:00:00+08:00",
    }


def test_threshold_is_partial_until_required_days_are_met():
    tracked = TrackedHypothesis(Hypothesis.from_dict(hypothesis_payload()))

    first = evaluate_hypothesis(
        tracked,
        [_market_evidence("E-20260807-001", "2026-08-07", 3500)],
        report_date=date(2026, 8, 7),
    )
    second = evaluate_hypothesis(
        tracked,
        [
            _market_evidence("E-20260807-001", "2026-08-07", 3500),
            _market_evidence("E-20260808-001", "2026-08-08", 3510),
        ],
        report_date=date(2026, 8, 8),
    )

    assert first["status"] == "partially_confirmed"
    assert second["status"] == "confirmed"


def test_falsification_condition_has_priority():
    tracked = TrackedHypothesis(Hypothesis.from_dict(hypothesis_payload()))

    result = evaluate_hypothesis(
        tracked,
        [_market_evidence("E-20260807-001", "2026-08-07", 3350)],
        report_date=date(2026, 8, 7),
    )

    assert result["status"] == "falsified"


def test_missing_evidence_stays_pending_before_deadline():
    tracked = TrackedHypothesis(Hypothesis.from_dict(hypothesis_payload()))

    result = evaluate_hypothesis(tracked, [], report_date=date(2026, 8, 7))

    assert result["status"] == "pending"
    assert result["evidence_ids"] == []


def test_relative_return_is_calculated_from_aligned_close_series():
    payload = hypothesis_payload(
        claim="半导体五日跑赢沪深300至少2个百分点",
        conditions=[
            {
                "type": "relative_return",
                "entity": "886063.TI",
                "benchmark": "000300.SH",
                "operator": ">=",
                "value": 2,
                "unit": "percentage_point",
                "window_trading_days": 1,
            }
        ],
    )
    tracked = TrackedHypothesis(Hypothesis.from_dict(payload))
    evidence = [
        _market_evidence("E-20260807-001", "2026-08-07", 100, entity="886063.TI"),
        _market_evidence("E-20260808-001", "2026-08-08", 105, entity="886063.TI"),
        _market_evidence("E-20260807-002", "2026-08-07", 100, entity="000300.SH"),
        _market_evidence("E-20260808-002", "2026-08-08", 102, entity="000300.SH"),
    ]

    result = evaluate_hypothesis(tracked, evidence, report_date=date(2026, 8, 8))

    assert result["status"] == "confirmed"
    assert result["conditions"][0]["observed"]["excess_return_percentage_point"] == 3
