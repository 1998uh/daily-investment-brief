"""Deterministic portfolio x capital-flow report generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re
from typing import Any, Iterable

from .capital_flow import CapitalFlowProvider, EastmoneyProvider, normalize_thscode
from .config import ROOT


SUPPORTED_ASSET_TYPES = {"a-share", "fund-etf"}
_CODE_WITH_SUFFIX = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")


class HoldingsInputError(ValueError):
    """Raised when the conversation payload cannot be safely analyzed."""


@dataclass(frozen=True)
class Holding:
    thscode: str
    name: str
    asset_type: str
    market_value: float | None = None
    weight_pct: float | None = None
    sector: str | None = None
    price_change_ratio_pct: float | None = None

    @property
    def supported(self) -> bool:
        return self.asset_type in SUPPORTED_ASSET_TYPES and bool(_CODE_WITH_SUFFIX.fullmatch(self.thscode))


@dataclass(frozen=True)
class CapitalDailyRun:
    report_path: Path
    ok: bool
    requested_date: str
    actual_date: str
    holding_count: int
    warning_count: int


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _asset_type(value: Any, code: str) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    if text in {"stock", "a-share", "a股", "a-share-stock"}:
        return "a-share"
    if text in {"etf", "fund-etf", "fund", "基金", "场内基金"}:
        return "fund-etf"
    if not text and code.endswith((".SH", ".SZ", ".BJ")):
        return "a-share"
    return text or "unknown"


def normalize_holdings(payload: Any) -> tuple[list[Holding], list[str]]:
    """Normalize a JSON list or ``{"holdings": [...]}`` payload."""
    items = payload.get("holdings") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or not items:
        raise HoldingsInputError("holdings payload must be a non-empty list")

    holdings: list[Holding] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            raise HoldingsInputError(f"holding #{index} must be an object")
        raw_code = raw.get("thscode", raw.get("code"))
        code = str(raw_code or "").strip().upper().replace(" ", "")
        if not code:
            raise HoldingsInputError(f"holding #{index} is missing code/thscode")
        if code in seen:
            raise HoldingsInputError(f"duplicate holding code: {code}")
        seen.add(code)
        name = str(raw.get("name") or code).strip()
        asset_type = _asset_type(raw.get("asset_type"), code)
        market_value = _number(raw.get("market_value"))
        weight_pct = _number(raw.get("weight_pct", raw.get("weight")))
        if market_value is None and weight_pct is None:
            warnings.append(f"{name}（{code}）未提供市值或仓位比例，只能做数量分析")
        if asset_type not in SUPPORTED_ASSET_TYPES:
            warnings.append(f"{name}（{code}）资产类型 {asset_type!r} 未覆盖")
        if not _CODE_WITH_SUFFIX.fullmatch(code):
            warnings.append(f"{name}（{code}）缺少交易所后缀，未调用资金流接口")
        holdings.append(
            Holding(
                thscode=code,
                name=name,
                asset_type=asset_type,
                market_value=market_value,
                weight_pct=weight_pct,
                sector=str(raw.get("sector") or "").strip() or None,
                price_change_ratio_pct=_number(raw.get("price_change_ratio_pct")),
            )
        )
    return holdings, warnings


def _load_history(provider: CapitalFlowProvider, kind: str, as_of: date) -> list[dict[str, Any]]:
    loader = getattr(provider, "load_history", None)
    if loader is None:
        return []
    try:
        rows = loader(kind, before_or_equal=as_of)
    except (OSError, ValueError, TypeError):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _actual_date(rows: Iterable[dict[str, Any]], fallback: date) -> date:
    dates: list[date] = []
    for row in rows:
        try:
            dates.append(date.fromisoformat(str(row.get("trade_date"))))
        except (TypeError, ValueError):
            continue
    return max(dates) if dates else fallback


def _window_sum(rows: Iterable[dict[str, Any]], key: str, as_of: date, limit: int) -> tuple[float | None, int]:
    by_date: dict[str, float] = {}
    for row in rows:
        try:
            row_date = date.fromisoformat(str(row.get("trade_date")))
        except (TypeError, ValueError):
            continue
        if row_date > as_of:
            continue
        value = _number(row.get(key))
        if value is not None:
            by_date[row_date.isoformat()] = value
    selected = sorted(by_date.items(), reverse=True)[:limit]
    if not selected:
        return None, 0
    return sum(value for _, value in selected), len(selected)


def _direction(value: float | None) -> str:
    if value is None:
        return "无法判断"
    if value > 0:
        return "流入"
    if value < 0:
        return "流出"
    return "中性"


def _format_yi(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value / 100_000_000:+.2f}亿"


def _format_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def _flow_index(rows: Iterable[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for candidate in (row.get(key), row.get("thscode"), row.get("sector_code"), row.get("sector_name")):
            if candidate:
                index.setdefault(str(candidate).strip().upper(), []).append(row)
    return index


def _weight_summary(holdings: list[Holding]) -> tuple[float | None, dict[int, float] | None, str]:
    values = [h.market_value for h in holdings]
    if all(value is not None for value in values):
        total = sum(value or 0 for value in values)
        equity = sum((h.market_value or 0) for h in holdings if h.supported)
        if total > 0:
            return equity / total * 100, {id(h): (h.market_value or 0) / total * 100 for h in holdings}, "market_value"
    weights = [h.weight_pct for h in holdings]
    if all(value is not None for value in weights):
        total = sum(value or 0 for value in weights)
        equity = sum((h.weight_pct or 0) for h in holdings if h.supported)
        if total > 0:
            return equity / total * 100, {id(h): (h.weight_pct or 0) / total * 100 for h in holdings}, "weight_pct"
    return None, None, "count"


def _sector_flow_for(holding: Holding, sector_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not holding.sector:
        return None
    target = holding.sector.strip().upper()
    for row in sector_rows:
        if target in {str(row.get("sector_name") or "").strip().upper(), str(row.get("sector_code") or "").strip().upper()}:
            return row
    return None


def _holding_section(
    title: str,
    holdings: list[Holding],
    sector_rows: list[dict[str, Any]],
    stock_by_code: dict[str, dict[str, Any]],
    weights: dict[int, float] | None,
) -> list[str]:
    lines = [f"### {title}", "", "| 名称 | 代码 | 仓位 | 当日涨跌 | 板块 | 个股主力 | 板块主力 | 判断 |", "|---|---|---:|---:|---|---:|---:|---|"]
    if not holdings:
        lines.append("| — | — | — | — | — | — | — | 无符合条件持仓 |")
    for holding in holdings:
        sector = _sector_flow_for(holding, sector_rows)
        stock = stock_by_code.get(holding.thscode)
        sector_direction = _direction(_number(sector.get("main_net")) if sector else None)
        lines.append(
            "| {name} | {code} | {weight} | {change} | {sector_name} | {stock_flow} | {sector_flow} | {direction} |".format(
                name=holding.name,
                code=holding.thscode,
                weight=_format_pct(weights.get(id(holding)) if weights else None),
                change=_format_pct(holding.price_change_ratio_pct),
                sector_name=holding.sector or "待映射",
                stock_flow=_format_yi(_number(stock.get("main_net")) if stock else None),
                sector_flow=_format_yi(_number(sector.get("main_net")) if sector else None),
                direction=sector_direction,
            )
        )
    return lines + [""]


def render_capital_report(
    *,
    requested_date: date,
    actual_date: date,
    holdings: list[Holding],
    warnings: list[str],
    sector_rows: list[dict[str, Any]],
    sector_history: list[dict[str, Any]],
    stock_rows: list[dict[str, Any]],
    stock_history: list[dict[str, Any]],
    source: str,
) -> str:
    equity_weight, weights, weight_mode = _weight_summary(holdings)
    stock_by_code = {str(row.get("thscode")): row for row in stock_rows if row.get("thscode")}
    sector_names = sorted({h.sector for h in holdings if h.sector})
    sector_lines: list[str] = [
        "## 板块暴露 × 资金流趋势",
        "",
        "| 板块 | 持仓数 | 仓位 | 当日主力 | 5日主力 | 20日主力 | 趋势 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    if not sector_names:
        sector_lines.append("| 待映射 | {count} | — | — | — | — | 无板块映射 |".format(count=len(holdings)))
    for sector_name in sector_names:
        members = [h for h in holdings if h.sector == sector_name]
        row = _sector_flow_for(members[0], sector_rows)
        history_rows = [r for r in sector_history if str(r.get("sector_name") or "").strip() == sector_name]
        current = _number(row.get("main_net")) if row else None
        five, five_days = _window_sum(history_rows + ([row] if row else []), "main_net", actual_date, 5)
        twenty, twenty_days = _window_sum(history_rows + ([row] if row else []), "main_net", actual_date, 20)
        sector_weight = sum(weights.get(id(h), 0) for h in members) if weights else None
        trend = _direction(current)
        if row and _number(row.get("total_net")) is None:
            trend += "（仅主力口径）"
        sector_lines.append(
            f"| {sector_name} | {len(members)} | {_format_pct(sector_weight)} | {_format_yi(current)} | {_format_yi(five)}（{five_days}日） | {_format_yi(twenty)}（{twenty_days}日） | {trend} |"
        )
    sector_lines.append("")

    eligible = [h for h in holdings if h.supported]
    flow_known = [h for h in eligible if _sector_flow_for(h, sector_rows)]
    flow_in = [h for h in flow_known if _direction(_number((_sector_flow_for(h, sector_rows) or {}).get("main_net"))) == "流入"]
    flow_out = [h for h in flow_known if _direction(_number((_sector_flow_for(h, sector_rows) or {}).get("main_net"))) == "流出"]
    unknown = [h for h in holdings if h not in flow_in and h not in flow_out]

    lines = [
        f"# A股资金面日报 PART-B — {actual_date.isoformat()}",
        "",
        f"> **请求日期**：{requested_date.isoformat()} | **实际数据日期**：{actual_date.isoformat()}",
        f"> **数据源**：{source} | **持仓数**：{len(holdings)} | **覆盖权益持仓**：{len(eligible)}",
        "> **说明**：资金流字段按数据源原始口径展示；当前公开接口未提供全市场净额时不做推断。",
        "",
        "## 整体评估",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 总持仓 | {len(holdings)}只 |",
        f"| 权益覆盖 | {len(eligible)}只 |",
        f"| 权益仓位 | {_format_pct(equity_weight)} |",
        f"| 顺风持仓 | {len(flow_in)}只 |",
        f"| 逆风持仓 | {len(flow_out)}只 |",
        f"| 无法判断 | {len(unknown)}只 |",
        "",
    ]
    if weight_mode == "count":
        lines.extend(["> ⚠️ 未提供每项市值或仓位比例，本报告不计算真实仓位权重。", ""])
    lines.extend(sector_lines)
    lines.extend(_holding_section("🟢 顺风持仓", flow_in, sector_rows, stock_by_code, weights))
    lines.extend(_holding_section("🔴 逆风持仓", flow_out, sector_rows, stock_by_code, weights))
    lines.extend(_holding_section("🟡 无法判断/未覆盖持仓", unknown, sector_rows, stock_by_code, weights))
    lines.extend(["## 数据覆盖与限制", ""])
    if warnings:
        lines.extend(f"- {warning}" for warning in dict.fromkeys(warnings))
    else:
        lines.append("- 输入校验通过。")
    lines.extend(
        [
            "- 5日历史实际可用窗口按缓存计算；20日窗口不足时报告实际天数。",
            "- 当前首版仅覆盖 A 股个股和 ETF；港股、现金及无法消歧资产不参与资金流方向判断。",
            "- 本报告仅为数据分析，不构成投资建议。",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def run_capital_daily(
    *,
    payload: Any,
    requested_date: date,
    out_dir: Path | None = None,
    cache_dir: Path | None = None,
    provider: CapitalFlowProvider | None = None,
) -> CapitalDailyRun:
    holdings, warnings = normalize_holdings(payload)
    target_out = Path(out_dir) if out_dir else ROOT / "private-reports" / requested_date.isoformat()
    target_cache = Path(cache_dir) if cache_dir else ROOT / "data" / "capital-flow"
    target_out.mkdir(parents=True, exist_ok=True)
    provider = provider or EastmoneyProvider(target_cache)

    errors: list[str] = []
    sector_rows: list[dict[str, Any]] = []
    stock_rows: list[dict[str, Any]] = []
    try:
        sector_rows = provider.fetch_sector_flow(requested_date)
    except Exception as exc:
        errors.append(f"板块资金流获取失败：{exc}")

    supported = [h for h in holdings if h.supported]
    if supported:
        try:
            stock_rows = provider.fetch_stock_flow(
                [normalize_thscode(holding.thscode) for holding in supported],
                requested_date,
            )
        except Exception as exc:
            errors.append(f"个股资金流获取失败（{len(supported)}只）：{exc}")

    all_dates = [row for row in sector_rows + stock_rows if row.get("trade_date")]
    actual_date = _actual_date(all_dates, requested_date)
    sector_rows = [row for row in sector_rows if row.get("trade_date") == actual_date.isoformat()]
    stock_rows = [row for row in stock_rows if row.get("trade_date") == actual_date.isoformat()]
    if all_dates and actual_date != requested_date:
        warnings.append(
            f"请求日期 {requested_date.isoformat()} 无完整资金流，使用最近数据日 {actual_date.isoformat()}"
        )
    sector_history = _load_history(provider, "sectors", actual_date)
    stock_history = _load_history(provider, "stocks", actual_date)
    if errors:
        warnings.extend(errors)
    if not sector_rows:
        warnings.append("资金流数据不可用，未输出板块方向结论。")
    markdown = render_capital_report(
        requested_date=requested_date,
        actual_date=actual_date,
        holdings=holdings,
        warnings=warnings,
        sector_rows=sector_rows,
        sector_history=sector_history,
        stock_rows=stock_rows,
        stock_history=stock_history,
        source="Eastmoney public API",
    )
    report_path = target_out / "capital-daily.md"
    report_path.write_text(markdown, encoding="utf-8")
    return CapitalDailyRun(
        report_path=report_path,
        ok=not errors,
        requested_date=requested_date.isoformat(),
        actual_date=actual_date.isoformat(),
        holding_count=len(holdings),
        warning_count=len(warnings),
    )


def run_capital_daily_from_stdin(
    *,
    raw: str,
    requested_date: date,
    out_dir: Path | None = None,
    cache_dir: Path | None = None,
    provider: CapitalFlowProvider | None = None,
) -> CapitalDailyRun:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HoldingsInputError(f"stdin is not valid JSON: {exc.msg}") from exc
    return run_capital_daily(
        payload=payload,
        requested_date=requested_date,
        out_dir=out_dir,
        cache_dir=cache_dir,
        provider=provider,
    )
