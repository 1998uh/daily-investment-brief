"""Two-panel market trend chart rendered with Pillow.

The PNG is embedded in the HTML report and in the email as a CID image, so it
must be self-contained and mobile-readable.
"""
from __future__ import annotations

from datetime import date
import os
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont

from .market_metrics import MarketPoint


WIDTH = 900
HEIGHT = 560
LEFT = 90
RIGHT = 870
TOP = 60
BOTTOM = 520
PANEL_GAP = 18
TEXT = (31, 41, 51)
MUTED = (102, 112, 133)
GRID = (226, 232, 240)
BLUE = (37, 99, 235)
ORANGE = (217, 119, 6)


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        os.getenv("BRIEF_CHART_FONT", "").strip(),
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else "",
        r"C:\Windows\Fonts\simhei.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _fmt(value: float, unit: str) -> str:
    return f"{value:.2f}{unit}"


def _line_panel(
    draw: ImageDraw.ImageDraw,
    *,
    title: str,
    values: list[float | None],
    top: int,
    height: int,
    color: tuple[int, int, int],
    font: ImageFont.FreeTypeFont,
) -> None:
    draw.text((LEFT, top), title, fill=TEXT, font=font)
    plot_top = top + 24
    plot_bottom = top + height - 10
    draw.rectangle((LEFT, plot_top, RIGHT, plot_bottom), outline=GRID)
    present = [value for value in values if value is not None]
    if not present:
        draw.text(
            ((LEFT + RIGHT) // 2 - 30, (plot_top + plot_bottom) // 2 - 8),
            "数据不可用",
            fill=MUTED,
            font=font,
        )
        return
    low, high = min(present), max(present)
    if low == high:
        low -= 1
        high += 1
    padding = (high - low) * 0.1
    low -= padding
    high += padding
    count = max(1, len(values) - 1)
    step = (RIGHT - LEFT) / count

    def xy(index: int, value: float) -> tuple[float, float]:
        x = LEFT + index * step
        y = plot_bottom - (value - low) / (high - low) * (plot_bottom - plot_top)
        return x, y

    points = [(index, value) for index, value in enumerate(values) if value is not None]
    for (i1, v1), (i2, v2) in zip(points, points[1:]):
        if i2 - i1 > 1:
            continue
        draw.line([xy(i1, v1), xy(i2, v2)], fill=color, width=2)
    for index, value in points:
        x, y = xy(index, value)
        draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=color)

    draw.text((8, plot_top), _fmt(high, ""), fill=MUTED, font=font)
    draw.text((8, plot_bottom - 12), _fmt(low, ""), fill=MUTED, font=font)
    last_index, last_value = points[-1]
    x, y = xy(last_index, last_value)
    draw.text(
        (min(x + 4, RIGHT - 70), max(plot_top, y - 16)),
        _fmt(last_value, ""),
        fill=TEXT,
        font=font,
    )


def render_market_trend(
    points: Sequence[MarketPoint],
    out_path: Path,
    *,
    as_of: date,
    margin_date: date | None = None,
) -> Path:
    """Render the 20-day turnover / margin PNG and return its path."""
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    title_font = _font(18, bold=True)
    label_font = _font(12)
    small_font = _font(11)

    draw.text(
        (30, 18),
        f"大盘量能趋势（近 {len(points)} 个交易日，截至 {as_of.isoformat()}）",
        fill=TEXT,
        font=title_font,
    )
    draw.text(
        (30, 40),
        "数据来源：BaoStock / 东方财富；区间为沪深两市，不含北证",
        fill=MUTED,
        font=small_font,
    )

    panel_height = (BOTTOM - TOP - PANEL_GAP) // 2
    dates = [point.date for point in points]
    _line_panel(
        draw,
        title="成交额（万亿元）",
        values=[
            None if point.turnover is None else point.turnover / 1e12 for point in points
        ],
        top=TOP,
        height=panel_height,
        color=BLUE,
        font=label_font,
    )
    margin_top = TOP + panel_height + PANEL_GAP
    _line_panel(
        draw,
        title="两融余额（万亿元）",
        values=[
            None if point.margin_balance is None else point.margin_balance / 1e12
            for point in points
        ],
        top=margin_top,
        height=panel_height,
        color=ORANGE,
        font=label_font,
    )

    if dates:
        step = (RIGHT - LEFT) / max(1, len(dates) - 1)
        for index, day in enumerate(dates):
            if index % 5 != 0 and index != len(dates) - 1:
                continue
            x = LEFT + index * step
            label = day.strftime("%m-%d")
            draw.text(
                (min(max(x - 14, LEFT), RIGHT - 30), BOTTOM - 2),
                label,
                fill=MUTED,
                font=small_font,
            )

    margin_label = (
        f"两融数据截至 {margin_date.isoformat()}" if margin_date else "两融数据截至日期未知"
    )
    draw.text((30, HEIGHT - 22), margin_label, fill=MUTED, font=small_font)

    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format="PNG")
    return target
