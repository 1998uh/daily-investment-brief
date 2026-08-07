from __future__ import annotations

from datetime import datetime
import email.utils
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from .accounts import Account
from .base import CollectedItem, CollectionLog
from .http import HttpClient, clean_text, extract_title, strip_html
from ..cancel import raise_if_cancelled
from ..config import Settings
from ..datetime_utils import parse_datetime

_WEREAD_BASE = "https://weread.qq.com"
_WEREAD_ARTICLES = _WEREAD_BASE + "/web/mp/articles"
_WEREAD_CONTENT = _WEREAD_BASE + "/web/mp/content"
_WEREAD_READER_BASE = _WEREAD_BASE + "/web/mp/reader"

_WEREAD_HEADERS_BASE = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Host": "weread.qq.com",
}

# WeRead 服务端校验 Referer 必须来自 reader 页面，否则会触发 session 失效
def _weread_headers(book_id: str) -> dict:
    return {**_WEREAD_HEADERS_BASE, "Referer": f"{_WEREAD_READER_BASE}/{book_id}"}

_MAX_CONTENT_PER_ACCOUNT = 5


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

    # 优先尝试微信读书 Web API（需要 account.uid 存公众号 book_id，且设置 WEREAD_COOKIE）
    weread_book_id = account.uid if account.uid and account.uid.startswith("MP_WXS_") else ""
    if weread_book_id and os.getenv("WEREAD_COOKIE"):
        try:
            items.extend(
                collect_wechat_weread(
                    account,
                    book_id=weread_book_id,
                    window_start=window_start,
                    window_end=window_end,
                    settings=settings,
                    include_undated=include_undated,
                    limit=limit,
                    log=log,
                )
            )
        except Exception as exc:
            log.add_warning(f"微信公众号 / {account.name}: 微信读书接口失败，降级到 RSS/URL: {exc}")

    # RSS 通道（weread 未配置或失败时使用）
    if not items and account.rss_url:
        try:
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
        except Exception as exc:
            log.add_warning(f"微信公众号 / {account.name}: RSS 失败: {exc}")

    # 手动 URL 通道（兜底）
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

    if not weread_book_id and not account.rss_url and not account.urls:
        log.add_warning(f"微信公众号 / {account.name}: 缺少 uid(book_id)/urls/rss_url，已跳过")
    else:
        log.add_info(f"微信公众号 / {account.name}: 采集 {len(items)} 条")

    return items[:limit]


def collect_wechat_weread(
    account: Account,
    *,
    book_id: str,
    window_start: datetime,
    window_end: datetime,
    settings: Settings,
    include_undated: bool,
    limit: int,
    log: CollectionLog,
) -> list[CollectedItem]:
    """通过微信读书 Web API 获取公众号文章。需设置 WEREAD_COOKIE 环境变量。"""
    raise_if_cancelled()
    client = HttpClient(cookie_env="WEREAD_COOKIE")
    headers = _weread_headers(book_id)
    items: list[CollectedItem] = []
    offset = 0
    content_fetched = 0

    # session probe：先验证 cookie 是否有效，避免用失效 session 跑整个采集
    probe = client.get_json(f"{_WEREAD_ARTICLES}?bookId={book_id}&offset=0", headers=headers)
    err = probe.get("errCode", 0)
    if err == -2010:
        raise RuntimeError("WEREAD_COOKIE 已失效（-2010），请重新运行 auth-login --platform weread")
    if err == -2041:
        raise RuntimeError(f"公众号 {account.name} 未同步到账号（-2041），请在 WeRead App 里打开一篇文章")

    while len(items) < limit:
        raise_if_cancelled()
        url = f"{_WEREAD_ARTICLES}?bookId={book_id}&offset={offset}"
        data = client.get_json(url, headers=headers)

        articles = data.get("reviews") or data.get("articles") or []
        if not articles:
            break

        found_old = False
        for entry in articles:
            raise_if_cancelled()
            if len(items) >= limit:
                break

            # 实际结构：{createTime, subReviews: [{reviewId, review: {reviewId, mpInfo: {title, ...}, ...}}]}
            sub_reviews = entry.get("subReviews") or []
            first_sub = sub_reviews[0] if sub_reviews else {}
            review = first_sub.get("review") or first_sub
            if not review:
                review = entry.get("review") or entry

            review_id = review.get("reviewId") or review.get("review_id") or ""
            mp_info = review.get("mpInfo") or review.get("mp_info") or {}
            title = mp_info.get("title") or review.get("title") or ""
            mp_url = mp_info.get("url") or ""
            create_time = (
                mp_info.get("time")
                or review.get("createTime")
                or review.get("create_time")
                or entry.get("createTime")
                or 0
            )

            published_at: datetime | None = None
            if create_time:
                try:
                    published_at = datetime.fromtimestamp(int(create_time), tz=window_end.tzinfo)
                except (ValueError, OSError):
                    pass

            if published_at and published_at < window_start:
                found_old = True
                break

            if published_at and published_at >= window_end:
                continue

            if published_at is None and not include_undated:
                continue

            # 拉取正文：/web/mp/content 返回 HTML 页面，限制每账号最多拉取数量避免触发反爬
            content = ""
            if review_id and content_fetched < _MAX_CONTENT_PER_ACCOUNT:
                try:
                    content_url = f"{_WEREAD_CONTENT}?reviewId={review_id}"
                    content_html_page = client.get_text(content_url, headers=headers)
                    raw_html = extract_wechat_content_html(content_html_page)
                    content = strip_html(raw_html) if raw_html else ""
                    content_fetched += 1
                except Exception as exc:
                    log.add_warning(f"微信公众号 / {account.name}: 正文获取失败 {review_id}: {exc}")

            # 文章链接：优先用 mp_url，否则拼接
            article_url = mp_url or f"https://mp.weixin.qq.com/s/{review_id.split('_')[-1]}" if review_id else ""

            items.append(
                CollectedItem(
                    source="微信公众号",
                    author=account.name,
                    title=clean_text(title) or account.name,
                    url=article_url,
                    published_at=published_at,
                    content=content,
                    provider="wechat_weread",
                )
            )

        if found_old:
            break

        # 翻页：微信读书每页约 20 条
        if len(articles) < 20:
            break
        offset += len(articles)

    return items


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
