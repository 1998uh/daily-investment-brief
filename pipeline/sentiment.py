"""Extract and aggregate author direction signals from daily briefs.

The parser intentionally consumes only the structured direction summary table
so narrative risk warnings and quoted opinions are not mistaken for signals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
from typing import Iterable


_HEADING_RE = re.compile(r"^#{1,6}\s+.*博主.*(?:看好|多空).*方向", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")
_CELL_SPLIT_RE = re.compile(r"[、,，;；/／]+")
_AUTHOR_SPLIT_RE = re.compile(r"[、,，;；]+")
_PLACEHOLDERS = {
    "无",
    "暂无",
    "未明确",
    "未发布",
    "未给出",
    "无明确看空",
    "无明确行业多空",
}


@dataclass(frozen=True)
class SentimentSignal:
    report_date: date
    author: str
    direction: str
    stance: str


@dataclass(frozen=True)
class SentimentParseResult:
    signals: tuple[SentimentSignal, ...]
    found_table: bool
    warning: str = ""


def parse_report_sentiment(markdown: str, report_date: date) -> SentimentParseResult:
    """Parse one report's structured author-direction table."""
    lines = markdown.splitlines()
    heading_index = next(
        (index for index, line in enumerate(lines) if _HEADING_RE.match(line.strip())),
        None,
    )
    if heading_index is None:
        return SentimentParseResult(
            (), False, f"{report_date.isoformat()}: 未找到博主看好方向汇总章节"
        )

    table = _find_table(lines, heading_index + 1)
    if table is None:
        return SentimentParseResult(
            (), False, f"{report_date.isoformat()}: 博主看好方向汇总章节缺少表格"
        )
    header, rows = table
    author_index = _find_column(header, ("博主", "作者"))
    bullish_index = _find_column(header, ("看好", "看多"))
    bearish_index = _find_column(header, ("看空", "回避", "规避"))
    if author_index is None or bullish_index is None or bearish_index is None:
        return SentimentParseResult(
            (), True, f"{report_date.isoformat()}: 方向表缺少博主/看好/看空列"
        )

    signals: set[tuple[date, str, str, str]] = set()
    for row in rows:
        if max(author_index, bullish_index, bearish_index) >= len(row):
            continue
        authors = _split_authors(row[author_index])
        for author in authors:
            for direction in _split_directions(row[bullish_index]):
                signals.add((report_date, author, direction, "bullish"))
            for direction in _split_directions(row[bearish_index]):
                signals.add((report_date, author, direction, "bearish"))

    result = tuple(
        SentimentSignal(report_date, author, direction, stance)
        for _, author, direction, stance in sorted(signals, key=lambda item: item[1:])
    )
    return SentimentParseResult(result, True)


def build_sentiment_snapshot(
    report_dirs: Iterable[tuple[date, Path]],
    *,
    window_days: int = 7,
    top_limit: int = 8,
) -> dict:
    """Build a dashboard-ready sentiment snapshot from historical reports."""
    parsed: dict[date, SentimentParseResult] = {}
    warnings: list[str] = []
    for report_date, report_dir in report_dirs:
        path = report_dir / "daily-brief.md"
        if not path.exists():
            continue
        try:
            result = parse_report_sentiment(path.read_text(encoding="utf-8"), report_date)
        except (OSError, UnicodeError) as exc:
            result = SentimentParseResult((), False, f"{report_date.isoformat()}: 读取日报失败: {exc}")
        parsed[report_date] = result
        if result.warning:
            warnings.append(result.warning)

    dates = sorted(parsed)[-max(1, window_days):]
    daily = [_daily_row(day, parsed[day].signals) for day in dates]
    direction_names = sorted(
        {
            signal.direction
            for day in dates
            for signal in parsed[day].signals
        }
    )
    totals = {name: _direction_totals(name, dates, parsed) for name in direction_names}
    ranked = sorted(
        totals.items(),
        key=lambda item: (-item[1]["activity"], -item[1]["days_active"], item[0].casefold()),
    )[: max(1, top_limit)]
    top_directions = []
    for name, total in ranked:
        top_directions.append(
            {
                "name": name,
                "bullish": total["bullish"],
                "bearish": total["bearish"],
                "activity": total["activity"],
                "days_active": total["days_active"],
                "net_score": _score(total["bullish"], total["bearish"]),
                "series": [
                    _direction_row(name, parsed[day].signals)
                    for day in dates
                ],
            }
        )

    return {
        "window_days": window_days,
        "top_limit": top_limit,
        "daily": daily,
        "top_directions": top_directions,
        "warnings": warnings,
    }


