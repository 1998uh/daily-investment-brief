from __future__ import annotations

import pytest

from pipeline.hypothesis_models import (
    ContractError,
    Hypothesis,
    parse_evidence_document,
    parse_hypotheses_document,
)


def hypothesis_payload(**overrides):
    payload = {
        "id": "H-20260806-001",
        "created_date": "2026-08-06",
        "claim": "创业板连续两日收于3486点以上",
        "subject": {"type": "index", "name": "创业板指", "thscode": "399006.SZ"},
        "sources": [
            {
                "author": "作者",
                "article_id": "A-001",
                "url": "https://example.com/article",
                "quote": "观察创业板能否站稳3486点。",
            }
        ],
        "deadline": "2026-08-10",
        "verification_mode": "quantitative",
        "conditions": [
            {
                "type": "price_threshold",
                "entity": "399006.SZ",
                "field": "close",
                "operator": ">",
                "value": 3486,
                "unit": "point",
                "required_days": 2,
            }
        ],
        "falsification_conditions": [
            {
                "type": "price_threshold",
                "entity": "399006.SZ",
                "field": "close",
                "operator": "<",
                "value": 3400,
                "unit": "point",
                "required_days": 1,
            }
        ],
        "status": "pending",
    }
    payload.update(overrides)
    return payload


def test_hypothesis_roundtrip_validates_contract():
    hypothesis = Hypothesis.from_dict(hypothesis_payload())

    assert hypothesis.id == "H-20260806-001"
    assert hypothesis.subject.thscode == "399006.SZ"
    assert hypothesis.review_policy == "daily"
    assert hypothesis.to_dict()["conditions"][0]["required_days"] == 2


def test_hypothesis_id_date_must_match_created_date():
    with pytest.raises(ContractError, match="id date must match"):
        Hypothesis.from_dict(hypothesis_payload(created_date="2026-08-07"))


def test_quantitative_hypothesis_requires_support_and_falsification():
    with pytest.raises(ContractError, match="support and falsification"):
        Hypothesis.from_dict(hypothesis_payload(falsification_conditions=[]))


def test_manual_hypothesis_requires_reason():
    payload = hypothesis_payload(
        verification_mode="manual",
        conditions=[],
        falsification_conditions=[],
        manual_reason="",
    )
    with pytest.raises(ContractError, match="manual_reason"):
        Hypothesis.from_dict(payload)


def test_event_triggered_hypothesis_requires_trigger_terms():
    payload = hypothesis_payload(
        verification_mode="event",
        conditions=[],
        falsification_conditions=[],
        manual_reason="等待正式政策文件。",
        review_policy="event_triggered",
    )
    with pytest.raises(ContractError, match="trigger_terms"):
        Hypothesis.from_dict(payload)


def test_review_date_must_not_exceed_deadline():
    with pytest.raises(ContractError, match="between created_date and deadline"):
        Hypothesis.from_dict(
            hypothesis_payload(next_review_date="2026-08-11")
        )


def test_hypotheses_document_rejects_duplicate_ids():
    payload = {
        "schema_version": "1.0",
        "report_date": "2026-08-06",
        "hypotheses": [hypothesis_payload(), hypothesis_payload()],
    }
    with pytest.raises(ContractError, match="duplicate hypothesis id"):
        parse_hypotheses_document(payload)


def test_evidence_document_normalizes_market_values():
    payload = {
        "schema_version": "1.0",
        "report_date": "2026-08-07",
        "items": [
            {
                "evidence_id": "E-20260807-001",
                "hypothesis_id": "H-20260806-001",
                "evidence_type": "market_metric",
                "metric": "index.close",
                "entity": {"name": "创业板指", "thscode": "399006.sz"},
                "observed_date": "2026-08-07",
                "value": "3522.18",
                "unit": "point",
                "provider": "hithink-finance",
                "request_id": "request-1",
                "fetched_at": "2026-08-07T09:05:00+08:00",
            }
        ],
    }

    _, items = parse_evidence_document(payload)

    assert items[0]["value"] == 3522.18
    assert items[0]["entity"]["thscode"] == "399006.SZ"
