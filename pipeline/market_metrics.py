"""Daily market-wide metrics for the report's trend section.

Turnover comes from BaoStock (Shanghai + Shenzhen indices), margin balance and
ETF main-force net inflow come from Eastmoney's public JSON endpoints.
"""
from __future__ import annotations

from bisect import bisect_right
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import StringIO
import json
from pathlib import Path
import statistics
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .config import ROOT


SHANGHAI_INDEX = "sh.000001"
SHENZHEN_INDEX = "sz.399001"
MARGIN_URL = (
    "https://datacenter-web.eastmoney.com/api/data/v1/get"
    "?reportName=RPTA_RZRQ_LSHJ&columns=ALL&sortColumns=DIM_DATE"
    "&sortTypes=-1&pageSize=30&pageNumber=1"
)
ETF_URL = (
    "https://push2.eastmoney.com/api/qt/clist/get"
    "?pn={page}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f62"
    "&fs=b:MK0021,b:MK0022,b:MK0023,b:MK0024&fields=f12,f14,f62,f124"
)
ETF_STORE_PATH = ROOT / "data" / "market-metrics" / "etf-flow.json"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}


@dataclass(frozen=True)
class MarketPoint:
    date: date
    turnover: float | None
    margin_balance: float | None
    etf_net_flow: float | None


@dataclass(frozen=True)
class EtfSnapshot:
    date: date
    net_flow: float
    top: list[dict[str, Any]]


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


def parse_etf_pages(pages: list[dict[str, Any]]) -> EtfSnapshot:
    """Sum every ETF's main-force net inflow and keep the top five."""
    total = 0.0
    entries: list[dict[str, Any]] = []
    snapshot_ts: int | None = None
    for payload in pages:
        for row in ((payload or {}).get("data") or {}).get("diff") or []:
            if not isinstance(row, dict):
                continue
            flow = _float(row.get("f62"))
            if flow is None:
                continue
            total += flow
            entries.append(
                {
                    "code": str(row.get("f12") or ""),
                    "name": str(row.get("f14") or ""),
                    "flow": flow,
                }
            )
            if snapshot_ts is None:
                ts = _float(row.get("f124"))
                if ts:
                    snapshot_ts = int(ts)
    snapshot_date = (
        datetime.fromtimestamp(snapshot_ts, tz=ZoneInfo("Asia/Shanghai")).date()
        if snapshot_ts
        else date.today()
    )
    entries.sort(key=lambda item: item["flow"], reverse=True)
    return EtfSnapshot(date=snapshot_date, net_flow=total, top=entries[:5])


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
    etf_store: dict[str, dict],
    etf_snapshot: EtfSnapshot | None,
    days: int = 20,
) -> dict[str, Any]:
    """Align the three series on the last trading day before the report date."""
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
            "etf_flow": {"latest": None, "date": None, "top": []},
            "warnings": ["成交额历史不可用"],
        }

    window = eligible[-max(1, days):]
    as_of = window[-1]
    points: list[MarketPoint] = []
    etf_dates: set[str] = set()

    for day in window:
        margin_value = None
        lookup = _latest_on_or_before(margin, day)
        if lookup:
            margin_value = lookup[1]
        etf_value = None
        stored = etf_store.get(day.isoformat())
        if isinstance(stored, dict):
            etf_value = _float(stored.get("net_flow"))
            etf_dates.add(day.isoformat())
        elif etf_snapshot and etf_snapshot.date == day:
            etf_value = etf_snapshot.net_flow
            etf_dates.add(day.isoformat())
        points.append(
            MarketPoint(
                date=day,
                turnover=turnover.get(day),
                margin_balance=margin_value,
                etf_net_flow=etf_value,
            )
        )

    if not margin:
        warnings.append("两融数据不可用")
    if len(etf_dates) < len(window):
        warnings.append("ETF 历史数据不完整")

    margin_lookup = _latest_on_or_before(margin, as_of)
    etf_latest = None
    etf_date = None
    etf_top: list[dict[str, Any]] = []
    as_of_iso = as_of.isoformat()
    stored = etf_store.get(as_of_iso)
    if isinstance(stored, dict):
        etf_latest = _float(stored.get("net_flow"))
        etf_date = as_of_iso
        etf_top = stored.get("top") or []
    elif etf_snapshot and etf_snapshot.date == as_of:
        etf_latest = etf_snapshot.net_flow
        etf_date = as_of_iso
        etf_top = etf_snapshot.top
    elif etf_snapshot and etf_snapshot.date > as_of:
        warnings.append("ETF 快照日期晚于行情日，已忽略")

    latest_turnover = turnover.get(as_of)
    previous_turnover = turnover.get(window[-2]) if len(window) >= 2 else None
    values = [turnover[day] for day in window if day in turnover]
    avg20 = statistics.fmean(values) if values else None

    return {
        "available": True,
        "as_of": as_of_iso,
        "window_days": days,
        "points": [
            {
                "date": point.date.isoformat(),
                "turnover": point.turnover,
                "margin": point.margin_balance,
                "etf_net_flow": point.etf_net_flow,
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
        "etf_flow": {"latest": etf_latest, "date": etf_date, "top": etf_top},
        "warnings": warnings,
    }


def load_etf_store(path: Path = ETF_STORE_PATH) -> dict[str, dict]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_etf_store(store: dict[str, dict], path: Path = ETF_STORE_PATH) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


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


def _fetch_etf_pages(max_pages: int = 30) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        response = requests.get(ETF_URL.format(page=page), headers=_HEADERS, timeout=20)
        response.raise_for_status()
        payload = response.json()
        rows = ((payload or {}).get("data") or {}).get("diff") or []
        pages.append(payload)
        if len(rows) < 100:
            break
    return pages


def fetch_market_inputs(*, report_date: date, days: int = 20) -> dict[str, Any]:
    """Fetch all sources; individual failures become warnings, never exceptions."""
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

    etf_snapshot = None
    try:
        etf_snapshot = parse_etf_pages(_fetch_etf_pages())
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"ETF 资金获取失败: {type(exc).__name__}")

    store = load_etf_store()
    if etf_snapshot is not None:
        store[etf_snapshot.date.isoformat()] = {
            "net_flow": etf_snapshot.net_flow,
            "top": etf_snapshot.top,
        }
        try:
            save_etf_store(store)
        except OSError as exc:
            warnings.append(f"ETF 历史写入失败: {type(exc).__name__}")

    return {
        "turnover": turnover,
        "margin": margin,
        "etf_store": store,
        "etf_snapshot": etf_snapshot,
        "warnings": warnings,
    }
