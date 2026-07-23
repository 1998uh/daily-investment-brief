from __future__ import annotations

from datetime import date, timedelta
import json

import pytest

from pipeline.capital_daily import (
    HoldingsInputError,
    normalize_holdings,
    run_capital_daily,
)
from pipeline.capital_flow import CapitalFlowError, EastmoneyProvider


class FakeProvider:
    def __init__(self, *, fail_sector: bool = False):
        self.fail_sector = fail_sector
        self.as_of = date(2026, 7, 23)

    def fetch_sector_flow(self, trade_date=None):
        if self.fail_sector:
            raise CapitalFlowError("upstream unavailable")
        return [
            {
                "sector_code": "BK0478",
                "sector_name": "有色金属",
                "trade_date": self.as_of.isoformat(),
                "main_net": 1_000_000_000,
                "super_large_net": 600_000_000,
                "large_net": 400_000_000,
                "medium_net": -300_000_000,
                "small_net": -700_000_000,
                "total_net": None,
                "source": "fixture",
            }
        ]

    def fetch_stock_flow(self, thscodes, trade_date=None):
        return [
            {
                "thscode": code,
                "trade_date": self.as_of.isoformat(),
                "main_net": 200_000_000,
                "super_large_net": 120_000_000,
                "large_net": 80_000_000,
                "medium_net": -50_000_000,
                "small_net": -150_000_000,
                "total_net": None,
                "source": "fixture",
            }
            for code in thscodes
        ]

    def load_history(self, kind, *, before_or_equal):
        if kind == "sectors":
            return [
                {
                    "sector_code": "BK0478",
                    "sector_name": "有色金属",
                    "trade_date": (self.as_of - timedelta(days=offset)).isoformat(),
                    "main_net": 100_000_000,
                }
                for offset in range(1, 20)
            ]
        return []


def sample_payload():
    return {
        "holdings": [
            {
                "thscode": "601899.SH",
                "name": "紫金矿业",
                "asset_type": "a-share",
                "market_value": 60,
                "sector": "有色金属",
                "price_change_ratio_pct": 2.9,
            },
            {
                "thscode": "560860.SH",
                "name": "工业有色ETF",
                "asset_type": "fund-etf",
                "market_value": 15,
                "sector": "有色金属",
            },
            {
                "thscode": "CASH",
                "name": "现金",
                "asset_type": "cash",
                "market_value": 25,
            },
        ]
    }


def test_normalize_holdings_rejects_duplicates():
    payload = {
        "holdings": [
            {"thscode": "600519.SH", "asset_type": "a-share", "market_value": 1},
            {"thscode": "600519.SH", "asset_type": "a-share", "market_value": 2},
        ]
    }

    with pytest.raises(HoldingsInputError, match="duplicate holding code"):
        normalize_holdings(payload)


def test_missing_weight_and_unsupported_asset_are_explicit():
    holdings, warnings = normalize_holdings(
        [{"code": "00700.HK", "name": "腾讯控股", "asset_type": "hk-stock"}]
    )

    assert not holdings[0].supported
    assert any("只能做数量分析" in warning for warning in warnings)
    assert any("未覆盖" in warning for warning in warnings)
    assert any("缺少交易所后缀" in warning for warning in warnings)


def test_report_uses_real_weights_and_actual_history_windows(tmp_path):
    run = run_capital_daily(
        payload=sample_payload(),
        requested_date=date(2026, 7, 23),
        out_dir=tmp_path / "private",
        cache_dir=tmp_path / "cache",
        provider=FakeProvider(),
    )

    report = run.report_path.read_text(encoding="utf-8")
    assert run.ok
    assert "| 权益仓位 | 75.0% |" in report
    assert "+14.00亿（5日）" in report
    assert "+29.00亿（20日）" in report
    assert "仅主力口径" in report
    assert "现金（CASH）资产类型 'cash' 未覆盖" in report
    assert "本报告仅为数据分析，不构成投资建议" in report


def test_provider_failure_writes_diagnostic_report_and_returns_nonzero_state(tmp_path):
    run = run_capital_daily(
        payload=sample_payload(),
        requested_date=date(2026, 7, 23),
        out_dir=tmp_path / "private",
        cache_dir=tmp_path / "cache",
        provider=FakeProvider(fail_sector=True),
    )

    report = run.report_path.read_text(encoding="utf-8")
    assert not run.ok
    assert "板块资金流获取失败" in report
    assert "资金流数据不可用，未输出板块方向结论" in report
    assert "顺风持仓 | 0只" in report


def test_eastmoney_provider_parses_verified_contract(monkeypatch, tmp_path):
    responses = iter(
        [
            {
                "data": {
                    "diff": [
                        {
                            "f12": "600519",
                            "f62": -40131392,
                            "f66": -136909984,
                            "f72": 96778592,
                            "f78": 40356048,
                            "f84": -224671,
                            "f124": 1784787189,
                        }
                    ]
                }
            },
            {
                "data": {
                    "total": 1,
                    "diff": [
                        {
                            "f12": "BK1200",
                            "f14": "电力设备",
                            "f62": 8870149376,
                            "f66": 5561137664,
                            "f72": 3309011712,
                            "f78": -3162199808,
                            "f84": -5447801344,
                            "f124": 1784787189,
                        }
                    ]
                }
            },
        ]
    )

    monkeypatch.setattr("pipeline.capital_flow._get_json", lambda *args, **kwargs: next(responses))
    provider = EastmoneyProvider(tmp_path, retries=0)

    stock = provider.fetch_stock_flow(["600519.SH"])[0]
    sector = provider.fetch_sector_flow()[0]

    assert stock["main_net"] == -40131392
    assert stock["large_net"] == 96778592
    assert stock["super_large_net"] == -136909984
    assert sector["sector_name"] == "电力设备"
    assert sector["main_net"] == 8870149376
    assert sector["total_net"] is None
    cached_stock = json.loads((tmp_path / "stocks" / "2026-07-23.json").read_text(encoding="utf-8"))
    assert cached_stock[0]["thscode"] == "600519.SH"


def test_eastmoney_provider_reuses_same_day_cache(monkeypatch, tmp_path):
    stock_dir = tmp_path / "stocks"
    sector_dir = tmp_path / "sectors"
    stock_dir.mkdir(parents=True)
    sector_dir.mkdir(parents=True)
    stock_record = {
        "thscode": "600519.SH",
        "trade_date": "2026-07-23",
        "main_net": 1,
    }
    sector_record = {
        "sector_code": "BK1200",
        "sector_name": "电力设备",
        "trade_date": "2026-07-23",
        "main_net": 2,
    }
    (stock_dir / "2026-07-23.json").write_text(json.dumps([stock_record]), encoding="utf-8")
    (sector_dir / "2026-07-23.json").write_text(json.dumps([sector_record]), encoding="utf-8")
    monkeypatch.setattr(
        "pipeline.capital_flow._get_json",
        lambda *args, **kwargs: pytest.fail("same-day cache should avoid network"),
    )
    provider = EastmoneyProvider(tmp_path)

    assert provider.fetch_stock_flow(["600519.SH"], date(2026, 7, 23)) == [stock_record]
    assert provider.fetch_sector_flow(date(2026, 7, 23)) == [sector_record]
