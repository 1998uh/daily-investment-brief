from __future__ import annotations

import pipeline.capital_flow_mcp as server


class HistoryProvider:
    def load_history(self, kind, *, before_or_equal):
        return [
            {
                "sector_code": "BK1200",
                "sector_name": "电力设备",
                "trade_date": "2026-07-23",
                "main_net": 100,
            },
            {
                "sector_code": "BK1200",
                "sector_name": "电力设备",
                "trade_date": "2026-07-22",
                "main_net": 50,
            },
        ]


def test_stock_tool_rejects_unbounded_input():
    result = server.get_stock_capital_flow([])

    assert result["code"] == 5001
    assert "1-50" in result["message"]


def test_history_tool_matches_sector_name_and_bounds_window(monkeypatch):
    monkeypatch.setattr(server, "_provider", HistoryProvider())

    result = server.get_capital_flow_history(
        kind="sectors",
        identifiers=["电力设备"],
        end_date="2026-07-23",
        window=1,
    )

    assert result["code"] == 0
    assert len(result["data"]["item"]) == 1
    assert result["data"]["item"][0]["trade_date"] == "2026-07-23"

