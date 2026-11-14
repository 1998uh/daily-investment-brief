from datetime import date

from PIL import Image

from pipeline.market_chart import render_market_trend
from pipeline.market_metrics import MarketPoint


def test_renders_a_three_panel_png(tmp_path):
    points = [
        MarketPoint(date(2026, 11, d), 1.5e12 + d, 2.3e12 + d, 1e9 - d)
        for d in range(1, 21)
    ]

    path = render_market_trend(
        points,
        tmp_path / "market-trend.png",
        as_of=date(2026, 11, 20),
        margin_date=date(2026, 11, 19),
    )

    assert path.exists() and path.stat().st_size > 1000
    assert Image.open(path).size == (900, 560)


def test_missing_values_do_not_crash(tmp_path):
    points = [MarketPoint(date(2026, 11, 1), None, None, None)]

    path = render_market_trend(points, tmp_path / "chart.png", as_of=date(2026, 11, 1))

    assert path.exists()
