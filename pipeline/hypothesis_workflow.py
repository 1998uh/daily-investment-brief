from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config import ROOT, Settings
from .datetime_utils import brief_window, format_window_cn
from .hypothesis_io import (
    active_hypotheses,
    article_id,
    file_sha256,
    load_all_evidence,
    previous_report_date,
    read_json,
    write_json,
)
from .hypothesis_models import (
    ContractError,
    SCHEMA_VERSION,
    parse_evidence_document,
)
from .hypothesis_rules import evaluate_hypothesis
from .ingest import build_coverage, expected_authors_from_accounts, load_articles


def prepare_hypothesis_context(
    *,
    report_date: date,
    settings: Settings,
    source_dir: Path,
    out_dir: Path,
    reports_root: Path | None = None,
    accounts_path: Path | None = None,
) -> Path:
    reports_root = reports_root or ROOT / "reports"
    articles = load_articles(source_dir)
    if not articles:
        raise ContractError(f"no articles found in {source_dir}")
    expected = (
        expected_authors_from_accounts(accounts_path)
        if accounts_path and accounts_path.exists()
        else None
    )
    coverage = build_coverage(articles, expected)
    active = active_hypotheses(reports_root, report_date=report_date)
    window_start, window_end = brief_window(
        report_date,
        timezone_name=settings.timezone,
        start_time=settings.window_start,
        end_time=settings.window_end,
    )
    previous = previous_report_date(reports_root, report_date)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "report_date": report_date.isoformat(),
        "timezone": settings.timezone,
        "source_dir": _display_path(source_dir),
        "article_count": len(articles),
        "articles": [
            {
                "article_id": article_id(article),
                "path": _display_path(article.path),
                "source": article.source,
                "author": article.author,
                "title": article.title,
                "url": article.url,
                "published_at": article.published_at,
                "sha256": file_sha256(article.path),
            }
            for article in articles
        ],
        "coverage": [
            {
                "source": row.source,
                "authors_total": row.authors_total,
                "articles_total": row.articles_total,
                "authors": row.authors,
                "expected_authors": row.expected_authors,
                "missing_authors": row.missing_authors,
            }
            for row in coverage
        ],
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            "label": format_window_cn(window_start, window_end),
        },
        "previous_report_date": previous.isoformat() if previous else None,
        "active_hypotheses": [tracked.snapshot() for tracked in active],
        "required_evidence": [
            item
            for tracked in active
            for item in required_evidence(tracked.hypothesis.to_dict())
        ],
        "generated_at": _now_iso(),
    }
    return write_json(out_dir / "codex-context.json", payload)


def required_evidence(hypothesis: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for role, key in (
        ("support", "conditions"),
        ("falsification", "falsification_conditions"),
    ):
        for condition in hypothesis.get(key, []):
            item = {
                "hypothesis_id": hypothesis["id"],
                "role": role,
                "rule_type": condition["type"],
                "entity": condition["entity"],
                "field": condition.get("field", _default_field(condition["type"])),
                "unit": condition["unit"],
                "deadline": hypothesis["deadline"],
                "recommended_provider": "hithink-finance",
            }
            if condition.get("benchmark"):
                item["benchmark"] = condition["benchmark"]
            if condition.get("window_trading_days"):
                item["window_trading_days"] = condition["window_trading_days"]
            result.append(item)
    if not result:
        result.append(
            {
                "hypothesis_id": hypothesis["id"],
                "role": "manual",
                "rule_type": hypothesis["verification_mode"],
                "deadline": hypothesis["deadline"],
                "required_evidence": hypothesis.get("manual_reason", "人工或事件证据"),
                "recommended_provider": "official-source-search",
            }
        )
    return result


def verify_hypotheses(
    *,
    report_date: date,
    out_dir: Path,
    reports_root: Path | None = None,
    evidence_path: Path | None = None,
) -> Path:
    reports_root = reports_root or ROOT / "reports"
    evidence_path = evidence_path or out_dir / "evidence.json"
    if not evidence_path.exists():
        raise ContractError(f"evidence file not found: {evidence_path}")
    document_date, current_evidence = parse_evidence_document(read_json(evidence_path))
    if document_date != report_date:
        raise ContractError("evidence report_date does not match requested date")

    active = active_hypotheses(reports_root, report_date=report_date)
    loaded_evidence = load_all_evidence(reports_root, through_date=report_date)
    all_evidence_by_id = {item["evidence_id"]: item for item in loaded_evidence}
    all_evidence_by_id.update(
        {item["evidence_id"]: item for item in current_evidence}
    )
    all_evidence = list(all_evidence_by_id.values())
    evaluated_at = _now_iso()
    results = [
        evaluate_hypothesis(
            tracked,
            all_evidence,
            report_date=report_date,
            evaluated_at=evaluated_at,
        )
        for tracked in active
    ]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "report_date": report_date.isoformat(),
        "results": results,
    }
    return write_json(out_dir / "verification.json", payload)


def _default_field(rule_type: str) -> str:
    return {
        "price_threshold": "close",
        "relative_return": "close",
        "turnover_threshold": "turnover",
        "capital_flow": "main_net_inflow",
    }.get(rule_type, "")


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
