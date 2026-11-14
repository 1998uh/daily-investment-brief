from datetime import date

from pipeline.report_gate import check_report

VALID = "# 📊 每日投资简报 — 2026年11月14日（周六·盘前）\n\n" + (
    "## 今日三句话\n\n## 一、⚡ 一页速览\n\n## 二、📈 大盘量能趋势\n\n"
    "## 三、⚡ 今日注意事项与投资总结\n\n"
    "## 数据覆盖情况\n\n" + "正文" * 1600
)


def test_valid_report_has_no_failures():
    assert check_report(date(2026, 11, 14), VALID, "<html>ok</html>") == []


def test_wrong_date_is_rejected():
    failures = check_report(date(2026, 11, 15), VALID, "<html>ok</html>")
    assert any("日期" in item for item in failures)


def test_missing_one_page_summary_is_rejected():
    text = VALID.replace("一页速览", "今日摘要")
    failures = check_report(date(2026, 11, 14), text, "<html>ok</html>")
    assert any("一页速览" in item for item in failures)


def test_missing_section_is_rejected():
    text = VALID.replace("今日三句话", "今日摘要")
    failures = check_report(date(2026, 11, 14), text, "<html>ok</html>")
    assert any("今日三句话" in item for item in failures)


def test_short_or_empty_body_is_rejected():
    short_failures = check_report(date(2026, 11, 14), "太短", "<html>ok</html>")
    assert any("长度不足" in item for item in short_failures)

    empty_html_failures = check_report(date(2026, 11, 14), VALID, "   ")
    assert "daily-brief.html 为空" in empty_html_failures