def _find_table(lines: list[str], start: int) -> tuple[list[str], list[list[str]]] | None:
    index = start
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith("#"):
            return None
        if (
            stripped.startswith("|")
            and index + 1 < len(lines)
            and _is_separator_row(lines[index + 1])
        ):
            header = _split_row(stripped)
            rows: list[list[str]] = []
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(_split_row(lines[index].strip()))
                index += 1
            return header, rows
        index += 1
    return None


def _is_separator_row(line: str) -> bool:
    cells = _split_row(line.strip())
    return bool(cells) and all(_SEPARATOR_RE.fullmatch(cell.replace(" ", "")) for cell in cells)


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _find_column(header: list[str], names: tuple[str, ...]) -> int | None:
    for index, cell in enumerate(header):
        normalized = re.sub(r"[\s*_`：:（）()]+", "", cell).lower()
        if any(name.lower() in normalized for name in names):
            return index
    return None


def _split_authors(value: str) -> list[str]:
    cleaned = _clean_cell(value)
    return [part for part in _AUTHOR_SPLIT_RE.split(cleaned) if part]


def _split_directions(value: str) -> list[str]:
    result = []
    for raw in _CELL_SPLIT_RE.split(_clean_cell(value)):
        direction = _clean_direction(raw)
        if direction and not _is_placeholder(direction):
            result.append(direction)
    return result


def _clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("**", "").replace("`", "")).strip()


def _clean_direction(value: str) -> str:
    direction = re.sub(r"^[-*•·]\s*", "", value.strip())
    direction = re.sub(r"\s*[（(][^（）()]*[）)]\s*$", "", direction)
    return direction.strip(" ：:，,;；")


def _is_placeholder(value: str) -> bool:
    if value in _PLACEHOLDERS:
        return True
    return value.startswith(("未明确", "未发布", "未给出", "无明确"))


def _daily_row(day: date, signals: Iterable[SentimentSignal]) -> dict:
    signals = tuple(signals)
    bullish = sum(signal.stance == "bullish" for signal in signals)
    bearish = sum(signal.stance == "bearish" for signal in signals)
    directions = sorted(
        {
            signal.direction
            for signal in signals
        },
        key=str.casefold,
    )
    return {
        "date": day.isoformat(),
        "bullish": bullish,
        "bearish": bearish,
        "net_score": _score(bullish, bearish),
        "directions": [_direction_row(name, signals) for name in directions],
    }


def _direction_row(name: str, signals: Iterable[SentimentSignal]) -> dict:
    signals = tuple(signal for signal in signals if signal.direction == name)
    bullish = sum(signal.stance == "bullish" for signal in signals)
    bearish = sum(signal.stance == "bearish" for signal in signals)
    return {
        "name": name,
        "bullish": bullish,
        "bearish": bearish,
        "activity": bullish + bearish,
        "net_score": _score(bullish, bearish),
    }


def _direction_totals(name: str, dates: list[date], parsed: dict[date, SentimentParseResult]) -> dict[str, int]:
    bullish = 0
    bearish = 0
    days_active = 0
    for day in dates:
        row = _direction_row(name, parsed[day].signals)
        bullish += row["bullish"]
        bearish += row["bearish"]
        days_active += bool(row["activity"])
    return {
        "bullish": bullish,
        "bearish": bearish,
        "activity": bullish + bearish,
        "days_active": days_active,
    }


def _score(bullish: int, bearish: int) -> float:
    total = bullish + bearish
    return round((bullish - bearish) / total, 4) if total else 0.0
