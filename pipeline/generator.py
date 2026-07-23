from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
import json
import re
import textwrap
import time

from .cancel import PipelineCancelled, raise_if_cancelled
from .config import ROOT, Settings
from .datetime_utils import brief_window, format_window_cn
from .ingest import build_coverage, expected_authors_from_accounts
from .llm import LLMError, chat_completion
from .models import Article, CoverageRow, GenerationResult


WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
REPORT_SOURCE_ORDER = ["雪球", "微博", "微信公众号"]


def extract_prev_watch_list(brief_date: date) -> str:
    """从上一期 daily-brief.md 中提取「下期关注」章节内容。"""
    prev_date = brief_date - timedelta(days=1)
    prev_path = ROOT / "reports" / prev_date.strftime("%Y-%m-%d") / "daily-brief.md"
    if not prev_path.exists():
        return ""
    text = prev_path.read_text(encoding="utf-8")
    match = re.search(
        r"(?:##[^#\n]*下期关注[^\n]*\n)(.*?)(?=\n##|\Z)",
        text,
        re.DOTALL,
    )
    if not match:
        return ""
    return match.group(1).strip()


def build_direct_prompt(
    articles: list[Article],
    coverage: list[CoverageRow],
    brief_date: date,
    settings: Settings,
) -> str:
    """生成可直接喂给任意外部模型的完整 prompt（无需分批提炼）。"""
    direct_prompt = read_template("direct_brief_prompt.md")
    coverage_json = json.dumps(coverage_to_dicts(coverage), ensure_ascii=False, indent=2)
    articles_text = "\n\n".join(
        format_article(a, settings.max_chars_per_article) for a in articles
    )
    window_start, window_end = brief_window(
        brief_date,
        timezone_name=settings.timezone,
        start_time=settings.window_start,
        end_time=settings.window_end,
    )
    return direct_prompt.format(
        markets=settings.markets,
        window_label=format_window_cn(window_start, window_end),
        date_cn=format_date_cn(brief_date),
        weekday_cn=WEEKDAY_CN[brief_date.weekday()],
        session=_session_label(window_end),
        coverage_json=coverage_json,
        articles_text=articles_text,
        prev_watch_list=extract_prev_watch_list(brief_date),
    )


def synthesize_from_batches(
    summaries: list[dict | str],
    coverage: list[CoverageRow],
    brief_date: date,
    settings: Settings,
) -> str:
    """用已有批次 JSON 合成最终简报。可单独调用，不依赖文章输入。"""
    raise_if_cancelled()
    final_prompt = read_template("final_brief_prompt.md")
    coverage_json = json.dumps(coverage_to_dicts(coverage), ensure_ascii=False, indent=2)
    summaries_json = json.dumps(summaries, ensure_ascii=False, indent=2)
    window_start, window_end = brief_window(
        brief_date,
        timezone_name=settings.timezone,
        start_time=settings.window_start,
        end_time=settings.window_end,
    )
    final_user_prompt = final_prompt.format(
        markets=settings.markets,
        window_label=format_window_cn(window_start, window_end),
        date_cn=format_date_cn(brief_date),
        weekday_cn=WEEKDAY_CN[brief_date.weekday()],
        coverage_json=coverage_json,
        batch_summaries_json=summaries_json,
        session=_session_label(window_end),
        prev_watch_list=extract_prev_watch_list(brief_date),
    )

    print(f"[info] LLM final brief: {len(summaries)} batch summaries", flush=True)
    final_started_at = time.perf_counter()
    markdown = chat_completion(
        replace(settings, llm_max_tokens=None),
        [
            {"role": "system", "content": "你是中文每日投资简报主编。"},
            {"role": "user", "content": final_user_prompt},
        ],
        temperature=settings.temperature,
        label="final brief",
    )
    print(
        f"[info] LLM final brief completed in {time.perf_counter() - final_started_at:.1f}s",
        flush=True,
    )
    return enforce_report_header(markdown, brief_date, settings, coverage)


