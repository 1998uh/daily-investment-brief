from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import json
import re
import hashlib

from .models import Article, CoverageRow


FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text.strip()

    meta: dict[str, str] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, text[match.end() :].strip()


def load_markdown(path: Path) -> Article:
    text = path.read_text(encoding="utf-8")
    meta, content = parse_front_matter(text)
    return Article(
        path=path,
        source=meta.get("source", infer_source(path)),
        author=meta.get("author", ""),
        title=meta.get("title", path.stem),
        url=meta.get("url", ""),
        published_at=meta.get("published_at", ""),
        content=content,
    )


def load_json(path: Path) -> Article:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Article(
        path=path,
        source=str(payload.get("source") or infer_source(path)),
        author=str(payload.get("author") or ""),
        title=str(payload.get("title") or path.stem),
        url=str(payload.get("url") or ""),
        published_at=str(payload.get("published_at") or ""),
        content=str(payload.get("content") or ""),
    )


def infer_source(path: Path) -> str:
    text = " ".join(path.parts).lower()
    if "xueqiu" in text or "雪球" in text:
        return "雪球"
    if "wechat" in text or "weixin" in text or "公众号" in text or "微信" in text:
        return "微信公众号"
    if "weibo" in text or "微博" in text:
        return "微博"
    return "未知来源"


def load_articles(source_dir: Path) -> list[Article]:
    if not source_dir.exists():
        raise FileNotFoundError(f"source directory not found: {source_dir}")

    articles: list[Article] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".md":
            articles.append(load_markdown(path))
        elif suffix == ".json":
            articles.append(load_json(path))

    return dedupe_articles([article for article in articles if article.content.strip()])


def dedupe_articles(articles: list[Article]) -> list[Article]:
    seen: set[str] = set()
    unique: list[Article] = []
    for article in articles:
        key = article.url.strip() or "|".join(
            [
                article.source.strip(),
                article.author.strip(),
                article.title.strip(),
                hashlib.sha1(article.content[:2000].encode("utf-8")).hexdigest(),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)
    return unique


def build_coverage(articles: list[Article]) -> list[CoverageRow]:
    authors_by_source: dict[str, set[str]] = defaultdict(set)
    count_by_source: dict[str, int] = defaultdict(int)

    for article in articles:
        count_by_source[article.source] += 1
        authors_by_source[article.source].add(article.display_author)

    rows: list[CoverageRow] = []
    for source in ["雪球", "微信公众号", "微博"]:
        authors = sorted(authors_by_source.get(source, set()))
        rows.append(
            CoverageRow(
                source=source,
                authors_total=len(authors),
                articles_total=count_by_source.get(source, 0),
                authors=authors,
            )
        )

    for source in sorted(set(count_by_source) - {"雪球", "微信公众号", "微博"}):
        authors = sorted(authors_by_source[source])
        rows.append(
            CoverageRow(
                source=source,
                authors_total=len(authors),
                articles_total=count_by_source[source],
                authors=authors,
            )
        )

    return rows
