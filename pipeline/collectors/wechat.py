from __future__ import annotations

from datetime import datetime
import email.utils
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from .accounts import Account
from .base import CollectedItem, CollectionLog
from .http import HttpClient, clean_text, extract_title, strip_html
from ..cancel import raise_if_cancelled
from ..config import Settings
from ..datetime_utils import parse_datetime


def collect_wechat(
    account: Account,
    *,
    window_start: datetime,
    window_end: datetime,
    settings: Settings,
    limit: int,
    include_undated: bool,
    log: CollectionLog,
) -> list[CollectedItem]:
    raise_if_cancelled()
    client = HttpClient(cookie_env="WECHAT_COOKIE")
    items: list[CollectedItem] = []

    if account.rss_url:
        items.extend(
            collect_wechat_rss(
                account,
                client=client,
                window_start=window_start,
                window_end=window_end,
                settings=settings,
                include_undated=include_undated,
                limit=limit,
            )
        )

    for url in account.urls:
        raise_if_cancelled()
        if len(items) >= limit:
            break
        try:
            item = fetch_wechat_article(account, url, client=client, settings=settings, reference=window_end)
        except Exception as exc:
            log.add_warning(f"微信公众号 / {account.name}: 抓取文章失败 {url}: {exc}")
            continue
        if item.published_at is None:
            if include_undated:
                items.append(item)
            continue
        if window_start <= item.published_at < window_end:
            items.append(item)

    if not account.rss_url and not account.urls:
        log.add_warning(f"微信公众号 / {account.name}: 缺少 urls 或 rss_url，已跳过")
    else:
        log.add_info(f"微信公众号 / {account.name}: 采集 {len(items)} 条")

    return items[:limit]


def collect_wechat_rss(
    account: Account,
    *,
    client: HttpClient,
    window_start: datetime,
    window_end: datetime,
    settings: Settings,
    include_undated: bool,
    limit: int,
) -> list[CollectedItem]:
    raise_if_cancelled()
    text = client.get_text(account.rss_url)
    root = ET.fromstring(text)
    items: list[CollectedItem] = []

    for node in root.findall(".//item"):
        raise_if_cancelled()
        if len(items) >= limit:
            break
        title = find_xml_text(node, "title") or account.name
        link = find_xml_text(node, "link")
        pub_date = find_xml_text(node, "pubDate") or find_xml_text(node, "published")
        content = (
            find_xml_text(node, "{http://purl.org/rss/1.0/modules/content/}encoded")
            or find_xml_text(node, "description")
            or ""
        )
        published_at = parse_rss_datetime(pub_date, reference=window_end, settings=settings)
        if published_at is None and not include_undated:
            continue
        if published_at and not (window_start <= published_at < window_end):
            continue
        items.append(
            CollectedItem(
                source="微信公众号",
                author=account.name,
                title=clean_text(title) or account.name,
                url=link,
                published_at=published_at,
                content=clean_text(content),
                provider="wechat_rss",
            )
        )

    return items


def collect_wechat_manual_urls(
    urls_path: Path,
    *,
    window_start: datetime,
    window_end: datetime,
    settings: Settings,
    include_undated: bool,
    log: CollectionLog,
) -> list[CollectedItem]:
    if not urls_path.exists():
        return []

    client = HttpClient(cookie_env="WECHAT_COOKIE")
    items: list[CollectedItem] = []
    seen_urls: set[str] = set()
    for author, url in parse_manual_url_pool(urls_path):
        raise_if_cancelled()
        if url in seen_urls:
            continue
        seen_urls.add(url)
        account = Account(source="微信公众号", name=author, urls=[url])
        try:
            item = fetch_wechat_article(account, url, client=client, settings=settings, reference=window_end)
        except Exception as exc:
            log.add_warning(f"微信公众号 / {author}: 手工 URL 抓取失败 {url}: {exc}")
            continue
        if item.published_at is None:
            if include_undated:
                items.append(item)
            continue
        if window_start <= item.published_at < window_end:
            items.append(item)

    if items:
        log.add_info(f"微信公众号 / 手工 URL 池: 采集 {len(items)} 条")
    return items


def parse_manual_url_pool(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        author = "手工公众号"
        url = line
        if "|" in line:
            left, right = line.split("|", 1)
            if left.strip() and right.strip():
                author = left.strip()
                url = right.strip()
        elif " " in line:
            left, right = line.split(None, 1)
            if right.startswith("http"):
                author = left.strip()
                url = right.strip()
        if url.startswith("http"):
            entries.append((author, url))
    return entries


def fetch_wechat_article(
    account: Account,
    url: str,
    *,
    client: HttpClient,
    settings: Settings,
    reference: datetime,
) -> CollectedItem:
    raise_if_cancelled()
    html = client.get_text(url)
    title = extract_title(html) or account.name
    content_html = extract_wechat_content_html(html) or html
    content = strip_html(content_html)
    published_at = extract_wechat_publish_time(html, reference=reference, settings=settings)
    return CollectedItem(
        source="微信公众号",
        author=account.name,
        title=title,
        url=url,
        published_at=published_at,
        content=content,
        provider="wechat_manual_url",
    )


def extract_wechat_content_html(html: str) -> str:
    match = re.search(
        r'<div[^>]+id=["\']js_content["\'][^>]*>(.*?)(?:<script|<div[^>]+class=["\']rich_media_tool)',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    return match.group(1) if match else ""


def extract_wechat_publish_time(
    html: str,
    *,
    reference: datetime,
    settings: Settings,
) -> datetime | None:
    patterns = [
        r'var\s+ct\s*=\s*["\'](\d+)["\']',
        r'publish_time\s*=\s*["\']([^"\']+)["\']',
        r'<em[^>]+id=["\']publish_time["\'][^>]*>(.*?)</em>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if match:
            return parse_datetime(
                clean_text(match.group(1)),
                reference=reference,
                timezone_name=settings.timezone,
            )
    return None


def parse_rss_datetime(value: str, *, reference: datetime, settings: Settings) -> datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return parse_datetime(value, reference=reference, timezone_name=settings.timezone)
    if parsed.tzinfo is None:
        return parse_datetime(parsed.isoformat(), reference=reference, timezone_name=settings.timezone)
    return parsed.astimezone(reference.tzinfo)


def find_xml_text(node: ET.Element, tag: str) -> str:
    found = node.find(tag)
    if found is not None and found.text:
        return found.text.strip()
    for child in node:
        if child.tag.endswith(tag) and child.text:
            return child.text.strip()
    return ""
