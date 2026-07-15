from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import calendar

from .config import ROOT


@dataclass(frozen=True)
class CreatedFile:
    path: Path
    created: bool


def create_journal_entry(
    entry_date: date,
    *,
    root: Path = ROOT,
    overwrite: bool = False,
) -> CreatedFile:
    path = journal_path(entry_date, root=root)
    return _write_once(path, render_journal_entry(entry_date), overwrite=overwrite)


def create_weekly_review(
    iso_week: str,
    *,
    root: Path = ROOT,
    overwrite: bool = False,
) -> CreatedFile:
    year, week = parse_iso_week(iso_week)
    start = date.fromisocalendar(year, week, 1)
    end = date.fromisocalendar(year, week, 7)
    path = root / "reviews" / "weekly" / f"{year}-W{week:02d}.md"
    content = render_weekly_review(year, week, start, end, root=root)
    return _write_once(path, content, overwrite=overwrite)


def create_monthly_review(
    month: str,
    *,
    root: Path = ROOT,
    overwrite: bool = False,
) -> CreatedFile:
    year_str, month_str = month.split("-", 1)
    year = int(year_str)
    month_num = int(month_str)
    path = root / "reviews" / "monthly" / f"{year}-{month_num:02d}.md"
    content = render_monthly_review(year, month_num, root=root)
    return _write_once(path, content, overwrite=overwrite)


def ensure_knowledge_base(*, root: Path = ROOT) -> list[CreatedFile]:
    created: list[CreatedFile] = []
    created.append(
        _write_once(
            root / "knowledge" / "themes" / "_template.md",
            render_theme_template(),
            overwrite=False,
        )
    )
    created.append(
        _write_once(
            root / "knowledge" / "companies" / "_template.md",
            render_company_template(),
            overwrite=False,
        )
    )
    created.append(
        _write_once(
            root / "knowledge" / "mistakes" / "_template.md",
            render_mistake_template(),
            overwrite=False,
        )
    )
    return created


def journal_path(entry_date: date, *, root: Path = ROOT) -> Path:
    return (
        root
        / "journal"
        / f"{entry_date.year:04d}"
        / f"{entry_date.month:02d}"
        / f"{entry_date.isoformat()}.md"
    )


def render_journal_entry(entry_date: date) -> str:
    date_label = entry_date.isoformat()
    return f"""# {date_label} 个人投资判断

## 今日最重要信息


## 它改变了我什么判断


## 我原来的看法


## 我现在的看法


## 接下来验证什么


## 如果错了，什么信号说明我错了


## 是否调整仓位/观察名单


## 今日错题或提醒


---

> 写作建议：每天只写 3-7 句话，重点记录判断过程，不追求长。
"""


def render_weekly_review(
    year: int,
    week: int,
    start: date,
    end: date,
    *,
    root: Path = ROOT,
) -> str:
    days = list(_date_range(start, end))
    report_links = _existing_daily_links(days, "reports", "daily-brief.md", root=root)
    journal_links = _existing_journal_links(days, root=root)
    return f"""# {year}-W{week:02d} 投资复盘

> 覆盖日期：{start.isoformat()} ~ {end.isoformat()}

## 本周材料索引

### 日报

{report_links}

### 个人判断

{journal_links}

## 本周市场主线


## 本周最重要的 5 个变化


## 上周假设验证结果


## 我的判断正确的地方


## 我的判断错误的地方


## 本周新增观察名单


## 本周删除/降权观察名单


## 下周待验证假设

| 假设 | 支持证据 | 反证信号 | 验证期限 | 状态 |
|---|---|---|---|---|
|  |  |  |  | 待验证 |

## 错题本


---

> 复盘重点：不是总结新闻，而是判断“哪些假设被验证，哪些被证伪，哪些只是噪音”。
"""


def render_monthly_review(year: int, month_num: int, *, root: Path = ROOT) -> str:
    first = date(year, month_num, 1)
    last = date(year, month_num, calendar.monthrange(year, month_num)[1])
    weekly_links = _existing_weekly_links(first, last, root=root)
    return f"""# {year}-{month_num:02d} 月度复盘

## 本月周复盘索引

{weekly_links}

## 本月主线


## 本月真正改变长期判断的事情


## 本月表现最强/最弱方向


## 我的主要错误


## 我的能力短板


## 下月重点跟踪主题


## 长期知识库更新


---

> 月度复盘重点：把 4-5 篇周复盘压缩成少数长期判断和可复用经验。
"""


def render_theme_template() -> str:
    return """# 主题名称

## 当前核心判断

## 关键跟踪指标

## 支持证据

## 反证信号

## 重要历史记录

## 相关日报/周报链接
"""


def render_company_template() -> str:
    return """# 公司名称

## 当前核心判断

## 商业模式与关键变量

## 财务与估值观察

## 支持证据

## 反证信号

## 重要公告/财报记录

## 相关日报/周报链接
"""


def render_mistake_template() -> str:
    return """# 错误类型

## 典型表现

## 最近案例

## 当时为什么会错

## 下次如何避免

## 相关记录
"""


def parse_iso_week(value: str) -> tuple[int, int]:
    normalized = value.upper()
    if "-W" in normalized:
        year_str, week_str = normalized.split("-W", 1)
    elif "W" in normalized:
        year_str, week_str = normalized.split("W", 1)
    else:
        year_str, week_str = normalized.split("-", 1)
    return int(year_str), int(week_str)


def _write_once(path: Path, content: str, *, overwrite: bool) -> CreatedFile:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return CreatedFile(path=path, created=False)
    path.write_text(content, encoding="utf-8")
    return CreatedFile(path=path, created=True)


def _date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _existing_daily_links(
    days: list[date],
    directory: str,
    filename: str,
    *,
    root: Path,
) -> str:
    lines = []
    for day in days:
        path = root / directory / day.isoformat() / filename
        if path.exists():
            lines.append(f"- [{day.isoformat()}](../../{directory}/{day.isoformat()}/{filename})")
    return "\n".join(lines) if lines else "- 暂无已生成日报"


def _existing_journal_links(days: list[date], *, root: Path) -> str:
    lines = []
    for day in days:
        path = journal_path(day, root=root)
        if path.exists():
            lines.append(
                f"- [{day.isoformat()}](../../journal/{day.year:04d}/{day.month:02d}/{day.isoformat()}.md)"
            )
    return "\n".join(lines) if lines else "- 暂无个人判断记录"


def _existing_weekly_links(first: date, last: date, *, root: Path) -> str:
    seen: set[tuple[int, int]] = set()
    lines: list[str] = []
    for day in _date_range(first, last):
        iso = day.isocalendar()
        key = (iso.year, iso.week)
        if key in seen:
            continue
        seen.add(key)
        path = root / "reviews" / "weekly" / f"{iso.year}-W{iso.week:02d}.md"
        if path.exists():
            lines.append(f"- [{iso.year}-W{iso.week:02d}](../weekly/{iso.year}-W{iso.week:02d}.md)")
    return "\n".join(lines) if lines else "- 暂无已生成周复盘"


def default_current_week() -> str:
    today = date.today()
    iso = today.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def default_current_month() -> str:
    return datetime.now().strftime("%Y-%m")
