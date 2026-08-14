"""Build and serve a local, read-only investment research dashboard.

The dashboard is deliberately a static snapshot. It reads validated report
artifacts and never calls collectors, the LLM, or any mutating workflow.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import webbrowser

from .hypothesis_io import (
    dated_report_dirs,
    load_all_evidence,
    load_hypothesis_ledger,
    read_json,
    write_json,
)
from .hypothesis_models import ContractError, TERMINAL_STATUSES


DASHBOARD_SCHEMA_VERSION = "1.0"
REQUIRED_SOURCES = ("雪球", "微博", "微信公众号")
STATUS_LABELS = {
    "pending": "待验证",
    "partially_confirmed": "部分确认",
    "confirmed": "已确认",
    "falsified": "已证伪",
    "inconclusive": "无结论",
    "unavailable": "数据不可用",
    "expired": "已过期",
}
MODE_LABELS = {
    "quantitative": "量化",
    "event": "事件",
    "hybrid": "混合",
    "manual": "人工",
}


@dataclass(frozen=True)
class DashboardBuild:
    snapshot_path: Path
    html_path: Path
    snapshot: dict


def build_dashboard_snapshot(
    reports_root: Path,
    *,
    journal_root: Path | None = None,
    as_of: date | None = None,
) -> dict:
    """Aggregate report artifacts into a stable, JSON-serializable snapshot."""
    report_dirs = [
        item for item in dated_report_dirs(reports_root, before_or_equal=as_of)
        if _has_report_artifact(item[1])
    ]
    if not report_dirs:
        raise FileNotFoundError(f"no report artifacts found in {reports_root}")

    latest_date, latest_dir = report_dirs[-1]
    effective_date = as_of or latest_date
    journal_root = journal_root or reports_root.parent / "journal"
    warnings: list[str] = []

    ledger = load_hypothesis_ledger(
        reports_root,
        before_date=effective_date,
        include_date=True,
    )
    events = _load_verification_events(report_dirs, warnings)
    evidence = _load_evidence(reports_root, effective_date, warnings)
    evidence_by_hypothesis: dict[str, list[dict]] = {}
    for item in evidence:
        evidence_by_hypothesis.setdefault(item["hypothesis_id"], []).append(item)

    hypotheses = []
    for tracked in sorted(
        ledger.values(),
        key=lambda item: (item.status in TERMINAL_STATUSES, item.hypothesis.deadline, item.hypothesis.id),
    ):
        hypothesis = tracked.hypothesis
        deadline = hypothesis.deadline
        next_review = hypothesis.next_review_date
        due_date = next_review or deadline
        is_due = tracked.status not in TERMINAL_STATUSES and due_date <= effective_date
        item_events = [event for event in events if event["hypothesis_id"] == hypothesis.id]
        history = [
            {
                "date": event["date"],
                "status": event["status"],
                "status_label": STATUS_LABELS.get(event["status"], event["status"]),
                "reason": event["reason"],
                "evidence_ids": event["evidence_ids"],
                "deterministic": event["deterministic"],
            }
            for event in item_events
        ]
        hypotheses.append(
            {
                "id": hypothesis.id,
                "claim": hypothesis.claim,
                "subject": hypothesis.subject.to_dict(),
                "status": tracked.status,
                "status_label": STATUS_LABELS.get(tracked.status, tracked.status),
                "created_date": hypothesis.created_date.isoformat(),
                "deadline": deadline.isoformat(),
                "next_review_date": next_review.isoformat() if next_review else "",
                "due_date": due_date.isoformat(),
                "due": is_due,
                "overdue": is_due and due_date < effective_date,
                "verification_mode": hypothesis.verification_mode,
                "verification_mode_label": MODE_LABELS.get(
                    hypothesis.verification_mode, hypothesis.verification_mode
                ),
                "review_policy": hypothesis.review_policy,
                "sources": [
                    {
                        "author": source.author,
                        "article_id": source.article_id,
                        "url": source.url,
                        "quote": source.quote,
                    }
                    for source in hypothesis.sources
                ],
                "history": history,
                "evidence": evidence_by_hypothesis.get(hypothesis.id, []),
            }
        )

    reports = [_report_summary(report_date, report_dir, journal_root, events) for report_date, report_dir in report_dirs]
    latest_summary = reports[-1]
    context = _read_optional_json(latest_dir / "codex-context.json", warnings)
    latest_coverage = context.get("coverage", []) if isinstance(context, dict) else []

    status_counts = Counter(item["status"] for item in hypotheses)
    event_status_counts = Counter(item["status"] for item in events)
    mode_counts = Counter(item["verification_mode"] for item in hypotheses)
    subject_counts = Counter(item["subject"]["type"] for item in hypotheses)
    due = [item for item in hypotheses if item["due"]]

    return {
        "schema_version": DASHBOARD_SCHEMA_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "as_of": effective_date.isoformat(),
        "latest_report_date": latest_date.isoformat(),
        "report_count": len(reports),
        "warnings": warnings,
        "summary": {
            "active_hypotheses": sum(
                count for status, count in status_counts.items() if status not in TERMINAL_STATUSES
            ),
            "due_hypotheses": len(due),
            "overdue_hypotheses": sum(1 for item in due if item["overdue"]),
            "confirmed_hypotheses": status_counts["confirmed"],
            "falsified_hypotheses": status_counts["falsified"],
            "partially_confirmed_hypotheses": status_counts["partially_confirmed"],
            "latest_article_count": latest_summary["article_count"],
        },
        "status_counts": dict(sorted(status_counts.items())),
        "event_status_counts": dict(sorted(event_status_counts.items())),
        "mode_counts": dict(sorted(mode_counts.items())),
        "subject_counts": dict(sorted(subject_counts.items())),
        "latest": {
            "date": latest_summary["date"],
            "article_count": latest_summary["article_count"],
            "coverage": latest_coverage,
            "verification_counts": latest_summary["verification_counts"],
            "warnings": latest_summary["warnings"],
            "readiness": _readiness(latest_coverage, latest_summary["warnings"]),
            "journal": latest_summary["journal"],
        },
        "reports": reports,
        "hypotheses": hypotheses,
        "events": events,
    }


def build_dashboard(
    reports_root: Path,
    output_dir: Path,
    *,
    journal_root: Path | None = None,
    as_of: date | None = None,
) -> DashboardBuild:
    snapshot = build_dashboard_snapshot(
        reports_root,
        journal_root=journal_root,
        as_of=as_of,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_dir / "snapshot.json"
    html_path = output_dir / "index.html"
    write_json(snapshot_path, snapshot)
    html_path.write_text(render_dashboard(snapshot), encoding="utf-8")
    return DashboardBuild(snapshot_path=snapshot_path, html_path=html_path, snapshot=snapshot)


def render_dashboard(snapshot: dict) -> str:
    """Render a self-contained dashboard so it can be opened offline."""
    assets = Path(__file__).parent / "assets"
    css = (assets / "dashboard.css").read_text(encoding="utf-8")
    js = (assets / "dashboard.js").read_text(encoding="utf-8")
    data = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="本地只读投资假设与数据源复盘看板">
  <link rel="icon" href="data:,">
  <title>投资复盘看板</title>
  <style>{css}</style>
</head>
<body>
  <div id="app"></div>
  <script>window.__DASHBOARD_DATA__={data};</script>
  <script>{js}</script>
</body>
</html>
"""