def generate_brief(
    articles: list[Article],
    brief_date: date,
    settings: Settings,
    accounts_path: Path | None = None,
    out_dir: Path | None = None,
) -> GenerationResult:
    raise_if_cancelled()
    expected = expected_authors_from_accounts(accounts_path) if accounts_path else None
    coverage = build_coverage(articles, expected)
    if settings.has_llm:
        try:
            markdown = generate_with_llm(articles, coverage, brief_date, settings, out_dir=out_dir)
            return GenerationResult(markdown=markdown, used_llm=True, model=settings.model)
        except LLMError as exc:
            print(f"[warn] LLM generation failed; using fallback: {exc}", flush=True)
            markdown = generate_fallback(articles, coverage, brief_date, settings, note=str(exc))
            return GenerationResult(markdown=markdown, used_llm=False, model="fallback")

    markdown = generate_fallback(articles, coverage, brief_date, settings)
    return GenerationResult(markdown=markdown, used_llm=False, model="fallback")


def generate_with_llm(
    articles: list[Article],
    coverage: list[CoverageRow],
    brief_date: date,
    settings: Settings,
    out_dir: Path | None = None,
) -> str:
    started_at = time.perf_counter()
    raise_if_cancelled()
    batch_prompt = read_template("batch_summary_prompt.md")

    batches = chunked_by_author(articles, settings.batch_max_chars)
    summaries = _summarize_batches(batches, settings, batch_prompt)
    print(
        f"[info] LLM batch summaries completed in {time.perf_counter() - started_at:.1f}s",
        flush=True,
    )

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        batches_path = out_dir / "batch-summaries.json"
        batches_path.write_text(
            json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[info] Batch summaries saved: {batches_path}", flush=True)

    return synthesize_from_batches(summaries, coverage, brief_date, settings)


def _summarize_batches(
    batches: list[list[Article]],
    settings: Settings,
    batch_prompt: str,
) -> list[dict | str]:
    if not batches:
        return []

    total = len(batches)
    worker_count = min(settings.llm_batch_concurrency, total)
    if worker_count == 1:
        results: list[dict | str] = []
        for index, batch in enumerate(batches, start=1):
            raise_if_cancelled()
            results.append(_summarize_single_batch(index, batch, total, settings, batch_prompt))
        return results

    results: list[dict | str] = ["" for _ in batches]
    executor = ThreadPoolExecutor(max_workers=worker_count)
    try:
        future_to_index = {
            executor.submit(_summarize_single_batch, index, batch, total, settings, batch_prompt): index - 1
            for index, batch in enumerate(batches, start=1)
        }
        pending = set(future_to_index)
        while pending:
            raise_if_cancelled()
            done, pending = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
            for future in done:
                results[future_to_index[future]] = future.result()
    except (KeyboardInterrupt, PipelineCancelled):
        for future in future_to_index:
            future.cancel()
        raise
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return results


def _summarize_single_batch(
    index: int,
    batch: list[Article],
    total: int,
    settings: Settings,
    batch_prompt: str,
) -> dict | str:
    raise_if_cancelled()
    print(f"[info] LLM batch summary {index}/{total}: {len(batch)} articles", flush=True)
    article_text = "\n\n".join(format_article(article, settings.max_chars_per_article) for article in batch)
    content = batch_prompt + "\n\n以下是本批文章：\n\n" + article_text
    started_at = time.perf_counter()
    response = chat_completion(
        settings,
        [
            {"role": "system", "content": "你是严谨的中文投研资料整理助手。"},
            {"role": "user", "content": content},
        ],
        temperature=0.1,
        label=f"batch summary {index}/{total}",
    )
    print(
        f"[info] LLM batch summary {index}/{total} completed in {time.perf_counter() - started_at:.1f}s",
        flush=True,
    )
    return parse_json_or_text(response)


def generate_fallback(
    articles: list[Article],
    coverage: list[CoverageRow],
    brief_date: date,
    settings: Settings,
    note: str | None = None,
) -> str:
    grouped = group_articles(articles)
    source_lines = [
        f"- 🟢 {row.source} {row.authors_total} 位作者 / {row.articles_total} 篇"
        for row in coverage
        if row.articles_total
    ]
    if not source_lines:
        source_lines = ["- ⚪ 暂无有效文章来源"]

    sections = []
    for section_name, section_articles in grouped.items():
        if not section_articles:
            continue
        bullets = []
        for article in section_articles[:8]:
            excerpt = first_meaningful_excerpt(article.content)
            bullets.append(
                f"- **{article.display_title}**（{article.source} / {article.display_author}）：{excerpt}"
            )
        sections.append(f"## {section_name}\n\n" + "\n".join(bullets))

    coverage_table = render_coverage_table(coverage)
    next_focus = render_next_focus(articles, coverage)
    authors = "、".join(
        article.display_author for article in articles if article.display_author != "未知作者"
    )
    model_line = "🤖 fallback（未调用模型）"
    if note:
        model_line += f"\n- ⚠ LLM 调用失败，已切换 fallback：{note}"

    header = build_report_header(brief_date, settings, coverage)
    markdown = f"""{header}

{chr(10).join(source_lines)}
- {model_line}

> 当前为本地 fallback 版本：用于验证项目流程、输入规范和输出样式。配置 `.env` 后会调用模型生成更接近样例的强叙事简报。

## 🧭 今日三句话

| 项目 | 内容 |
|---|---|
| 今日最重要变化 | 本期共整理 {len(articles)} 篇来源材料，先用高频主题和静默账号识别市场主线。 |
| 对投资假设的影响 | 需要把博主观点进一步写成可验证假设，而不是直接当成结论。 |
| 今日不做什么 | 不根据 fallback 摘要直接形成买卖动作；等待模型版或人工复核。 |

{chr(10).join(sections)}

## ⚔️ 观点碰撞

| 方向 | 代表来源 | 核心观察 |
|---|---|---|
| 🔺 偏积极 | 原文作者 | 提取到的积极表述会在模型版中聚合为多头逻辑。 |
| 🔻 偏谨慎 | 原文作者 | 风险提示、分歧和反身性担忧会在模型版中单独呈现。 |
| ⚖️ 需要跟踪 | 编辑归纳 | 第一版只整理观点；具体数据和政策变化需要人工决定是否核验。 |

## 📋 数据覆盖与来源统计

{coverage_table}

**已覆盖作者**：{authors or "暂无"}

## 🎯 本期核心矛盾

```text
                         本期文章观点池
                               │
               ┌───────────────┼───────────────┐
               │               │               │
          宏观流动性        A/H 股策略       行业景气线索
               │               │               │
               └───────────────┼───────────────┘
                               │
                        多空观点碰撞
```

{next_focus}

## 🧪 待验证假设

| 假设 | 支持证据 | 反证信号 | 验证期限 | 状态 |
|---|---|---|---|---|
| 高频讨论方向是否延续 | 本期文章主题聚合与下期关注条目 | 下一期相关讨论明显降温或核心作者转向 | 下一期 | 待验证 |
| 静默账号是否影响主线 | 数据覆盖表中的静默账号 | 静默账号回归后观点与本期主线相反 | 下一期 | 待验证 |

## ✍️ 我的判断区

> 这部分建议由本人手写，AI 不自动代填。

| 问题 | 我的回答 |
|---|---|
| 今天哪条信息最重要？ |  |
| 它改变了我什么判断？ |  |
| 我原来的看法是什么？ |  |
| 现在我的看法是什么？ |  |
| 接下来验证什么？ |  |
| 如果错了，什么信号说明我错了？ |  |
| 是否调整仓位/观察名单？ |  |

---

⚠ **免责声明**：本简报为原始文章与观点的结构化整理，不构成任何投资建议。市场有风险，投资需谨慎。

*Generated by daily-investment-brief · {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} · 数据来源：雪球 / 微信公众号 / 微博*
"""
    return markdown


def read_template(name: str) -> str:
    return (ROOT / "templates" / name).read_text(encoding="utf-8")


def format_article(article: Article, max_chars: int) -> str:
    content = article.content.strip()
    if len(content) > max_chars:
        content = content[:max_chars] + "\n...[截断]"
    return textwrap.dedent(
        f"""
        <article>
        source: {article.source}
        author: {article.display_author}
        title: {article.display_title}
        url: {article.url}
        published_at: {article.published_at}

        {content}
        </article>
        """
    ).strip()


def parse_json_or_text(text: str) -> dict | str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return cleaned


def coverage_to_dicts(coverage: list[CoverageRow]) -> list[dict]:
    return [
        {
            "source": row.source,
            "authors_total": row.authors_total,
            "articles_total": row.articles_total,
            "authors": row.authors,
            "expected_authors": row.expected_authors,
            "missing_authors": row.missing_authors,
        }
        for row in coverage
    ]


def enforce_report_header(
    markdown: str,
    brief_date: date,
    settings: Settings,
    coverage: list[CoverageRow],
) -> str:
    header = build_report_header(brief_date, settings, coverage)
    lines = markdown.strip().splitlines()
    if not lines:
        return header + "\n"

    had_heading = bool(lines and lines[0].startswith("# "))
    if had_heading:
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)

    if had_heading:
        while lines:
            stripped = lines[0].strip()
            if stripped == "---":
                lines.pop(0)
                break
            if not stripped or lines[0].startswith(">"):
                lines.pop(0)
                continue
            break
        while lines and not lines[0].strip():
            lines.pop(0)

    body = "\n".join(lines).strip()
    if not body:
        return header + "\n"
    return header + "\n\n" + body + "\n"


