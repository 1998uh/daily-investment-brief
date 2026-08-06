from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import re

from .hypothesis_models import (
    ContractError,
    Hypothesis,
    SCHEMA_VERSION,
    TERMINAL_STATUSES,
    parse_evidence_document,
    parse_hypotheses_document,
    parse_verification_document,
)
from .models import Article


DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class TrackedHypothesis:
    hypothesis: Hypothesis
    status: str = "pending"
    history: list[dict[str, Any]] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        payload = self.hypothesis.to_dict()
        payload["status"] = self.status
        payload["history"] = self.history
        return payload


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def dated_report_dirs(
    reports_root: Path,
    *,
    before_or_equal: date | None = None,
) -> list[tuple[date, Path]]:
    if not reports_root.exists():
        return []
    result: list[tuple[date, Path]] = []
    for path in reports_root.iterdir():
        if not path.is_dir() or not DATE_DIR_RE.match(path.name):
            continue
        parsed = date.fromisoformat(path.name)
        if before_or_equal is None or parsed <= before_or_equal:
            result.append((parsed, path))
    return sorted(result, key=lambda item: item[0])


def load_hypothesis_ledger(
    reports_root: Path,
    *,
    before_date: date | None = None,
    include_date: bool = False,
) -> dict[str, TrackedHypothesis]:
    ledger: dict[str, TrackedHypothesis] = {}
    limit = before_date if include_date else None
    for report_date, report_dir in dated_report_dirs(
        reports_root, before_or_equal=limit
    ):
        if before_date is not None:
            if include_date and report_date > before_date:
                continue
            if not include_date and report_date >= before_date:
                continue

        hypotheses_path = report_dir / "hypotheses.json"
        if hypotheses_path.exists():
            document_date, hypotheses = parse_hypotheses_document(read_json(hypotheses_path))
            if document_date != report_date:
                raise ContractError(
                    f"{hypotheses_path} report_date does not match directory"
                )
            for hypothesis in hypotheses:
                if hypothesis.id in ledger:
                    raise ContractError(f"duplicate historical hypothesis id: {hypothesis.id}")
                ledger[hypothesis.id] = TrackedHypothesis(hypothesis=hypothesis)

        verification_path = report_dir / "verification.json"
        if verification_path.exists():
            document_date, results = parse_verification_document(read_json(verification_path))
            if document_date != report_date:
                raise ContractError(
                    f"{verification_path} report_date does not match directory"
                )
            for result in results:
                hypothesis_id = result["hypothesis_id"]
                if hypothesis_id not in ledger:
                    raise ContractError(
                        f"verification references unknown hypothesis: {hypothesis_id}"
                    )
                tracked = ledger[hypothesis_id]
                if result["previous_status"] != tracked.status:
                    raise ContractError(
                        f"verification previous_status mismatch for {hypothesis_id}: "
                        f"expected {tracked.status}, got {result['previous_status']}"
                    )
                tracked.status = result["status"]
                tracked.history.append(
                    {
                        "report_date": report_date.isoformat(),
                        "status": result["status"],
                        "reason": result["reason"],
                    }
                )
    return ledger


def active_hypotheses(
    reports_root: Path,
    *,
    report_date: date,
) -> list[TrackedHypothesis]:
    ledger = load_hypothesis_ledger(reports_root, before_date=report_date)
    return [
        tracked
        for tracked in ledger.values()
        if tracked.status not in TERMINAL_STATUSES
    ]


def previous_report_date(reports_root: Path, report_date: date) -> date | None:
    candidates = [
        day
        for day, path in dated_report_dirs(reports_root)
        if day < report_date and (path / "daily-brief.md").exists()
    ]
    return max(candidates) if candidates else None


def load_all_evidence(
    reports_root: Path,
    *,
    through_date: date,
) -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for report_date, report_dir in dated_report_dirs(
        reports_root, before_or_equal=through_date
    ):
        path = report_dir / "evidence.json"
        if not path.exists():
            continue
        document_date, evidence = parse_evidence_document(read_json(path))
        if document_date != report_date:
            raise ContractError(f"{path} report_date does not match directory")
        for item in evidence:
            evidence_id = item["evidence_id"]
            if evidence_id in items and items[evidence_id] != item:
                raise ContractError(f"conflicting evidence id: {evidence_id}")
            items[evidence_id] = item
    return list(items.values())


def article_id(article: Article) -> str:
    seed = article.url.strip() or str(article.path).replace("\\", "/")
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"A-{digest}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hypotheses_document(report_date: date, hypotheses: Iterable[Hypothesis]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_date": report_date.isoformat(),
        "hypotheses": [hypothesis.to_dict() for hypothesis in hypotheses],
    }


def evidence_document(report_date: date, items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_date": report_date.isoformat(),
        "items": list(items),
    }


def clone_with_status(tracked: TrackedHypothesis) -> Hypothesis:
    return replace(tracked.hypothesis, status="pending")
