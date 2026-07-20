from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import re

from .base import CollectedItem


def write_items(items: list[CollectedItem], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
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
    source_slug = {
        "雪球": "xueqiu",
        "微信公众号": "wechat",
        "微博": "weibo",
    }.get(item.source, "source")
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