def build_report_header(
    brief_date: date,
    settings: Settings,
    coverage: list[CoverageRow],
) -> str:
    window_start, window_end = brief_window(
        brief_date,
        timezone_name=settings.timezone,
        start_time=settings.window_start,
        end_time=settings.window_end,
    )
    total = sum(row.articles_total for row in coverage)
    source_summary = "、".join(
        f"{row.source}（{row.articles_total}篇）"
        for row in ordered_coverage(coverage)
        if row.articles_total
    ) or "暂无有效来源"
    author_summary = " | ".join(
        f"{row.source} {row.authors_total} 位"
        for row in ordered_coverage(coverage)
        if row.articles_total
    ) or "暂无有效作者"
    date_cn = format_date_cn(brief_date)
    weekday_cn = WEEKDAY_CN[brief_date.weekday()]
    session = _session_label(window_end)
    window_label = format_window_cn(window_start, window_end)
    return textwrap.dedent(
        f"""\
        # 📊 每日投资简报 — {date_cn}（{weekday_cn}·{session}）

        > **数据来源**：{source_summary} | 共 **{total} 篇**文章
        > **覆盖时段**：{window_label}（北京时间）
        > **覆盖作者**：{author_summary}
        > **生成时间**：{date_cn} {session}

        ---
        """
    ).strip()


