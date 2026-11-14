"""Daily market-wide metrics for the report's trend section.

Turnover comes from BaoStock (Shanghai + Shenzhen indices); margin balance
comes from Eastmoney's public JSON endpoint.
"""
from __future__ import annotations

from bisect import bisect_right
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import date, timedelta
from io import StringIO
import statistics
from typing import Any

import requests


SHANGHAI_INDEX = "sh.000001"
SHENZHEN_INDEX = "sz.399001"
MARGIN_URL = (
    "https://datacenter-web.eastmoney.com/api/data/v1/get"
    "?reportName=RPTA_RZRQ_LSHJ&columns=ALL&sortColumns=DIM_DATE"
    "&sortTypes=-1&pageSize=30&pageNumber=1"
)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}


@dataclass(frozen=True)
class MarketPoint:
    date: date
    turnover: float | None
    margin_balance: float | None


def _float(value: Any) -> float | None:
    try:
        text = str(value).strip()
        if not text or text in {"-", "--", "None"}:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def parse_baostock_rows(
    sh_rows: list[list[str]], sz_rows: list[list[str]]
) -> dict[date, float]:
    """Sum Shanghai and Shenzhen turnover by trading day."""
    totals: dict[date, float] = {}
    for rows in (sh_rows, sz_rows):
        for row in rows:
            if len(row) < 2:
                continue
            amount = _float(row[1])
            if amount is None:
                continue
            try:
                day = date.fromisoformat(str(row[0])[:10])
            except ValueError:
                continue
            totals[day] = totals.get(day, 0.0) + amount
    return dict(sorted(totals.items()))


def parse_margin_payload(payload: dict[str, Any]) -> dict[date, float]:
    rows = ((payload or {}).get("result") or {}).get("data") or []
    margin: dict[date, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = _float(row.get("RZRQYE"))
        try:
            day = date.fromisoformat(str(row.get("DIM_DATE", ""))[:10])
        except ValueError:
            continue
        if value is not None:
            margin[day] = value
    return dict(sorted(margin.items()))


def _latest_on_or_before(values: dict[date, float], day: date) -> tuple[date, float] | None:
    dated = sorted(values)
    index = bisect_right(dated, day) - 1
    if index < 0:
        return None
    key = dated[index]
    return key, values[key]


def build_market_metrics(
    *,
    report_date: date,
    turnover: dict[date, float],
    margin: dict[date, float],
    days: int = 20,
) -> dict[str, Any]:
    """Align turnover and margin on the last trading day before the report date."""
    warnings: list[str] = []
    eligible = sorted(day for day in turnover if day < report_date)
    if not eligible:
        return {
            "available": False,
            "as_of": None,
            "window_days": days,
            "points": [],
            "turnover": {"latest": None, "prev": None, "avg20": None},
            "margin": {"latest": None, "latest_date": None},
            "warnings": ["成交额历史不可用"],
        }

    window = eligible[-max(1, days):]
    as_of = window[-1]
    points: list[MarketPoint] = []
    for day in window:
        lookup = _latest_on_or_before(margin, day)
        points.append(
            MarketPoint(
                date=day,
                turnover=turnover.get(day),
                margin_balance=lookup[1] if lookup else None,
            )
        )

    if not margin:
        warnings.append("两融数据不可用")

    margin_lookup = _latest_on_or_before(margin, as_of)
    latest_turnover = turnover.get(as_of)
    previous_turnover = turnover.get(window[-2]) if len(window) >= 2 else None
    values = [turnover[day] for day in window if day in turnover]
    avg20 = statistics.fmean(values) if values else None

    return {
        "available": True,
        "as_of": as_of.isoformat(),
        "window_days": days,
        "points": [
            {
                "date": point.date.isoformat(),
                "turnover": point.turnover,
                "margin": point.margin_balance,
            }
            for point in points
        ],
        "turnover": {
            "latest": latest_turnover,
            "prev": previous_turnover,
            "avg20": avg20,
        },
        "margin": {
            "latest": margin_lookup[1] if margin_lookup else None,
            "latest_date": margin_lookup[0].isoformat() if margin_lookup else None,
        },
        "warnings": warnings,
    }


def _baostock_rows(code: str, start: date, end: date) -> list[list[str]]:
    import baostock as bs

    with redirect_stdout(StringIO()):
        login = bs.login()
        if login.error_code != "0":
            raise RuntimeError(f"baostock login failed: {login.error_msg}")
        try:
            result = bs.query_history_k_data_plus(
                code,
                "date,amount",
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                frequency="d",
                adjustflag="3",
            )
            rows: list[list[str]] = []
            while result.next():
                rows.append(result.get_row_data())
            return rows
        finally:
            bs.logout()


def _fetch_margin() -> dict[date, float]:
    response = requests.get(MARGIN_URL, headers=_HEADERS, timeout=20)
    response.raise_for_status()
    return parse_margin_payload(response.json())


def fetch_market_inputs(*, report_date: date, days: int = 20) -> dict[str, Any]:
    """Fetch both sources; individual failures become warnings, never exceptions."""
    warnings: list[str] = []
    end = report_date - timedelta(days=1)
    start = end - timedelta(days=60)

    turnover: dict[date, float] = {}
    try:
        sh = _baostock_rows(SHANGHAI_INDEX, start, end)
        sz = _baostock_rows(SHENZHEN_INDEX, start, end)
        turnover = parse_baostock_rows(sh, sz)
    except Exception as exc:  # noqa: BLE001 - degrade instead of failing the report
        warnings.append(f"成交额历史获取失败: {type(exc).__name__}")

    margin: dict[date, float] = {}
    try:
        margin = _fetch_margin()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"两融数据获取失败: {type(exc).__name__}")

    return {
        "turnover": turnover,
        "margin": margin,
        "warnings": warnings,
    }
