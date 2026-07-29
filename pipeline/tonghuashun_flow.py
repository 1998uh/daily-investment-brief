"""Tonghuashun public industry net-flow fallback for PART-B reports."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Callable, Sequence
from zoneinfo import ZoneInfo

import requests

from .capital_flow import CapitalFlowError


THS_FLOW_URL = (
    "https://data.10jqka.com.cn/funds/hyzjl/field/tradezdf/"
    "order/desc/page/{page}/ajax/1/free/1/"
)
THS_REFERER = "https://data.10jqka.com.cn/funds/hyzjl/"
THS_TOKEN_SCRIPT = Path(__file__).resolve().parent / "assets" / "ths.js"


def _latest_weekday(value: date) -> date:
    while value.weekday() >= 5:
        value -= timedelta(days=1)
    return value


class _IndustryTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[list[str], list[str | None]]] = []
        self._row: list[str] | None = None
        self._hrefs: list[str | None] | None = None
        self._cell: list[str] | None = None
        self._cell_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
            self._hrefs = []
        elif tag == "td" and self._row is not None:
            self._cell = []
            self._cell_href = None
        elif tag == "a" and self._cell is not None:
            self._cell_href = dict(attrs).get("href")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._row is not None and self._hrefs is not None and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._hrefs.append(self._cell_href)
            self._cell = None
            self._cell_href = None
        elif tag == "tr" and self._row is not None and self._hrefs is not None:
            if len(self._row) >= 11 and self._row[0].isdigit():
                self.rows.append((self._row, self._hrefs))
            self._row = None
            self._hrefs = None
            self._cell = None
            self._cell_href = None


def _generate_hexin_v() -> str:
    node = os.getenv("THS_NODE_PATH", "").strip() or shutil.which("node")
    if not node:
        raise CapitalFlowError("Tonghuashun fallback needs Node.js on PATH or THS_NODE_PATH")
    if not THS_TOKEN_SCRIPT.exists():
        raise CapitalFlowError(f"Tonghuashun token script is missing: {THS_TOKEN_SCRIPT}")
    script_path = json.dumps(str(THS_TOKEN_SCRIPT))
    javascript = (
        "const fs=require('fs'),vm=require('vm');"
        f"vm.runInThisContext(fs.readFileSync({script_path},'utf8'));"
        "process.stdout.write(v())"
    )
    try:
        completed = subprocess.run(
            [node, "-e", javascript],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CapitalFlowError(f"failed to generate Tonghuashun request token: {exc}") from exc
    token = completed.stdout.strip()
    if not token:
        raise CapitalFlowError("Tonghuashun request token generator returned an empty value")
    return token


def _get_html(
    url: str,
    *,
    token_factory: Callable[[], str],
    timeout: float,
    retries: int,
    retry_delay: float,
) -> str:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            headers = {
                "Accept": "text/html, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
                "hexin-v": token_factory(),
                "Referer": THS_REFERER,
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
                ),
                "X-Requested-With": "XMLHttpRequest",
            }
            session = requests.Session()
            session.trust_env = attempt % 2 == 1
            response = session.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            html = response.content.decode("gbk", errors="replace")
            if "J-ajax-table" not in html:
                raise CapitalFlowError("Tonghuashun returned a non-table response")
            return html
        except (requests.RequestException, OSError, ValueError, CapitalFlowError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(retry_delay * (2**attempt))
    raise CapitalFlowError(
        f"Tonghuashun sector flow failed after {retries + 1} attempt(s): {last_error}"
    )


def _page_count(html: str) -> int:
    match = re.search(r'class=["\']page_info["\']>\s*\d+/(\d+)\s*<', html)
    return int(match.group(1)) if match else 1


def _parse_amount_yi(value: str, field: str) -> float:
    text = value.strip().replace(",", "")
    if not text or text == "-":
        raise CapitalFlowError(f"missing Tonghuashun numeric field: {field}")
    try:
        return float(text) * 100_000_000
    except ValueError as exc:
        raise CapitalFlowError(f"invalid Tonghuashun numeric field {field}: {value!r}") from exc


def _parse_sector_rows(html: str, trade_date: date) -> list[dict[str, Any]]:
    parser = _IndustryTableParser()
    parser.feed(html)
    records: list[dict[str, Any]] = []
    for cells, hrefs in parser.rows:
        href = hrefs[1] or ""
        code_match = re.search(r"/code/(\d+)/", href)
        sector_code = f"{code_match.group(1)}.TI" if code_match else cells[1]
        records.append(
            {
                "sector_code": sector_code,
                "sector_name": cells[1],
                "trade_date": trade_date.isoformat(),
                "main_net": None,
                "small_net": None,
                "medium_net": None,
                "large_net": None,
                "super_large_net": None,
                "total_net": _parse_amount_yi(cells[6], "net_flow"),
                "inflow_total": _parse_amount_yi(cells[4], "inflow"),
                "outflow_total": _parse_amount_yi(cells[5], "outflow"),
                "source": "tonghuashun",
                "flow_metric": "total_net",
                "flow_label": "同花顺资金净额",
            }
        )
    return records


class TonghuashunSectorFlowProvider:
    """Read current industry inflow/outflow net values from data.10jqka.com.cn."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        timeout: float = 15.0,
        retries: int = 2,
        retry_delay: float = 0.5,
        token_factory: Callable[[], str] = _generate_hexin_v,
        today_factory: Callable[[], date] | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.timeout = timeout
        self.retries = max(0, retries)
        self.retry_delay = max(0.0, retry_delay)
        self.token_factory = token_factory
        self.today_factory = today_factory or (
            lambda: datetime.now(ZoneInfo("Asia/Shanghai")).date()
        )

    def fetch_sector_flow(self, trade_date: date | None = None) -> list[dict[str, Any]]:
        requested = trade_date or self.today_factory()
        cached = self._read_cache("sectors", requested.isoformat())
        if cached:
            return cached
        today = self.today_factory()
        if requested != today:
            raise CapitalFlowError(
                "Tonghuashun public sector flow is current-day only and no matching cache exists: "
                f"{requested.isoformat()}"
            )
        effective_date = _latest_weekday(requested)
        cached = self._read_cache("sectors", effective_date.isoformat())
        if cached:
            return cached
        first_page = _get_html(
            THS_FLOW_URL.format(page=1),
            token_factory=self.token_factory,
            timeout=self.timeout,
            retries=self.retries,
            retry_delay=self.retry_delay,
        )
        pages = _page_count(first_page)
        if pages < 1 or pages > 20:
            raise CapitalFlowError(f"unexpected Tonghuashun page count: {pages}")
        records = _parse_sector_rows(first_page, effective_date)
        for page in range(2, pages + 1):
            html = _get_html(
                THS_FLOW_URL.format(page=page),
                token_factory=self.token_factory,
                timeout=self.timeout,
                retries=self.retries,
                retry_delay=self.retry_delay,
            )
            records.extend(_parse_sector_rows(html, effective_date))
        records = list(
            {str(record["sector_code"]): record for record in records}.values()
        )
        if not records:
            raise CapitalFlowError("empty Tonghuashun sector-flow response")
        self._write_cache("sectors", effective_date.isoformat(), records)
        return records

    def fetch_stock_flow(
        self,
        thscodes: Sequence[str],
        trade_date: date | None = None,
    ) -> list[dict[str, Any]]:
        raise CapitalFlowError("Tonghuashun fallback only implements sector flow")

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
                rows.extend(self._read_cache(kind, path.stem))
        return rows

    def _write_cache(self, kind: str, trade_date: str, records: list[dict[str, Any]]) -> None:
        directory = self.cache_dir / kind
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{trade_date}.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
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
