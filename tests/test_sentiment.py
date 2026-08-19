from __future__ import annotations

from datetime import date

from pipeline.sentiment import build_sentiment_snapshot, parse_report_sentiment


def _report_table(header: str = "| 博主 | 看好方向 | 看空/回避方向 |") -> str:
    return f"""# 日报

## 二、📡 博主看好方向汇总

{header}
| --- | --- | --- |
| 甲 | CPO/硅光、CPO | 白酒；消费 |
| 乙、丙 | 医药，CPO | 未明确看空 |
"""


def test_parse_direction_table_splits_and_deduplicates_signals():
    result = parse_report_sentiment(_report_table(), date(2026, 8, 19))

    assert result.found_table is True
    assert result.warning == ""
    assert {(item.author, item.direction, item.stance) for item in result.signals} == {
        ("丙", "CPO", "bullish"),
        ("丙", "医药", "bullish"),
        ("乙", "CPO", "bullish"),
        ("乙", "医药", "bullish"),
        ("甲", "CPO", "bullish"),
        ("甲", "消费", "bearish"),
        ("甲", "白酒", "bearish"),
        ("甲", "硅光", "bullish"),
    }


def test_parse_direction_table_supports_older_header_and_preserves_conflict():
    markdown = """# 日报

## 二、博主看好方向汇总

| 作者 | 看多方向 | 回避方向 |
| --- | --- | --- |
| 甲 | CPO | CPO |
"""
    result = parse_report_sentiment(markdown, date(2026, 8, 19))

    cpo = {
        (item.author, item.direction, item.stance)
        for item in result.signals
        if item.author == "甲"
    }
    assert cpo == {("甲", "CPO", "bullish"), ("甲", "CPO", "bearish")}


def test_parse_missing_direction_table_returns_warning():
    result = parse_report_sentiment("# 日报\n\n## 今日总结\n", date(2026, 8, 19))

    assert result.signals == ()
    assert result.found_table is False
    assert "未找到" in result.warning


def test_build_sentiment_snapshot_limits_to_recent_days_and_ranks_activity(tmp_path):
    report_dirs = []
    for index in range(9):
        day = date(2026, 8, 1 + index)
        report_dir = tmp_path / day.isoformat()
        report_dir.mkdir()
        direction = "存储" if index >= 2 else "旧方向"
        (report_dir / "daily-brief.md").write_text(
            _report_table().replace("CPO/硅光、CPO", direction).replace("医药，CPO", direction),
            encoding="utf-8",
        )
        report_dirs.append((day, report_dir))

    snapshot = build_sentiment_snapshot(report_dirs, window_days=7, top_limit=8)

    assert snapshot["daily"][0]["date"] == "2026-08-03"
    assert len(snapshot["daily"]) == 7
    assert snapshot["top_directions"][0]["name"] == "存储"
    assert snapshot["top_directions"][0]["activity"] == 21
    assert snapshot["top_directions"][0]["series"][-1]["net_score"] == 1.0
