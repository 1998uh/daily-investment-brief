from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import date, datetime
import json
import textwrap
import time

from .config import ROOT, Settings
from .datetime_utils import brief_window, format_window_cn
from .ingest import build_coverage
from .llm import LLMError, chat_completion
from .models import Article, CoverageRow, GenerationResult


WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
REPORT_SOURCE_ORDER = ["雪球", "微博", "微信公众号"]


def generate_brief(articles: list[Article], brief_date: date, settings: Settings) -> GenerationResult:
    coverage = build_coverage(articles)
    if settings.has_llm:
        try:
            markdown = generate_with_llm(articles, coverage, brief_date, settings)
            return GenerationResult(markdown=markdown, used_llm=True, model=settings.model)
        except LLMError as exc:
            markdown = generate_fallback(articles, coverage, brief_date, settings, note=str(exc))
            return GenerationResult(markdown=markdown, used_llm=False, model="fallback")

    markdown = generate_fallback(articles, coverage, brief_date, settings)
    return GenerationResult(markdown=markdown, used_llm=False, model="fallback")


def generate_with_llm(
    articles: list[Article],
    coverage: list[CoverageRow],
    brief_date: date,
    settings: Settings,
) -> str:
    started_at = time.perf_counter()
    batch_prompt = read_template("batch_summary_prompt.md")
    final_prompt = read_template("final_brief_prompt.md")

    batches = chunked(articles, settings.batch_size)
    summaries = _summarize_batches(batches, settings, batch_prompt)
    print(
        f"[info] LLM batch summaries completed in {time.perf_counter() - started_at:.1f}s",
        flush=True,
    )

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
    print(f"[info] LLM total generation time: {time.perf_counter() - started_at:.1f}s", flush=True)
    return enforce_report_header(markdown, brief_date, settings, coverage)


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
        return [
            _summarize_single_batch(index, batch, total, settings, batch_prompt)
            for index, batch in enumerate(batches, start=1)
        ]

    results: list[dict | str] = ["" for _ in batches]
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_index = {
            executor.submit(_summarize_single_batch, index, batch, total, settings, batch_prompt): index - 1
            for index, batch in enumerate(batches, start=1)
        }
        for future in as_completed(future_to_index):
            results[future_to_index[future]] = future.result()
    return results


def _summarize_single_batch(
    index: int,
    batch: list[Article],
    total: int,
    settings: Settings,
    batch_prompt: str,
) -> dict | str:
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
    authors = "、".join(
        article.display_author for article in articles if article.display_author != "未知作者"
    )
    model_line = f"🤖 fallback（未调用模型）"
    if note:
        model_line += f"\n- ⚠ LLM 调用失败，已切换 fallback：{note}"

    header = build_report_header(brief_date, settings, coverage)
    markdown = f"""{header}

{chr(10).join(source_lines)}
- {model_line}

> 当前为本地 fallback 版本：用于验证项目流程、输入规范和输出样式。配置 `.env` 后会调用模型生成更接近样例的强叙事简报。

{chr(10).join(sections)}

## ⚔️ 观点碰撞

| 方向 | 代表来源 | 核心观察 |
|---|---|---|
| 🔺 偏积极 | 原文作者 | 提取到的积极表述会在模型版中聚合为多头逻辑。 |
| 🔻 偏谨慎 | 原文作者 | 风险提示、分歧和反身性担忧会在模型版中单独呈现。 |
| ⚖️ 需要跟踪 | 编辑归纳 | 第一版只整理观点；具体数据和政策变化需要人工决定是否核验。 |

## 💡 投资理念与金句

- “理解应对优于主观预判。”（样例保留句式，正式版会从原文提取）
- “涨多了，就是下跌的核心因素，其他都是故事。”（样例保留句式，正式版会从原文提取）

## 📋 数据覆盖与来源统计

{coverage_table}

**已覆盖作者**：{authors or "暂无"}

## 🎯 本期核心矛盾与下期关注

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
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
             下期验证变量                组合风险提示
```

### 📌 下期五大关注

1. A 股与港股核心指数能否延续当前方向。
2. 科技成长与红利资源之间的风格切换。
3. 港股流动性、南向资金和互联网权重表现。
4. 资源品价格、库存和产业链利润传导。
5. 样本作者中缺失声音是否改变主线判断。

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
    lines = ["| 来源 | 作者/账号 | 文章数 | 已覆盖作者 |", "|---|---:|---:|---|"]
    for row in coverage:
        authors = "、".join(row.authors) if row.authors else "-"
        lines.append(f"| {row.source} | {row.authors_total} | {row.articles_total} | {authors} |")
    return "\n".join(lines)


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
