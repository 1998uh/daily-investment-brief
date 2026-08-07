from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping
import re


SCHEMA_VERSION = "1.0"

HYPOTHESIS_ID_RE = re.compile(r"^H-(\d{8})-(\d{3,})$")
EVIDENCE_ID_RE = re.compile(r"^E-(\d{8})-(\d{3,})$")

VERIFICATION_MODES = {"quantitative", "event", "hybrid", "manual"}
REVIEW_POLICIES = {"daily", "weekly", "event_triggered", "deadline_only"}
HYPOTHESIS_STATUSES = {
    "pending",
    "partially_confirmed",
    "confirmed",
    "falsified",
    "inconclusive",
    "unavailable",
    "expired",
}
TERMINAL_STATUSES = {"confirmed", "falsified", "inconclusive", "expired"}
RULE_TYPES = {
    "price_threshold",
    "relative_return",
    "turnover_threshold",
    "capital_flow",
}
OPERATORS = {">", ">=", "<", "<=", "==", "!="}
EVIDENCE_TYPES = {"market_metric", "event", "manual_resolution"}
SOURCE_LEVELS = {"official", "authoritative", "media", "social"}


class ContractError(ValueError):
    """Raised when a hypothesis workflow artifact violates its contract."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object")
    return value


def _required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ContractError(f"{label} is required")
    return text


def _optional_text(value: Any) -> str:
    return str(value or "").strip()


def _iso_date(value: Any, label: str) -> date:
    text = _required_text(value, label)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ContractError(f"{label} must be YYYY-MM-DD: {text}") from exc


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ContractError(f"{label} must be numeric")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{label} must be numeric") from exc


def _positive_int(value: Any, label: str, *, default: int = 1) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{label} must be an integer") from exc
    if parsed < 1:
        raise ContractError(f"{label} must be >= 1")
    return parsed


@dataclass(frozen=True)
class Subject:
    type: str
    name: str
    thscode: str = ""

    @classmethod
    def from_dict(cls, payload: Any) -> "Subject":
        data = _mapping(payload, "subject")
        return cls(
            type=_required_text(data.get("type"), "subject.type"),
            name=_required_text(data.get("name"), "subject.name"),
            thscode=_optional_text(data.get("thscode")).upper(),
        )

    @property
    def key(self) -> str:
        return self.thscode or self.name

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "name": self.name, "thscode": self.thscode}


@dataclass(frozen=True)
class SourceReference:
    author: str
    article_id: str
    url: str
    quote: str

    @classmethod
    def from_dict(cls, payload: Any) -> "SourceReference":
        data = _mapping(payload, "source reference")
        reference = cls(
            author=_required_text(data.get("author"), "source.author"),
            article_id=_optional_text(data.get("article_id")),
            url=_optional_text(data.get("url")),
            quote=_required_text(data.get("quote"), "source.quote"),
        )
        if not reference.article_id and not reference.url:
            raise ContractError("source requires article_id or url")
        return reference

    def to_dict(self) -> dict[str, Any]:
        return {
            "author": self.author,
            "article_id": self.article_id,
            "url": self.url,
            "quote": self.quote,
        }


@dataclass(frozen=True)
class Condition:
    type: str
    entity: str
    operator: str
    value: float
    unit: str
    field: str = ""
    required_days: int = 1
    benchmark: str = ""
    window_trading_days: int = 0

    @classmethod
    def from_dict(cls, payload: Any, label: str = "condition") -> "Condition":
        data = _mapping(payload, label)
        rule_type = _required_text(data.get("type"), f"{label}.type")
        if rule_type not in RULE_TYPES:
            raise ContractError(f"unsupported {label}.type: {rule_type}")
        operator = _required_text(data.get("operator"), f"{label}.operator")
        if operator not in OPERATORS:
            raise ContractError(f"unsupported {label}.operator: {operator}")
        benchmark = _optional_text(data.get("benchmark")).upper()
        if rule_type == "relative_return" and not benchmark:
            raise ContractError(f"{label}.benchmark is required for relative_return")
        return cls(
            type=rule_type,
            entity=_required_text(data.get("entity"), f"{label}.entity").upper(),
            field=_optional_text(data.get("field")),
            operator=operator,
            value=_number(data.get("value"), f"{label}.value"),
            unit=_required_text(data.get("unit"), f"{label}.unit"),
            required_days=_positive_int(
                data.get("required_days"), f"{label}.required_days"
            ),
            benchmark=benchmark,
            window_trading_days=(
                _positive_int(
                    data.get("window_trading_days"),
                    f"{label}.window_trading_days",
                )
                if rule_type == "relative_return"
                else 0
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": self.type,
            "entity": self.entity,
            "operator": self.operator,
            "value": self.value,
            "unit": self.unit,
            "required_days": self.required_days,
        }
        if self.field:
            result["field"] = self.field
        if self.benchmark:
            result["benchmark"] = self.benchmark
        if self.window_trading_days:
            result["window_trading_days"] = self.window_trading_days
        return result


@dataclass(frozen=True)
class Hypothesis:
    id: str
    created_date: date
    claim: str
    subject: Subject
    sources: tuple[SourceReference, ...]
    deadline: date
    verification_mode: str
    conditions: tuple[Condition, ...]
    falsification_conditions: tuple[Condition, ...]
    status: str = "pending"
    manual_reason: str = ""
    review_policy: str = ""
    next_review_date: date | None = None
    trigger_terms: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: Any) -> "Hypothesis":
        data = _mapping(payload, "hypothesis")
        hypothesis_id = _required_text(data.get("id"), "hypothesis.id")
        match = HYPOTHESIS_ID_RE.match(hypothesis_id)
        if not match:
            raise ContractError(
                f"hypothesis.id must match H-YYYYMMDD-NNN: {hypothesis_id}"
            )
        created_date = _iso_date(data.get("created_date"), "hypothesis.created_date")
        if match.group(1) != created_date.strftime("%Y%m%d"):
            raise ContractError("hypothesis.id date must match created_date")
        deadline = _iso_date(data.get("deadline"), "hypothesis.deadline")
        if deadline < created_date:
            raise ContractError("hypothesis.deadline cannot be before created_date")
        verification_mode = _required_text(
            data.get("verification_mode"), "hypothesis.verification_mode"
        )
        if verification_mode not in VERIFICATION_MODES:
            raise ContractError(f"unsupported verification_mode: {verification_mode}")
        status = _required_text(data.get("status", "pending"), "hypothesis.status")
        if status not in HYPOTHESIS_STATUSES:
            raise ContractError(f"unsupported hypothesis.status: {status}")
        if status != "pending":
            raise ContractError("new hypotheses must start with status=pending")

        raw_sources = data.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise ContractError("hypothesis.sources must be a non-empty list")
        raw_conditions = data.get("conditions", [])
        raw_falsification = data.get("falsification_conditions", [])
        if not isinstance(raw_conditions, list) or not isinstance(raw_falsification, list):
            raise ContractError("hypothesis conditions must be lists")

        subject = Subject.from_dict(data.get("subject"))
        manual_reason = _optional_text(data.get("manual_reason"))
        review_policy = _optional_text(data.get("review_policy")) or {
            "quantitative": "daily",
            "event": "weekly",
            "hybrid": "weekly",
            "manual": "deadline_only",
        }[verification_mode]
        if review_policy not in REVIEW_POLICIES:
            raise ContractError(f"unsupported review_policy: {review_policy}")
        next_review_date = (
            _iso_date(data.get("next_review_date"), "hypothesis.next_review_date")
            if data.get("next_review_date") not in (None, "")
            else None
        )
        if next_review_date and not created_date <= next_review_date <= deadline:
            raise ContractError(
                "hypothesis.next_review_date must be between created_date and deadline"
            )
        raw_trigger_terms = data.get("trigger_terms", [])
        if not isinstance(raw_trigger_terms, list):
            raise ContractError("hypothesis.trigger_terms must be a list")
        trigger_terms = tuple(
            text
            for item in raw_trigger_terms
            if (text := _optional_text(item))
        )
        if review_policy == "event_triggered" and not trigger_terms:
            raise ContractError(
                "event_triggered hypothesis requires non-empty trigger_terms"
            )
        conditions = tuple(
            Condition.from_dict(item, f"conditions[{index}]")
            for index, item in enumerate(raw_conditions)
        )
        falsification = tuple(
            Condition.from_dict(item, f"falsification_conditions[{index}]")
            for index, item in enumerate(raw_falsification)
        )

        if verification_mode == "quantitative":
            if not subject.thscode and subject.name.upper() != "A_SHARE":
                raise ContractError(
                    "quantitative hypothesis subject requires thscode or A_SHARE"
                )
            if not conditions or not falsification:
                raise ContractError(
                    "quantitative hypothesis requires support and falsification conditions"
                )
        if verification_mode in {"event", "hybrid"} and not (
            conditions or manual_reason
        ):
            raise ContractError(
                f"{verification_mode} hypothesis requires conditions or manual_reason"
            )
        if verification_mode == "manual" and not manual_reason:
            raise ContractError("manual hypothesis requires manual_reason")

        return cls(
            id=hypothesis_id,
            created_date=created_date,
            claim=_required_text(data.get("claim"), "hypothesis.claim"),
            subject=subject,
            sources=tuple(SourceReference.from_dict(item) for item in raw_sources),
            deadline=deadline,
            verification_mode=verification_mode,
            conditions=conditions,
            falsification_conditions=falsification,
            status=status,
            manual_reason=manual_reason,
            review_policy=review_policy,
            next_review_date=next_review_date,
            trigger_terms=trigger_terms,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "created_date": self.created_date.isoformat(),
            "claim": self.claim,
            "subject": self.subject.to_dict(),
            "sources": [source.to_dict() for source in self.sources],
            "deadline": self.deadline.isoformat(),
            "verification_mode": self.verification_mode,
            "conditions": [condition.to_dict() for condition in self.conditions],
            "falsification_conditions": [
                condition.to_dict() for condition in self.falsification_conditions
            ],
            "review_policy": self.review_policy,
            "status": self.status,
        }
        if self.manual_reason:
            result["manual_reason"] = self.manual_reason
        if self.next_review_date:
            result["next_review_date"] = self.next_review_date.isoformat()
        if self.trigger_terms:
            result["trigger_terms"] = list(self.trigger_terms)
        return result


def parse_hypotheses_document(payload: Any) -> tuple[date, list[Hypothesis]]:
    data = _mapping(payload, "hypotheses document")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(
            f"unsupported hypotheses schema_version: {data.get('schema_version')!r}"
        )
    report_date = _iso_date(data.get("report_date"), "report_date")
    raw_items = data.get("hypotheses")
    if not isinstance(raw_items, list):
        raise ContractError("hypotheses must be a list")
    hypotheses = [Hypothesis.from_dict(item) for item in raw_items]
    seen: set[str] = set()
    for hypothesis in hypotheses:
        if hypothesis.id in seen:
            raise ContractError(f"duplicate hypothesis id: {hypothesis.id}")
        seen.add(hypothesis.id)
        if hypothesis.created_date != report_date:
            raise ContractError(
                f"{hypothesis.id} created_date must match document report_date"
            )
    return report_date, hypotheses


def parse_evidence_document(payload: Any) -> tuple[date, list[dict[str, Any]]]:
    data = _mapping(payload, "evidence document")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(
            f"unsupported evidence schema_version: {data.get('schema_version')!r}"
        )
    report_date = _iso_date(data.get("report_date"), "report_date")
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise ContractError("evidence items must be a list")

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_items):
        item = dict(_mapping(raw, f"evidence.items[{index}]"))
        evidence_id = _required_text(item.get("evidence_id"), "evidence_id")
        if not EVIDENCE_ID_RE.match(evidence_id):
            raise ContractError(
                f"evidence_id must match E-YYYYMMDD-NNN: {evidence_id}"
            )
        if evidence_id in seen:
            raise ContractError(f"duplicate evidence_id: {evidence_id}")
        seen.add(evidence_id)
        item["hypothesis_id"] = _required_text(
            item.get("hypothesis_id"), "evidence.hypothesis_id"
        )
        evidence_type = _required_text(item.get("evidence_type"), "evidence_type")
        if evidence_type not in EVIDENCE_TYPES:
            raise ContractError(f"unsupported evidence_type: {evidence_type}")

        if evidence_type == "market_metric":
            item["metric"] = _required_text(item.get("metric"), "evidence.metric")
            entity = _mapping(item.get("entity"), "evidence.entity")
            entity_name = _required_text(entity.get("name"), "evidence.entity.name")
            entity_code = _optional_text(entity.get("thscode")).upper()
            item["entity"] = {"name": entity_name, "thscode": entity_code}
            item["observed_date"] = _iso_date(
                item.get("observed_date"), "evidence.observed_date"
            ).isoformat()
            item["value"] = _number(item.get("value"), "evidence.value")
            item["unit"] = _required_text(item.get("unit"), "evidence.unit")
            item["provider"] = _required_text(
                item.get("provider"), "evidence.provider"
            )
        elif evidence_type == "event":
            item["title"] = _required_text(item.get("title"), "evidence.title")
            item["published_at"] = _required_text(
                item.get("published_at"), "evidence.published_at"
            )
            level = _required_text(item.get("source_level"), "evidence.source_level")
            if level not in SOURCE_LEVELS:
                raise ContractError(f"unsupported source_level: {level}")
            item["source_level"] = level
            item["publisher"] = _required_text(
                item.get("publisher"), "evidence.publisher"
            )
            item["url"] = _required_text(item.get("url"), "evidence.url")
            item["quote"] = _required_text(item.get("quote"), "evidence.quote")
            if not isinstance(item.get("supports"), bool):
                raise ContractError("event evidence supports must be boolean")
        else:
            resolved_status = _required_text(
                item.get("resolved_status"), "evidence.resolved_status"
            )
            if resolved_status not in {
                "confirmed",
                "falsified",
                "inconclusive",
            }:
                raise ContractError(
                    "manual_resolution status must be confirmed, falsified, or inconclusive"
                )
            item["resolved_status"] = resolved_status
            item["note"] = _required_text(item.get("note"), "evidence.note")
            item["resolved_by"] = _required_text(
                item.get("resolved_by"), "evidence.resolved_by"
            )

        item["evidence_id"] = evidence_id
        item["evidence_type"] = evidence_type
        item["fetched_at"] = _required_text(item.get("fetched_at"), "evidence.fetched_at")
        items.append(item)
    return report_date, items


def parse_verification_document(payload: Any) -> tuple[date, list[dict[str, Any]]]:
    data = _mapping(payload, "verification document")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(
            f"unsupported verification schema_version: {data.get('schema_version')!r}"
        )
    report_date = _iso_date(data.get("report_date"), "report_date")
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        raise ContractError("verification results must be a list")

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_results):
        result = dict(_mapping(raw, f"verification.results[{index}]"))
        hypothesis_id = _required_text(result.get("hypothesis_id"), "hypothesis_id")
        if hypothesis_id in seen:
            raise ContractError(f"duplicate verification result: {hypothesis_id}")
        seen.add(hypothesis_id)
        previous_status = _required_text(
            result.get("previous_status"), "previous_status"
        )
        status = _required_text(result.get("status"), "status")
        if previous_status not in HYPOTHESIS_STATUSES or status not in HYPOTHESIS_STATUSES:
            raise ContractError(f"unsupported verification status for {hypothesis_id}")
        if not isinstance(result.get("deterministic"), bool):
            raise ContractError("verification deterministic must be boolean")
        if not isinstance(result.get("conditions", []), list) or not isinstance(
            result.get("falsification_conditions", []), list
        ):
            raise ContractError("verification condition results must be lists")
        if not isinstance(result.get("evidence_ids", []), list) or not all(
            isinstance(item, str) and item.strip()
            for item in result.get("evidence_ids", [])
        ):
            raise ContractError("verification evidence_ids must be a list of strings")
        result["hypothesis_id"] = hypothesis_id
        result["previous_status"] = previous_status
        result["status"] = status
        result["reason"] = _required_text(result.get("reason"), "verification.reason")
        result["evaluated_at"] = _required_text(
            result.get("evaluated_at"), "verification.evaluated_at"
        )
        result["evidence_ids"] = [
            item.strip() for item in result.get("evidence_ids", [])
        ]
        results.append(result)
    return report_date, results
