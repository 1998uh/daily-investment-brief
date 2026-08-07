from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .html import wrap_html
from .hypothesis_io import (
    file_sha256,
    load_all_evidence,
    load_hypothesis_ledger,
    read_json,
    write_json,
)
from .hypothesis_models import (
    ContractError,
    SCHEMA_VERSION,
    parse_evidence_document,
    parse_hypotheses_document,
    parse_verification_document,
)


MIN_NEW_HYPOTHESES = 2
MAX_NEW_HYPOTHESES = 4


@dataclass(frozen=True)
class ValidationReport:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    html_path: Path | None = None
    manifest_path: Path | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_report_bundle(
    *,
    report_date: date,
    out_dir: Path,
    reports_root: Path,
    strict: bool = False,
) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    md_path = out_dir / "daily-brief.md"
    hypotheses_path = out_dir / "hypotheses.json"
    context_path = out_dir / "codex-context.json"
    article_pack_path = out_dir / "article-pack.md"
    article_index_path = out_dir / "article-index.jsonl"
    evidence_tasks_path = out_dir / "evidence-tasks.json"
    evidence_path = out_dir / "evidence.json"
    verification_path = out_dir / "verification.json"
    context_payload: dict[str, Any] = {}

    if not md_path.exists():
        errors.append(f"missing daily brief: {md_path}")
    if not hypotheses_path.exists():
        errors.append(f"missing hypotheses file: {hypotheses_path}")

    optional_paths = (context_path, evidence_path, verification_path)
    for path in optional_paths:
        if not path.exists():
            message = f"missing workflow artifact: {path}"
            (errors if strict else warnings).append(message)

    if context_path.exists():
        try:
            context_payload = read_json(context_path)
            if not isinstance(context_payload, dict):
                raise ContractError("codex-context.json must contain an object")
            for key, path in (
                ("article_pack", article_pack_path),
                ("article_index", article_index_path),
                ("evidence_tasks", evidence_tasks_path),
            ):
                if context_payload.get(key) and not path.exists():
                    errors.append(f"missing context artifact: {path}")
        except ContractError as exc:
            errors.append(str(exc))

    hypotheses = []
    verification_results: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []
    if hypotheses_path.exists():
        try:
            hypotheses_payload = read_json(hypotheses_path)
            document_date, hypotheses = parse_hypotheses_document(hypotheses_payload)
            if document_date != report_date:
                errors.append("hypotheses report_date does not match requested date")
            if not MIN_NEW_HYPOTHESES <= len(hypotheses) <= MAX_NEW_HYPOTHESES:
                errors.append(
                    "hypotheses.json must contain 2-4 new hypotheses; "
                    f"found {len(hypotheses)}"
                )
            if context_payload.get("article_pack"):
                for index, item in enumerate(hypotheses_payload.get("hypotheses", [])):
                    if not str(item.get("review_policy") or "").strip():
                        errors.append(
                            f"hypotheses[{index}].review_policy is required "
                            "for token-efficient runtime"
                        )
        except ContractError as exc:
            errors.append(str(exc))
    if evidence_path.exists():
        try:
            document_date, evidence_items = parse_evidence_document(read_json(evidence_path))
            if document_date != report_date:
                errors.append("evidence report_date does not match requested date")
        except ContractError as exc:
            errors.append(str(exc))
    if verification_path.exists():
        try:
            document_date, verification_results = parse_verification_document(
                read_json(verification_path)
            )
            if document_date != report_date:
                errors.append("verification report_date does not match requested date")
        except ContractError as exc:
            errors.append(str(exc))

    try:
        previous_ledger = load_hypothesis_ledger(reports_root, before_date=report_date)
        for hypothesis in hypotheses:
            if hypothesis.id in previous_ledger:
                errors.append(f"hypothesis id already exists in history: {hypothesis.id}")
    except ContractError as exc:
        errors.append(str(exc))

    markdown = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    for hypothesis in hypotheses:
        if hypothesis.id not in markdown:
            errors.append(f"daily brief does not reference new hypothesis {hypothesis.id}")
    for result in verification_results:
        if result["hypothesis_id"] not in markdown:
            errors.append(
                f"daily brief does not reference verification {result['hypothesis_id']}"
            )

    try:
        all_evidence = load_all_evidence(reports_root, through_date=report_date)
    except ContractError as exc:
        errors.append(str(exc))
        all_evidence = []
    evidence_ids = {item["evidence_id"] for item in all_evidence}
    evidence_ids.update(item["evidence_id"] for item in evidence_items)
    for result in verification_results:
        missing = set(result.get("evidence_ids", [])) - evidence_ids
        if missing:
            errors.append(
                f"verification {result['hypothesis_id']} references missing evidence: "
                + ", ".join(sorted(missing))
            )
        if result["status"] in {"confirmed", "falsified"} and not result.get(
            "evidence_ids"
        ):
            errors.append(
                f"verification {result['hypothesis_id']} has terminal status without evidence"
            )

    if errors:
        return ValidationReport(tuple(errors), tuple(warnings))

    html_path = out_dir / "daily-brief.html"
    html_path.write_text(wrap_html(markdown, "每日投资简报"), encoding="utf-8")
    manifest_path = out_dir / "run-manifest.json"
    manifest = _build_manifest(
        report_date=report_date,
        out_dir=out_dir,
        evidence_items=evidence_items,
        warnings=warnings,
    )
    write_json(manifest_path, manifest)
    return ValidationReport(
        tuple(errors), tuple(warnings), html_path=html_path, manifest_path=manifest_path
    )


def _build_manifest(
    *,
    report_date: date,
    out_dir: Path,
    evidence_items: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    names = [
        "codex-context.json",
        "article-pack.md",
        "article-index.jsonl",
        "evidence-tasks.json",
        "evidence.json",
        "verification.json",
        "hypotheses.json",
        "daily-brief.md",
        "daily-brief.html",
    ]
    files = []
    for name in names:
        path = out_dir / name
        if path.exists():
            files.append(
                {
                    "name": name,
                    "sha256": file_sha256(path),
                    "size": path.stat().st_size,
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_date": report_date.isoformat(),
        "workflow": "codex-native-hypothesis-tracking",
        "providers": sorted(
            {
                str(item.get("provider") or item.get("publisher") or "").strip()
                for item in evidence_items
                if str(item.get("provider") or item.get("publisher") or "").strip()
            }
        ),
        "request_ids": sorted(
            {
                str(item.get("request_id", "")).strip()
                for item in evidence_items
                if str(item.get("request_id", "")).strip()
            }
        ),
        "warnings": warnings,
        "files": files,
        "validated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
