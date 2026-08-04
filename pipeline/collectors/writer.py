from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import hashlib
import re

from .base import CollectedItem

SOURCE_SLUGS = {
    "雪球": "xueqiu",
    "微信公众号": "wechat",
    "微博": "weibo",
}

_REPLY_RE = re.compile(r"^回复[@\[]")


def write_items(items: list[CollectedItem], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    reply_items = [item for item in items if is_reply_item(item)]
    normal_items = [item for item in items if not is_reply_item(item)]

    written = _write_normal_items(normal_items, out_dir)
    written.extend(_write_reply_groups(reply_items, out_dir))
    return written


def is_reply_item(item: CollectedItem) -> bool:
    """判断是否为"回复"类内容（同作者同天的回复会合并成一个文件）。"""
    return bool(_REPLY_RE.match(item.content.strip()) or _REPLY_RE.match(item.title.strip()))


def _write_normal_items(items: list[CollectedItem], out_dir: Path) -> list[Path]:
    written: list[Path] = []
    existing = load_existing_files(out_dir)  # key -> (path, content_length)

    for item in items:
        key = item.url.strip() or content_key(item)
        new_content = render_markdown(item)
        new_body_len = len(item.content.strip())

        if key in existing:
            old_path, old_body_len = existing[key]
            if new_body_len > old_body_len * 1.2:
                # 新内容明显更长（>20%），覆盖旧文件
                old_path.write_text(new_content, encoding="utf-8")
                existing[key] = (old_path, new_body_len)
                written.append(old_path)
            continue

        filename = make_filename(item)
        path = unique_path(out_dir / filename)
        path.write_text(new_content, encoding="utf-8")
        existing[key] = (path, new_body_len)
        written.append(path)

    return written


def _write_reply_groups(items: list[CollectedItem], out_dir: Path) -> list[Path]:
    written: list[Path] = []
    groups: dict[tuple[str, str, str], list[CollectedItem]] = defaultdict(list)
    for item in items:
        groups[_reply_group_key(item)].append(item)

    for (source, author, date_str), group_items in groups.items():
        group_items.sort(key=lambda i: i.published_at or datetime.min)
        content = render_reply_group_markdown(source, author, date_str, group_items)
        path = out_dir / make_reply_group_filename(source, author, date_str)
        if path.exists() and path.read_text(encoding="utf-8", errors="replace") == content:
            continue
        path.write_text(content, encoding="utf-8")
        written.append(path)

    return written


def _reply_group_key(item: CollectedItem) -> tuple[str, str, str]:
    date_str = item.published_at.strftime("%Y-%m-%d") if item.published_at else "undated"
    return (item.source, item.author, date_str)


def render_reply_group_markdown(
    source: str, author: str, date_str: str, items: list[CollectedItem]
) -> str:
    sections = []
    for item in items:
        time_str = item.published_at.strftime("%H:%M:%S") if item.published_at else ""
        header = f"## {time_str} [查看原文]({item.url})" if item.url else f"## {time_str}"
        sections.append(f"{header}\n\n{item.content.strip()}")
    body = "\n\n---\n\n".join(sections)

    return f"""---
source: {source}
author: {author}
title: {escape_front_matter(author)} 回复合集 - {date_str}
url:
published_at: {date_str}
provider: xueqiu_reply_digest
collected_at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
---

{body}
"""


def make_reply_group_filename(source: str, author: str, date_str: str) -> str:
    source_slug = SOURCE_SLUGS.get(source, "source")
    name_slug = slugify(author, 20)
    digest = hashlib.sha1(f"{source}|{author}|{date_str}|reply".encode("utf-8")).hexdigest()[:8]
    return f"{source_slug}-{name_slug}-回复合集-{date_str}-{digest}.md"


def load_existing_files(out_dir: Path) -> dict[str, tuple[Path, int]]:
    """加载已有文件的 key -> (path, 正文长度) 映射。"""
    files: dict[str, tuple[Path, int]] = {}
    for path in out_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        url_match = re.search(r"^url:\s*(.*?)$", text, re.MULTILINE)
        if url_match and url_match.group(1).strip():
            key = url_match.group(1).strip()
        else:
            key = hashlib.sha1(text.encode("utf-8")).hexdigest()
        # 正文在 front matter 之后（第二个 --- 之后）
        parts = text.split("---", 2)
        body = parts[2].strip() if len(parts) >= 3 else text
        files[key] = (path, len(body))
    return files


def render_markdown(item: CollectedItem) -> str:
    published = item.published_at.strftime("%Y-%m-%d %H:%M:%S") if item.published_at else ""
    return f"""---
source: {item.source}
author: {item.author}
title: {escape_front_matter(item.title)}
url: {item.url}
published_at: {published}
provider: {item.provider}
collected_at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
---

{item.content.strip()}
"""


def make_filename(item: CollectedItem) -> str:
    source_slug = SOURCE_SLUGS.get(item.source, "source")
    name_slug = slugify(item.author, 20)
    title_slug = slugify(item.title, 30)
    digest = hashlib.sha1((item.url or item.title or item.content[:200]).encode("utf-8")).hexdigest()[:8]
    return f"{source_slug}-{name_slug}-{title_slug}-{digest}.md"


def slugify(text: str, max_len: int = 30) -> str:
    """将中英文文本转为适合文件名的 slug，保留中文字符。"""
    text = re.sub(r"[^\w一-鿿]+", "-", text.strip())
    text = text.strip("-")
    if not text:
        return "unknown"
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"unable to find unique file name for {path}")


def content_key(item: CollectedItem) -> str:
    return hashlib.sha1(
        "|".join([item.source, item.author, item.title, item.content[:2000]]).encode("utf-8")
    ).hexdigest()


def escape_front_matter(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ").strip()
