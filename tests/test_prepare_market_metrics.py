import json

from pipeline.hypothesis_workflow import _load_market_metrics


def test_loads_existing_snapshot(tmp_path):
    (tmp_path / "market-metrics.json").write_text(
        json.dumps({"available": True, "as_of": "2026-11-13"}), encoding="utf-8"
    )

    assert _load_market_metrics(tmp_path)["as_of"] == "2026-11-13"


def test_missing_snapshot_is_marked_unavailable(tmp_path):
    result = _load_market_metrics(tmp_path)

    assert result["available"] is False
    assert result["warnings"]
