from __future__ import annotations

from datetime import date


REQUIRED_SECTIONS: tuple[str, ...] = (
    "今日三句话",
    "一页速览",
    "大盘量能趋势",
    "今日注意事项",
    "数据覆盖情况",
    "博主看好方向汇总",
)

MIN_BODY_CHARS = 3000


def _first_heading(markdown: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped
    return ""


def check_report(report_date: date, md_text: str, html_text: str) -> list[str]:
    """Return human-readable failures for a daily brief that is unsafe to send."""
    failures: list[str] = []
    body = md_text.strip()
    if not body:
        failures.append("daily-brief.md 为空")
    elif len(body) < MIN_BODY_CHARS:
        failures.append(f"正文长度不足 {MIN_BODY_CHARS} 字符")

    heading = _first_heading(md_text)
    date_cn = f"{report_date.year}年{report_date.month}月{report_date.day}日"
    if report_date.isoformat() not in heading and date_cn not in heading:
        failures.append(f"标题日期与报告日期 {report_date.isoformat()} 不一致")

    for section in REQUIRED_SECTIONS:
        if section not in md_text:
            failures.append(f"缺少章节: {section}")

    if not html_text.strip():
        failures.append("daily-brief.html 为空")

    return failures
