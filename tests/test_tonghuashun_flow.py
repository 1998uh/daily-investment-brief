from __future__ import annotations

from datetime import date

import pytest

from pipeline.capital_flow import CapitalFlowError, FallbackCapitalFlowProvider
from pipeline.tonghuashun_flow import TonghuashunSectorFlowProvider


def _page(name: str, code: str, net: str, page_info: str) -> str:
    return f"""
    <table class="m-table J-ajax-table"><tbody><tr>
      <td>1</td><td><a href="http://q.10jqka.com.cn/thshy/detail/code/{code}/">{name}</a></td>
      <td>1000.00</td><td>1.23%</td><td>12.50</td><td>10.00</td><td>{net}</td>
      <td>20</td><td>领涨股</td><td>5.00%</td><td>10.00</td>
    </tr></tbody></table><span class="page_info">{page_info}</span>
    """


def test_tonghuashun_provider_parses_all_pages_and_reuses_cache(monkeypatch, tmp_path):
    requested = date(2026, 7, 24)
    calls: list[str] = []

    def fake_get_html(url, **kwargs):
        calls.append(url)
        if "page/1/" in url:
            return _page("证券", "881157", "2.50", "1/2")
        return _page("工业金属", "881168", "-3.25", "2/2")

    monkeypatch.setattr("pipeline.tonghuashun_flow._get_html", fake_get_html)
    provider = TonghuashunSectorFlowProvider(
        tmp_path,
        retries=0,
        token_factory=lambda: "token",
        today_factory=lambda: requested,
    )

    rows = provider.fetch_sector_flow(requested)

    assert len(calls) == 2
    assert [row["sector_code"] for row in rows] == ["881157.TI", "881168.TI"]
    assert rows[0]["main_net"] is None
    assert rows[0]["total_net"] == 250_000_000
    assert rows[0]["source"] == "tonghuashun"

    monkeypatch.setattr(
        "pipeline.tonghuashun_flow._get_html",
        lambda *args, **kwargs: pytest.fail("same-day cache should avoid network"),
    )
    assert provider.fetch_sector_flow(requested) == rows


def test_tonghuashun_provider_does_not_backfill_historical_dates(tmp_path):
    provider = TonghuashunSectorFlowProvider(
        tmp_path,
        today_factory=lambda: date(2026, 7, 24),
    )

    with pytest.raises(CapitalFlowError, match="current-day only"):
        provider.fetch_sector_flow(date(2026, 7, 23))


def test_tonghuashun_provider_labels_weekend_data_with_latest_weekday(monkeypatch, tmp_path):
    requested = date(2026, 7, 25)
    monkeypatch.setattr(
        "pipeline.tonghuashun_flow._get_html",
        lambda *args, **kwargs: _page("证券", "881157", "2.50", "1/1"),
    )
    provider = TonghuashunSectorFlowProvider(
        tmp_path,
        retries=0,
        token_factory=lambda: "token",
        today_factory=lambda: requested,
    )

    rows = provider.fetch_sector_flow(requested)

    assert {row["trade_date"] for row in rows} == {"2026-07-24"}
    assert (tmp_path / "sectors" / "2026-07-24.json").exists()
    assert not (tmp_path / "sectors" / "2026-07-25.json").exists()


class _PrimaryProvider:
    def fetch_sector_flow(self, trade_date=None):
        raise CapitalFlowError("Eastmoney unavailable")

    def fetch_stock_flow(self, thscodes, trade_date=None):
        return [{"thscode": code, "source": "eastmoney"} for code in thscodes]

    def load_history(self, kind, *, before_or_equal):
        return [{"source": "primary"}]


class _SectorFallback:
    def fetch_sector_flow(self, trade_date=None):
        return [{"sector_name": "证券", "source": "tonghuashun"}]

    def fetch_stock_flow(self, thscodes, trade_date=None):
        raise AssertionError("stock flow must stay on the primary provider")

    def load_history(self, kind, *, before_or_equal):
        return [{"source": "fallback"}]


def test_composite_provider_falls_back_only_for_sector_flow():
    provider = FallbackCapitalFlowProvider(_PrimaryProvider(), _SectorFallback())

    assert provider.fetch_sector_flow()[0]["source"] == "tonghuashun"
    assert provider.fetch_stock_flow(["600519.SH"])[0]["source"] == "eastmoney"
    assert provider.load_history("sectors", before_or_equal=date(2026, 7, 24)) == [
        {"source": "fallback"}
    ]
    assert provider.diagnostics
    assert "fallback" in provider.source_label.lower()
