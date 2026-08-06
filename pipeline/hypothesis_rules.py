from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable
import operator

from .hypothesis_io import TrackedHypothesis
from .hypothesis_models import Condition, Hypothesis


COMPARATORS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}

DEFAULT_FIELDS = {
    "price_threshold": "close",
    "turnover_threshold": "turnover",
    "capital_flow": "main_net_inflow",
}


def evaluate_hypothesis(
    tracked: TrackedHypothesis,
    evidence: Iterable[dict[str, Any]],
    *,
    report_date: date,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    hypothesis = tracked.hypothesis
    relevant = [item for item in evidence if item.get("hypothesis_id") == hypothesis.id]
    manual = _latest_manual_resolution(relevant)
    if manual is not None:
        return {
            "hypothesis_id": hypothesis.id,
            "previous_status": tracked.status,
            "status": manual["resolved_status"],
            "conditions": [],
            "falsification_conditions": [],
            "reason": manual["note"],
            "deterministic": False,
            "evidence_ids": [manual["evidence_id"]],
            "evaluated_at": evaluated_at or _now_iso(),
        }

    support_results = [
        evaluate_condition(condition, relevant) for condition in hypothesis.conditions
    ]
    falsification_results = [
        evaluate_condition(condition, relevant)
        for condition in hypothesis.falsification_conditions
    ]
    status, reason = _derive_status(
        hypothesis,
        support_results,
        falsification_results,
        report_date=report_date,
    )
    evidence_ids = sorted(
        {
            evidence_id
            for result in support_results + falsification_results
            for evidence_id in result["evidence_ids"]
        }
    )
    return {
        "hypothesis_id": hypothesis.id,
        "previous_status": tracked.status,
        "status": status,
        "conditions": support_results,
        "falsification_conditions": falsification_results,
        "reason": reason,
        "deterministic": hypothesis.verification_mode == "quantitative",
        "evidence_ids": evidence_ids,
        "evaluated_at": evaluated_at or _now_iso(),
    }


def evaluate_condition(
    condition: Condition,
    evidence: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    if condition.type == "relative_return":
        return _evaluate_relative_return(condition, evidence)
    return _evaluate_threshold(condition, evidence)


def _evaluate_threshold(
    condition: Condition,
    evidence: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    field = condition.field or DEFAULT_FIELDS[condition.type]
    rows = [
        item
        for item in evidence
        if item.get("evidence_type") == "market_metric"
        and _entity_matches(item, condition.entity)
        and _metric_matches(str(item.get("metric", "")), field)
        and str(item.get("unit", "")) == condition.unit
    ]
    rows = _latest_per_date(rows)
    passed_rows = [
        item
        for item in rows
        if COMPARATORS[condition.operator](float(item["value"]), condition.value)
    ]
    passed = len(passed_rows) >= condition.required_days
    partial = bool(passed_rows) and not passed
    values = [
        {
            "date": item["observed_date"],
            "value": item["value"],
            "unit": item["unit"],
        }
        for item in rows
    ]
    return {
        "condition": condition.to_dict(),
        "available": bool(rows),
        "passed": passed,
        "partial": partial,
        "observed": {
            "matching_days": len(passed_rows),
            "required_days": condition.required_days,
            "values": values,
        },
        "evidence_ids": [item["evidence_id"] for item in rows],
        "reason": _threshold_reason(condition, rows, len(passed_rows)),
    }


def _evaluate_relative_return(
    condition: Condition,
    evidence: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    subject_rows = _close_series(evidence, condition.entity)
    benchmark_rows = _close_series(evidence, condition.benchmark)
    subject_by_date = {item["observed_date"]: item for item in subject_rows}
    benchmark_by_date = {item["observed_date"]: item for item in benchmark_rows}
    common_dates = sorted(set(subject_by_date) & set(benchmark_by_date))
    required_points = condition.window_trading_days + 1
    enough = len(common_dates) >= required_points
    selected_dates = common_dates[-required_points:] if enough else common_dates
    evidence_ids = [
        item["evidence_id"]
        for day in selected_dates
        for item in (subject_by_date[day], benchmark_by_date[day])
    ]

    observed: dict[str, Any] = {
        "common_observations": len(common_dates),
        "required_observations": required_points,
        "dates": selected_dates,
    }
    if len(selected_dates) < 2:
        return {
            "condition": condition.to_dict(),
            "available": bool(selected_dates),
            "passed": False,
            "partial": False,
            "observed": observed,
            "evidence_ids": evidence_ids,
            "reason": "relative return requires at least two aligned close observations",
        }

    first_date, last_date = selected_dates[0], selected_dates[-1]
    subject_start = float(subject_by_date[first_date]["value"])
    subject_end = float(subject_by_date[last_date]["value"])
    benchmark_start = float(benchmark_by_date[first_date]["value"])
    benchmark_end = float(benchmark_by_date[last_date]["value"])
    if subject_start == 0 or benchmark_start == 0:
        return {
            "condition": condition.to_dict(),
            "available": True,
            "passed": False,
            "partial": False,
            "observed": observed,
            "evidence_ids": evidence_ids,
            "reason": "relative return cannot use a zero starting value",
        }

    subject_return = (subject_end / subject_start - 1) * 100
    benchmark_return = (benchmark_end / benchmark_start - 1) * 100
    excess_return = subject_return - benchmark_return
    threshold_met = COMPARATORS[condition.operator](excess_return, condition.value)
    observed.update(
        {
            "subject_return_pct": round(subject_return, 6),
            "benchmark_return_pct": round(benchmark_return, 6),
            "excess_return_percentage_point": round(excess_return, 6),
        }
    )
    return {
        "condition": condition.to_dict(),
        "available": True,
        "passed": enough and threshold_met,
        "partial": threshold_met and not enough,
        "observed": observed,
        "evidence_ids": evidence_ids,
        "reason": (
            f"excess return {excess_return:.2f} percentage points; "
            f"requires {condition.operator} {condition.value:g} over "
            f"{condition.window_trading_days} trading days"
        ),
    }


def _derive_status(
    hypothesis: Hypothesis,
    support: list[dict[str, Any]],
    falsification: list[dict[str, Any]],
    *,
    report_date: date,
) -> tuple[str, str]:
    if any(item["passed"] for item in falsification):
        return "falsified", "At least one predefined falsification condition was met."
    if support and all(item["passed"] for item in support):
        return "confirmed", "All predefined support conditions were met."
    if any(item["passed"] or item["partial"] for item in support):
        return (
            "partially_confirmed",
            "Some support conditions were met, but the full confirmation rule was not satisfied.",
        )

    has_available = any(
        item["available"] for item in support + falsification
    )
    if report_date >= hypothesis.deadline:
        if not has_available:
            return "unavailable", "The deadline was reached without the required evidence."
        return "inconclusive", "The deadline was reached without confirmation or falsification."
    if not has_available and hypothesis.verification_mode in {"manual", "event", "hybrid"}:
        return "pending", hypothesis.manual_reason or "Manual or event evidence is still required."
    return "pending", "No confirmation or falsification condition has been met yet."


def _latest_manual_resolution(evidence: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [item for item in evidence if item.get("evidence_type") == "manual_resolution"]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: str(item.get("fetched_at", "")))[-1]


def _entity_matches(item: dict[str, Any], expected: str) -> bool:
    entity = item.get("entity")
    if not isinstance(entity, dict):
        return False
    expected_upper = expected.strip().upper()
    return expected_upper in {
        str(entity.get("thscode", "")).strip().upper(),
        str(entity.get("name", "")).strip().upper(),
    }


def _metric_matches(metric: str, field: str) -> bool:
    metric_lower = metric.strip().lower()
    field_lower = field.strip().lower()
    return metric_lower == field_lower or metric_lower.endswith("." + field_lower)


def _latest_per_date(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: str(item.get("fetched_at", ""))):
        by_date[str(row["observed_date"])] = row
    return [by_date[day] for day in sorted(by_date)]


def _close_series(
    evidence: Iterable[dict[str, Any]], entity: str
) -> list[dict[str, Any]]:
    rows = [
        item
        for item in evidence
        if item.get("evidence_type") == "market_metric"
        and _entity_matches(item, entity)
        and _metric_matches(str(item.get("metric", "")), "close")
    ]
    return _latest_per_date(rows)


def _threshold_reason(
    condition: Condition,
    rows: list[dict[str, Any]],
    matching_days: int,
) -> str:
    if not rows:
        return "No matching evidence with the required entity, metric, and unit."
    return (
        f"{matching_days} of {len(rows)} observed days matched "
        f"{condition.operator} {condition.value:g} {condition.unit}; "
        f"requires {condition.required_days} day(s)."
    )


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
