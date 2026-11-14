from datetime import date

from pipeline.market_metrics import (
    EtfSnapshot,
    build_market_metrics,
    parse_baostock_rows,
    parse_etf_pages,
    parse_margin_payload,
)


def test_baostock_rows_sum_sh_and_sz_by_date():
    sh = [["2026-11-12", "879537113560.40"], ["2026-11-13", "770614169983.60"]]
    sz = [["2026-11-12", "1052544765720.63"], ["2026-11-13", "885054041844.24"]]

    turnover = parse_baostock_rows(sh, sz)

    assert turnover[date(2026, 11, 13)] == 770614169983.60 + 885054041844.24


def test_parse_margin_payload_reads_rzrqye():
    payload = {
        "result": {
            "data": [
                {"DIM_DATE": "2026-11-12 00:00:00", "RZRQYE": 2302864590917},
                {"DIM_DATE": "2026-11-11 00:00:00", "RZRQYE": 2302294339469},
            ]
        }
    }

    margin = parse_margin_payload(payload)

    assert margin[date(2026, 11, 12)] == 2302864590917.0


def test_parse_etf_pages_sums_and_returns_top_five():
    pages = [
        {
            "data": {
                "diff": [
                    {"f12": "512980", "f14": "传媒ETF", "f62": 215777366, "f124": 1794557520},
                    {"f12": "511990", "f14": "华宝添益ETF", "f62": 495963040, "f124": 1794557520},
                    {"f12": "000001", "f14": "空值", "f62": "-", "f124": 1794557520},
                ]
            }
        }
    ]

    snapshot = parse_etf_pages(pages)

    assert snapshot.net_flow == 215777366 + 495963040
    assert snapshot.top[0]["code"] == "511990"


def test_build_clamps_to_the_day_before_report_date():
    turnover = {
        date(2026, 11, 12): 1.9e12,
        date(2026, 11, 13): 1.65e12,
        date(2026, 11, 14): 9.9e12,
    }
    margin = {date(2026, 11, 12): 2.3029e12}

    result = build_market_metrics(
        report_date=date(2026, 11, 14),
        turnover=turnover,
        margin=margin,
        etf_store={},
        etf_snapshot=None,
    )

    assert result["as_of"] == "2026-11-13"
    assert result["turnover"]["latest"] == 1.65e12
    assert all(point["date"] < "2026-11-14" for point in result["points"])


def test_partial_etf_store_is_not_used_as_full():
    turnover = {date(2026, 11, 13): 1.65e12}
    store = {"2026-11-13": {"net_flow": 1.0, "partial": True}}

    result = build_market_metrics(
        report_date=date(2026, 11, 14),
        turnover=turnover,
        margin={},
        etf_store=store,
        etf_snapshot=None,
    )

    assert result["etf_flow"]["latest"] is None
    assert any("不完整" in item for item in result["warnings"])


def test_full_etf_store_is_used():
    turnover = {date(2026, 11, 13): 1.65e12}
    store = {"2026-11-13": {"net_flow": 1.0, "partial": False}}

    result = build_market_metrics(
        report_date=date(2026, 11, 14),
        turnover=turnover,
        margin={},
        etf_store=store,
        etf_snapshot=None,
    )

    assert result["etf_flow"]["latest"] == 1.0


def test_etf_snapshot_after_as_of_is_ignored_and_warned():
    turnover = {date(2026, 11, 13): 1.65e12}
    snapshot = EtfSnapshot(date=date(2026, 11, 14), net_flow=8.8e9, top=[])

    result = build_market_metrics(
        report_date=date(2026, 11, 15),
        turnover=turnover,
        margin={},
        etf_store={},
        etf_snapshot=snapshot,
    )

    assert result["etf_flow"]["latest"] is None
    assert any("ETF" in item for item in result["warnings"])