def ordered_coverage(coverage: list[CoverageRow]) -> list[CoverageRow]:
    order = {source: index for index, source in enumerate(REPORT_SOURCE_ORDER)}
    return sorted(coverage, key=lambda row: (order.get(row.source, len(order)), row.source))


def chunked(items: list[Article], size: int) -> list[list[Article]]:
    size = max(1, size)
    return [items[index : index + size] for index in range(0, len(items), size)]


def chunked_by_author(articles: list[Article], max_chars: int) -> list[list[Article]]:
    """按博主分组后，将小博主合并成不超过 max_chars 的批次。

    同一博主在不超限时保持同批，让 LLM 能看到完整的逻辑链；单个博主
    超限时按文章拆分，避免单个超大请求被中转站拒绝。
    """
    from collections import defaultdict

    # 按博主聚合，保留原始顺序中首次出现的顺序
    author_order: list[str] = []
    by_author: dict[str, list[Article]] = defaultdict(list)
    for article in articles:
        key = (article.source, article.author)
        if key not in by_author:
            author_order.append(key)
        by_author[key].append(article)

    def author_chars(key: tuple[str, str]) -> int:
        return sum(len(a.content) for a in by_author[key])

    batches: list[list[Article]] = []
    current: list[Article] = []
    current_chars = 0

    for key in author_order:
        group = by_author[key]
        group_chars = author_chars(key)
        if group_chars > max_chars:
            if current:
                batches.append(current)
                current = []
                current_chars = 0
            oversized: list[Article] = []
            oversized_chars = 0
            for article in group:
                article_chars = len(article.content)
                if oversized and oversized_chars + article_chars > max_chars:
                    batches.append(oversized)
                    oversized = []
                    oversized_chars = 0
                oversized.append(article)
                oversized_chars += article_chars
            if oversized:
                batches.append(oversized)
            continue
        # 若当前批次已有内容且加入此博主会超限，先提交当前批次
        if current and current_chars + group_chars > max_chars:
            batches.append(current)
            current = []
            current_chars = 0
        current.extend(group)
        current_chars += group_chars
        # 单博主本身超限，立即提交（单独成批）
        if current_chars >= max_chars:
            batches.append(current)
            current = []
            current_chars = 0

    if current:
        batches.append(current)

    return batches


