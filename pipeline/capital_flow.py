"""Capital-flow provider and cache primitives for the private PART-B report.

The provider intentionally uses the public Eastmoney JSON endpoints through the
standard library.  Keeping the transport small makes it easy to replace with
AkShare or another MCP-backed provider without changing report calculations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
import time
from typing import Any, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import requests
except ImportError:  # pragma: no cover - package metadata installs requests in normal use
    requests = None


class CapitalFlowError(RuntimeError):
    """Raised when a capital-flow response cannot be trusted."""


class CapitalFlowProvider(Protocol):
    def fetch_stock_flow(self, thscodes: Sequence[str], trade_date: date | None = None) -> list[dict[str, Any]]:
        ...

    def fetch_sector_flow(self, trade_date: date | None = None) -> list[dict[str, Any]]:
        ...


@dataclass(frozen=True)
class StockFlow:
    thscode: str
    trade_date: str
    main_net: float
    small_net: float
    medium_net: float
    large_net: float
    super_large_net: float
    total_net: float | None = None
    source: str = "eastmoney"


@dataclass(frozen=True)
class SectorFlow:
    sector_code: str
    sector_name: str
    trade_date: str
    main_net: float
    small_net: float
    medium_net: float
    large_net: float
    super_large_net: float
    total_net: float | None = None
    source: str = "eastmoney"


def _as_number(value: Any) -> float | None:
    if value is None or value == "" or value == "-":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _required_number(value: Any, field: str) -> float:
    parsed = _as_number(value)
    if parsed is None:
        raise CapitalFlowError(f"missing numeric field: {field}")
    return parsed


def normalize_thscode(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = re.sub(r"\s+", "", text)
    if re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", text):
        return text
    raise ValueError(f"thscode must include exchange suffix (.SH/.SZ/.BJ): {value!r}")


def _eastmoney_secid(thscode: str) -> str:
    code = normalize_thscode(thscode)
    ticker, suffix = code.split(".")
    # Eastmoney uses 1 for Shanghai and 0 for Shenzhen/Beijing stock quotes.
    market = "1" if suffix == "SH" else "0"
    return f"{market}.{ticker}"


def _parse_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if text.isdigit() and len(text) >= 10:
        return datetime.fromtimestamp(int(text[:10]), tz=timezone.utc).date().isoformat()
    return None


def _get_json(url: str, *, timeout: float, retries: int, retry_delay: float) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Codex capital-daily)",
                "Accept": "application/json,text/plain,*/*",
                "Referer": "https://quote.eastmoney.com/",
            }
            if requests is not None:
                session = requests.Session()
                # Public market endpoints are often more reliable without a stale system proxy.
                # Retry through the configured proxy once for environments that require it.
                session.trust_env = attempt % 2 == 1
                response = session.get(url, timeout=timeout, headers=headers)
                response.raise_for_status()
                payload = response.json()
            else:
                request = Request(url, headers=headers)
                with urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise CapitalFlowError("provider returned a non-object JSON response")
            return payload
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, CapitalFlowError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(retry_delay * (2**attempt))
    raise CapitalFlowError(f"capital-flow request failed after {retries + 1} attempt(s): {last_error}")


class EastmoneyProvider:
    """Read current stock and industry capital flow from public endpoints."""

    STOCK_FLOW_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    SECTOR_FLOW_URL = "https://push2.eastmoney.com/api/qt/clist/get"

    def __init__(
        self,
        cache_dir: Path,
        *,
        timeout: float = 15.0,
        retries: int = 2,
        retry_delay: float = 0.5,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.timeout = timeout
        self.retries = max(0, retries)
        self.retry_delay = max(0.0, retry_delay)

    def fetch_stock_flow(self, thscodes: Sequence[str], trade_date: date | None = None) -> list[dict[str, Any]]:
        normalized = list(dict.fromkeys(normalize_thscode(code) for code in thscodes))
        if not normalized:
            return []
        if len(normalized) > 50:
            raise CapitalFlowError("stock capital-flow batch exceeds 50 items")
        records: list[dict[str, Any]] = []
        if trade_date:
            cached = self._read_cache("stocks", trade_date.isoformat())
            cached_by_code = {str(row.get("thscode")): row for row in cached}
            records = [cached_by_code[code] for code in normalized if code in cached_by_code]
            normalized = [code for code in normalized if code not in cached_by_code]
            if not normalized:
                return records
        by_ticker = {code.split(".")[0]: code for code in normalized}
        params = {
            "fltt": "2",
            "secids": ",".join(_eastmoney_secid(code) for code in normalized),
            "fields": "f12,f14,f62,f66,f72,f78,f84,f124",
        }
        payload = _get_json(
            f"{self.STOCK_FLOW_URL}?{urlencode(params)}",
            timeout=self.timeout,
            retries=self.retries,
            retry_delay=self.retry_delay,
        )
        data = payload.get("data") or {}
        rows = data.get("diff") or []
        if not rows:
            raise CapitalFlowError("empty stock capital-flow response")
        for row in rows:
            ticker = str(row.get("f12") or "").strip()
            thscode = by_ticker.get(ticker)
            if not thscode:
                continue
            actual_date = _parse_date(row.get("f124"))
            if not actual_date:
                raise CapitalFlowError(f"missing stock trade date: {thscode}")
            record = asdict(
                StockFlow(
                    thscode=thscode,
                    trade_date=actual_date,
                    main_net=_required_number(row.get("f62"), "main_net"),
                    super_large_net=_required_number(row.get("f66"), "super_large_net"),
                    large_net=_required_number(row.get("f72"), "large_net"),
                    medium_net=_required_number(row.get("f78"), "medium_net"),
                    small_net=_required_number(row.get("f84"), "small_net"),
                )
            )
            records.append(record)
        missing = sorted(set(normalized) - {record["thscode"] for record in records})
        if missing:
            raise CapitalFlowError(f"missing stock capital-flow rows: {', '.join(missing)}")
        if records:
            self._merge_cache("stocks", records[0]["trade_date"], records, key="thscode")
        return records

    def fetch_sector_flow(self, trade_date: date | None = None) -> list[dict[str, Any]]:
        if trade_date:
            cached = self._read_cache("sectors", trade_date.isoformat())
            if cached:
                return cached
        rows: list[dict[str, Any]] = []
        page = 1
        total = 1
        while len(rows) < total:
            params = {
                "pn": str(page),
                "pz": "100",
                "po": "1",
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fid": "f62",
                "fs": "m:90+t:2",
                "fields": "f12,f14,f2,f3,f62,f66,f69,f72,f75,f78,f81,f84,f87,f124",
            }
            payload = _get_json(
                f"{self.SECTOR_FLOW_URL}?{urlencode(params)}",
                timeout=self.timeout,
                retries=self.retries,
                retry_delay=self.retry_delay,
            )
            data = payload.get("data") or {}
            page_rows = data.get("diff") or []
            total = int(data.get("total") or len(page_rows))
            if not page_rows:
                break
            rows.extend(row for row in page_rows if isinstance(row, dict))
            page += 1
            if len(rows) < total:
                time.sleep(0.15)
        if not rows:
            raise CapitalFlowError("empty sector capital-flow response")
        rows = list({str(row.get("f12")): row for row in rows if row.get("f12")}.values())
        records: list[dict[str, Any]] = []
        for row in rows:
            actual_date = _parse_date(row.get("f124")) or (trade_date.isoformat() if trade_date else date.today().isoformat())
            records.append(
                asdict(
                    SectorFlow(
                        sector_code=str(row.get("f12") or "").strip(),
                        sector_name=str(row.get("f14") or "").strip(),
                        trade_date=actual_date,
                        main_net=_required_number(row.get("f62"), "main_net"),
                        super_large_net=_required_number(row.get("f66"), "super_large_net"),
                        large_net=_required_number(row.get("f72"), "large_net"),
                        medium_net=_required_number(row.get("f78"), "medium_net"),
                        small_net=_required_number(row.get("f84"), "small_net"),
                    )
                )
            )
        actual_date = records[0]["trade_date"]
        self._merge_cache("sectors", actual_date, records, key="sector_code")
        return records

    def load_history(self, kind: str, *, before_or_equal: date) -> list[dict[str, Any]]:
        directory = self.cache_dir / kind
        if not directory.exists():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            try:
                stored_date = date.fromisoformat(path.stem)
            except ValueError:
                continue
            if stored_date <= before_or_equal:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(payload, list):
                    rows.extend(item for item in payload if isinstance(item, dict))
        return rows

    def _merge_cache(self, kind: str, trade_date: str, records: list[dict[str, Any]], *, key: str) -> None:
        directory = self.cache_dir / kind
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{trade_date}.json"
        existing: list[dict[str, Any]] = []
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    existing = [item for item in payload if isinstance(item, dict)]
            except (OSError, json.JSONDecodeError):
                existing = []
        merged = {str(item.get(key)): item for item in existing if item.get(key)}
        merged.update({str(item[key]): item for item in records if item.get(key)})
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(list(merged.values()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)

    def _read_cache(self, kind: str, trade_date: str) -> list[dict[str, Any]]:
        path = self.cache_dir / kind / f"{trade_date}.json"
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]
