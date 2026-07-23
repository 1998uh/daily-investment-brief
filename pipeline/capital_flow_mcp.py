"""stdio MCP server exposing the small capital-flow contract used by PART-B."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .capital_flow import CapitalFlowError, EastmoneyProvider, normalize_thscode
from .config import ROOT


mcp = FastMCP("capital-flow-mcp")
_provider = EastmoneyProvider(ROOT / "data" / "capital-flow")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _error(message: str) -> dict[str, Any]:
    return {"code": 5001, "message": message, "data": None}


@mcp.tool()
def get_stock_capital_flow(
    thscodes: list[str],
    trade_date: str | None = None,
) -> dict[str, Any]:
    """Get current per-stock main/super-large/large/medium/small flow records."""
    try:
        if not thscodes or len(thscodes) > 50:
            return _error("thscodes must contain 1-50 items")
        requested = _parse_date(trade_date)
        items = _provider.fetch_stock_flow([normalize_thscode(code) for code in thscodes], requested)
        return {"code": 0, "message": "success", "data": {"item": items}}
    except (CapitalFlowError, ValueError) as exc:
        return _error(str(exc))


@mcp.tool()
def get_sector_capital_flow(
    sectors: list[str],
    trade_date: str | None = None,
) -> dict[str, Any]:
    """Get current flow records for named Eastmoney industry sectors or sector codes."""
    try:
        if not sectors or len(sectors) > 50:
            return _error("sectors must contain 1-50 items")
        requested = _parse_date(trade_date)
        wanted = {str(item).strip().upper() for item in sectors if str(item).strip()}
        rows = _provider.fetch_sector_flow(requested)
        items = [
            row
            for row in rows
            if str(row.get("sector_name") or "").strip().upper() in wanted
            or str(row.get("sector_code") or "").strip().upper() in wanted
        ]
        return {"code": 0, "message": "success", "data": {"item": items}}
    except (CapitalFlowError, ValueError) as exc:
        return _error(str(exc))


@mcp.tool()
def get_capital_flow_history(
    kind: Literal["stocks", "sectors"],
    identifiers: list[str],
    end_date: str,
    window: int = 20,
) -> dict[str, Any]:
    """Read cached daily flow records for up to 20 trading days."""
    try:
        if kind not in {"stocks", "sectors"}:
            return _error("kind must be stocks or sectors")
        if not identifiers or len(identifiers) > 50:
            return _error("identifiers must contain 1-50 items")
        if not 1 <= window <= 20:
            return _error("window must be between 1 and 20")
        cutoff = date.fromisoformat(end_date)
        rows = _provider.load_history(kind, before_or_equal=cutoff)
        wanted = {str(item).strip().upper() for item in identifiers if str(item).strip()}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            candidates = {
                str(row.get("thscode") or "").strip().upper(),
                str(row.get("sector_code") or "").strip().upper(),
                str(row.get("sector_name") or "").strip().upper(),
            }
            matches = sorted((candidates - {""}) & wanted)
            if matches:
                grouped.setdefault(matches[0], []).append(row)
        items: list[dict[str, Any]] = []
        for key, records in grouped.items():
            records.sort(key=lambda row: str(row.get("trade_date") or ""), reverse=True)
            items.extend(records[:window])
        return {"code": 0, "message": "success", "data": {"item": items, "window": window}}
    except (CapitalFlowError, ValueError, OSError) as exc:
        return _error(str(exc))


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
