from datetime import date

from pipeline.market_metrics import (
    build_market_metrics,
    parse_baostock_rows,
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
    )

    assert result["as_of"] == "2026-11-13"
    assert result["turnover"]["latest"] == 1.65e12
    assert result["points"][-1]["margin"] == 2.3029e12
    assert all(point["date"] < "2026-11-14" for point in result["points"])


def test_missing_margin_warns():
    result = build_market_metrics(
        report_date=date(2026, 11, 14),
        turnover={date(2026, 11, 13): 1.65e12},
        margin={},
    )

    assert result["margin"]["latest"] is None
    assert any("两融" in item for item in result["warnings"])
