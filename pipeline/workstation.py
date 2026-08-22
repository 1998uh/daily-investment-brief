from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import calendar
import json

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


def generate_journal_draft(
    entry_date: date,
    *,
    root: Path = ROOT,
) -> Path | None:
    """功能 3: 自动生成 journal 首稿

    基于当日的 daily-brief.md 用 LLM 生成首稿。
    如果日报不存在或 LLM 调用失败，返回 None。
    """
    report_path = root / "reports" / entry_date.isoformat() / "daily-brief.md"
    if not report_path.exists():
        return None

    try:
        report_content = report_path.read_text(encoding="utf-8")
    except Exception:
        return None

    # 构建 prompt
    prompt = f"""请阅读以下每日投资简报，为我生成一份个人判断记录的首稿。

要求：
1. 提取今日最重要的 2-3 个信息点
2. 识别文中最强的观点分歧（多空碰撞）
3. 保持精简，每个字段 1-2 句话即可
4. 如果某个字段无法从日报中提取，留空

请按以下 JSON 格式输出：

```json
{{
  "most_important_info": "今日最重要信息的 1-2 句总结",
  "judgment_changed": "它改变了我什么判断（如果没有明确改变，留空）",
  "previous_view": "我原来的看法（如果日报中没有提及，留空）",
  "current_view": "我现在的看法（基于今日信息）",
  "next_verification": "接下来需要验证什么",
  "error_signal": "如果我的判断错了，什么信号会说明",
  "position_adjustment": "是否需要调整仓位或观察名单",
  "mistakes_reminder": "今日值得提醒的风险点或错题"
}}
```

日报内容：

{report_content}
"""

    try:
        from .llm import chat_completion
        from .config import get_settings

        settings = get_settings()
        response = chat_completion(
            settings,
            [
                {"role": "system", "content": "你是投资决策助手，帮助用户提炼日报核心信息。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            label="journal draft",
        )

        # 提取 JSON
        draft_data = _extract_json_from_response(response)
        if not draft_data:
            return None

        # 生成 journal 内容
        journal_content = _render_journal_with_draft(entry_date, draft_data)
        journal_path_target = journal_path(entry_date, root=root)
        journal_path_target.parent.mkdir(parents=True, exist_ok=True)
        journal_path_target.write_text(journal_content, encoding="utf-8")
        return journal_path_target

    except Exception:
        return None


def _extract_json_from_response(response: str) -> dict | None:
    """从 LLM 响应中提取 JSON"""
    # 尝试提取代码块中的 JSON
    json_match = response.find("```json")
    if json_match != -1:
        end_match = response.find("```", json_match + 7)
        if end_match != -1:
            json_str = response[json_match + 7:end_match].strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

    # 尝试直接解析整个响应
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return None


def _render_journal_with_draft(entry_date: date, draft: dict) -> str:
    """用 LLM 生成的首稿渲染 journal"""
    date_label = entry_date.isoformat()
    return f"""# {date_label} 个人投资判断

## 今日最重要信息

{draft.get("most_important_info", "")}

## 它改变了我什么判断

{draft.get("judgment_changed", "")}

## 我原来的看法

{draft.get("previous_view", "")}

## 我现在的看法

{draft.get("current_view", "")}

## 接下来验证什么

{draft.get("next_verification", "")}

## 如果错了，什么信号说明我错了

{draft.get("error_signal", "")}

## 是否调整仓位/观察名单

{draft.get("position_adjustment", "")}

## 今日错题或提醒

{draft.get("mistakes_reminder", "")}

---

> 此首稿由 LLM 基于日报自动生成，请根据个人判断修改和完善。
"""