def group_articles(articles: list[Article]) -> dict[str, list[Article]]:
    groups = {
        "🌍 宏观与大势": [],
        "📈 A 股与港股策略": [],
        "🤖 科技与成长": [],
        "🔋 资源与周期": [],
        "🏭 行业与个股速览": [],
    }
    keywords = {
        "📈 A 股与港股策略": ["a股", "港股", "恒生", "上证", "创业板", "策略", "市场"],
        "🤖 科技与成长": ["ai", "半导体", "算力", "芯片", "互联网", "科技", "成长"],
        "🔋 资源与周期": ["锂", "有色", "煤", "油", "黄金", "资源", "周期", "商品"],
        "🌍 宏观与大势": ["宏观", "利率", "流动性", "政策", "汇率", "地产", "信用"],
    }
    for article in articles:
        haystack = f"{article.title}\n{article.content}".lower()
        best_group = ""
        best_score = 0
        for group_name, group_keywords in keywords.items():
            score = sum(haystack.count(keyword.lower()) for keyword in group_keywords)
            if score > best_score:
                best_score = score
                best_group = group_name
        if best_group:
            groups[best_group].append(article)
        else:
            groups["🏭 行业与个股速览"].append(article)
    return groups


def first_meaningful_excerpt(content: str, max_len: int = 180) -> str:
    for raw_line in content.splitlines():
        line = raw_line.strip().lstrip("#>-*0123456789. ")
        if len(line) >= 12:
            return shorten(line, max_len)
    return shorten(content.replace("\n", " "), max_len)


def shorten(text: str, max_len: int) -> str:
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def render_coverage_table(coverage: list[CoverageRow]) -> str:
    lines = ["| 来源 | 已覆盖/配置 | 文章数 | 静默账号 |", "|---|---:|---:|---|"]
    for row in coverage:
        if row.expected_authors:
            cover = f"{row.authors_total}/{row.expected_authors}"
        else:
            cover = str(row.authors_total)
        missing = "、".join(row.missing_authors) if row.missing_authors else "-"
        lines.append(f"| {row.source} | {cover} | {row.articles_total} | {missing} |")
    return "\n".join(lines)


def render_next_focus(articles: list[Article], coverage: list[CoverageRow]) -> str:
    """fallback 版「下期关注」：从覆盖与高频板块机械生成，无 LLM 依赖。"""
    points: list[str] = []

    # 1. 静默账号：缺失声音可能改变主线
    silent = [name for row in coverage for name in row.missing_authors]
    if silent:
        sample = "、".join(silent[:5])
        suffix = " 等" if len(silent) > 5 else ""
        points.append(
            f"静默账号是否回归并改变主线判断：本期 {sample}{suffix} 未产出内容。"
        )

    # 2. 高频板块：复用 group_articles 的关键词命中分布
    grouped = group_articles(articles)
    ranked = sorted(
        ((name, items) for name, items in grouped.items() if items),
        key=lambda kv: len(kv[1]),
        reverse=True,
    )
    for name, items in ranked[:3]:
        clean_name = name.split(" ", 1)[-1] if " " in name else name
        points.append(f"{clean_name}方向能否延续（本期 {len(items)} 篇相关讨论）的后续验证。")

    if not points:
        points.append("样本作者整体方向是否在下一交易日得到验证。")

    numbered = "\n".join(f"{i}. {p}" for i, p in enumerate(points[:5], start=1))
    return "## 🎯 下期关注\n\n" + numbered


def format_date_cn(value: date) -> str:
    return f"{value.year}年{value.month}月{value.day}日"


def _session_label(window_end: datetime) -> str:
    """根据窗口结束时间判断盘前/盘中/盘后。"""
    hour_minute = window_end.hour * 60 + window_end.minute
    if hour_minute < 9 * 60 + 30:
        return "盘前"
    elif hour_minute >= 15 * 60:
        return "盘后"
    else:
        return "盘中"