def serve_dashboard(directory: Path, *, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    directory = directory.resolve()
    if not (directory / "index.html").exists():
        raise FileNotFoundError(f"dashboard index not found in {directory}; run dashboard build first")
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer((host, port), handler)
    address = f"http://{host}:{server.server_port}/"
    print(f"Dashboard: {address}")
    if open_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


def _has_report_artifact(path: Path) -> bool:
    return any((path / name).exists() for name in ("hypotheses.json", "codex-context.json", "daily-brief.md"))


def _read_optional_json(path: Path, warnings: list[str]) -> dict:
    if not path.exists():
        return {}
    try:
        payload = read_json(path)
    except (ContractError, OSError) as exc:
        warnings.append(f"无法读取 {path.name}: {exc}")
        return {}
    if not isinstance(payload, dict):
        warnings.append(f"{path.name} 不是 JSON 对象")
        return {}
    return payload


def _load_verification_events(report_dirs: list[tuple[date, Path]], warnings: list[str]) -> list[dict]:
    events: list[dict] = []
    for report_date, report_dir in report_dirs:
        payload = _read_optional_json(report_dir / "verification.json", warnings)
        for result in payload.get("results", []):
            if not isinstance(result, dict):
                continue
            events.append(
                {
                    "date": report_date.isoformat(),
                    "hypothesis_id": str(result.get("hypothesis_id") or ""),
                    "previous_status": str(result.get("previous_status") or ""),
                    "status": str(result.get("status") or ""),
                    "status_label": STATUS_LABELS.get(str(result.get("status") or ""), str(result.get("status") or "")),
                    "reason": str(result.get("reason") or ""),
                    "evidence_ids": [str(item) for item in result.get("evidence_ids", []) if item],
                    "deterministic": bool(result.get("deterministic", False)),
                }
            )
    return events


def _load_evidence(reports_root: Path, through_date: date, warnings: list[str]) -> list[dict]:
    try:
        return load_all_evidence(reports_root, through_date=through_date)
    except (ContractError, OSError) as exc:
        warnings.append(f"证据账本读取失败: {exc}")
        return []


def _report_summary(report_date: date, report_dir: Path, journal_root: Path, events: list[dict]) -> dict:
    context = _read_optional_json(report_dir / "codex-context.json", [])
    manifest = _read_optional_json(report_dir / "run-manifest.json", [])
    report_events = [event for event in events if event["date"] == report_date.isoformat()]
    warnings = [str(item) for item in manifest.get("warnings", []) if item]
    journal_path = journal_root / f"{report_date.year:04d}" / f"{report_date.month:02d}" / f"{report_date.isoformat()}.md"
    journal_exists = journal_path.exists()
    journal_filled = _journal_has_content(journal_path) if journal_exists else False
    return {
        "date": report_date.isoformat(),
        "article_count": int(context.get("article_count", 0) or 0),
        "coverage": context.get("coverage", []),
        "verification_counts": dict(Counter(event["status"] for event in report_events)),
        "warnings": warnings,
        "has_brief": (report_dir / "daily-brief.md").exists(),
        "has_manifest": (report_dir / "run-manifest.json").exists(),
        "journal": {"exists": journal_exists, "filled": journal_filled},
    }


def _readiness(coverage: list, warnings: list[str]) -> dict:
    rows = {str(row.get("source")): row for row in coverage if isinstance(row, dict)}
    sources = []
    blocking: list[str] = []
    for source in REQUIRED_SOURCES:
        row = rows.get(source, {})
        article_count = int(row.get("articles_total", 0) or 0)
        status = "ok" if article_count > 0 else "missing"
        if status != "ok":
            blocking.append(f"{source} 无有效文章")
        sources.append({"source": source, "status": status, "articles": article_count})
    if warnings:
        blocking.extend(warnings)
    return {"status": "blocked" if blocking else "ready", "sources": sources, "blocking": blocking}


def _journal_has_content(path: Path) -> bool:
    if not path.exists():
        return False
    ignored = ("#", ">", "---", "写作建议：")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(ignored):
            continue
        return True
    return False
