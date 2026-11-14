from datetime import date

from pipeline.report_gate import check_report

VALID = "# 📊 每日投资简报 — 2026年11月14日（周六·盘前）\n\n" + (
    "## 今日三句话\n\n## 一、💼 博主持仓信息\n\n## 二、📡 博主看好方向汇总\n\n"
    "## 三、⚡ 今日注意事项与投资总结\n\n## N-3、📋 数据覆盖情况\n\n" + "正文" * 1600
)


def test_valid_report_has_no_failures():
    assert check_report(date(2026, 11, 14), VALID, "<html>ok</html>") == []


def test_wrong_date_is_rejected():
    failures = check_report(date(2026, 11, 15), VALID, "<html>ok</html>")
    assert any("日期" in item for item in failures)


def test_missing_section_is_rejected():
    text = VALID.replace("今日三句话", "今日摘要")
    failures = check_report(date(2026, 11, 14), text, "<html>ok</html>")
    assert any("今日三句话" in item for item in failures)


def test_short_or_empty_body_is_rejected():
    assert check_report(date(2026, 11, 14), "太短", "<html>ok</html>")
    assert check_report(date(2026, 11, 14), VALID, "   ")
