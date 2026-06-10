from __future__ import annotations

from datetime import datetime
import logging
import os
import random
import re
import time

from .accounts import Account
from .base import CollectedItem, CollectionLog
from .browser import fetch_status_detail, HAS_PLAYWRIGHT
from .http import HttpClient, absolute_url, clean_text, compact_text
from ..config import Settings
from ..datetime_utils import parse_datetime

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 雪球专用请求头 —— 模拟前端 XHR，减少反爬触发
# ---------------------------------------------------------------------------

def _xueqiu_headers(uid: str = "") -> dict[str, str]:
    """返回雪球 API 请求需要的完整 headers。"""
    cookie = os.getenv("XUEQIU_COOKIE", "")
    # 从 cookie 中提取 xq_a_token（雪球的核心鉴权 token）
    xq_a_token = ""
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("xq_a_token="):
            xq_a_token = part.split("=", 1)[1]
            break

    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": f"https://xueqiu.com/u/{uid}" if uid else "https://xueqiu.com/",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://xueqiu.com",
    }


# ---------------------------------------------------------------------------
# 请求节奏控制
# ---------------------------------------------------------------------------

def _polite_sleep(min_s: float = 0.8, max_s: float = 2.0) -> None:
    """随机延迟，模拟人类浏览节奏，降低反爬风险。"""
    time.sleep(random.uniform(min_s, max_s))


def _long_sleep() -> None:
    """翻页 / 账号切换时稍长延迟。"""
    time.sleep(random.uniform(2.0, 4.0))


# ---------------------------------------------------------------------------
# 主采集逻辑
# ---------------------------------------------------------------------------

def collect_xueqiu(
    account: Account,
    *,
    window_start: datetime,
    window_end: datetime,
    settings: Settings,
    limit: int,
    include_undated: bool,
    clog: CollectionLog,
) -> list[CollectedItem]:
    uid = account.uid or extract_uid(account.url)
    if not uid:
        clog.add_warning(f"雪球 / {account.name}: 缺少 url 或 uid，已跳过")
        return []

    client = HttpClient(cookie_env="XUEQIU_COOKIE")
    headers = _xueqiu_headers(uid)

    # 从 user_timeline 采集（type=2 帖子自带全文，type=3 专栏由 Playwright 补全）
    seen_ids: set[str] = set()
    items = _fetch_timeline(
        "https://xueqiu.com/statuses/user_timeline.json",
        uid=uid, account=account, headers=headers, client=client,
        window_start=window_start, window_end=window_end,
        settings=settings, limit=limit, include_undated=include_undated,
        clog=clog, seen_ids=seen_ids, label="timeline",
    )

    clog.add_info(f"雪球 / {account.name}: 采集 {len(items)} 条（过滤后）")
    return items[:limit]


def _fetch_timeline(
    api_base: str,
    *,
    uid: str,
    account: Account,
    headers: dict[str, str],
    client: HttpClient,
    window_start: datetime,
    window_end: datetime,
    settings: Settings,
    limit: int,
    include_undated: bool,
    clog: CollectionLog,
    seen_ids: set[str],
    label: str,
    max_pages: int = 10,
) -> list[CollectedItem]:
    """从指定 API 端点翻页采集，跳过 seen_ids 中已有的条目。"""
    items: list[CollectedItem] = []
    page = 1

    while len(items) < limit and page <= max_pages:
        api_url = f"{api_base}?user_id={uid}&page={page}&count={min(limit, 20)}"
        try:
            payload = client.get_json(api_url, headers=headers)
        except Exception as exc:
            clog.add_warning(f"雪球 / {account.name}: {label} 第 {page} 页请求失败: {exc}")
            break

        if isinstance(payload, dict) and payload.get("error_code"):
            clog.add_warning(
                f"雪球 / {account.name}: {label} API 返回错误 "
                f"code={payload.get('error_code')} msg={payload.get('error_description', '')}"
            )
            break

        statuses = payload.get("statuses") or payload.get("list") or []
        if not statuses:
            break

        page_timestamps: list[datetime | None] = []
        for status in statuses:
            sid = str(status.get("id") or "")
            if sid and sid in seen_ids:
                continue
            # 先不获取全文，只解析基本信息和日期
            item = _parse_status(status, account, uid, window_end, settings, client, clog, fetch_full=False)
            if not item:
                continue
            if sid:
                seen_ids.add(sid)
            page_timestamps.append(item.published_at)
            if item.published_at is None:
                if include_undated:
                    # 日期未知也尝试获取全文
                    item = _upgrade_full_text(item, status, sid, uid, client, clog, account.name)
                    items.append(item)
                continue
            if window_start <= item.published_at < window_end:
                # 在窗口内的帖子才获取全文
                item = _upgrade_full_text(item, status, sid, uid, client, clog, account.name)
                items.append(item)
            if len(items) >= limit:
                break

        dated = [t for t in page_timestamps if t is not None]
        if dated and all(t < window_start for t in dated):
            break

        page += 1
        if page <= max_pages:
            _long_sleep()

    return items


def _upgrade_full_text(
    item: CollectedItem,
    status: dict,
    status_id: str,
    uid: str,
    client: HttpClient,
    clog: CollectionLog,
    author: str,
) -> CollectedItem:
    """对已在窗口内的条目补充获取全文，返回更新后的 item。"""
    full_content = _fetch_full_text(status, status_id, uid, client, clog, author)
    if full_content and len(full_content) > len(item.content):
        from dataclasses import replace
        return replace(item, content=full_content)
    return item


# ---------------------------------------------------------------------------
# 内容过滤
# ---------------------------------------------------------------------------

def _is_reply_or_junk(status: dict, content: str) -> bool:
    """判断是否为回复、转发或系统生成的低质量内容，应跳过。"""
    # 1. API 字段过滤：reply_id 非空 → 回复
    reply_id = status.get("reply_id")
    if reply_id and str(reply_id) != "0":
        return True

    # 2. 文本特征过滤
    stripped = content.strip()
    junk_prefixes = (
        "回复@",
        "我刚刚调整了雪球组合",
        "我刚刚关注了",
        "我创建了一个组合",
        "我刚刚买入了",
        "我刚刚卖出了",
    )
    if any(stripped.startswith(p) for p in junk_prefixes):
        return True

    # 3. 转发别人内容且自己没写实质内容
    if status.get("retweeted_status") and len(stripped) < 100:
        return True

    # 4. 内容太短（< 30 字），大概率无分析价值
    if len(stripped) < 30:
        return True

    return False


# ---------------------------------------------------------------------------
# 单条解析 + 全文获取
# ---------------------------------------------------------------------------

def _parse_status(
    status: dict,
    account: Account,
    uid: str,
    reference: datetime,
    settings: Settings,
    client: HttpClient,
    clog: CollectionLog,
    *,
    fetch_full: bool = True,
) -> CollectedItem | None:
    raw_text = str(status.get("text") or status.get("description") or "")
    content = clean_text(raw_text)
    if not content:
        return None

    # 过滤低质量内容
    if _is_reply_or_junk(status, content):
        return None

    title = str(status.get("title") or "").strip() or compact_text(content, 48)
    target = str(status.get("target") or "")
    status_id = str(status.get("id") or "")
    if target:
        url = absolute_url("https://xueqiu.com", target)
    elif status_id:
        url = f"https://xueqiu.com/{uid}/{status_id}"
    else:
        url = account.url

    published_at = parse_datetime(
        status.get("created_at"),
        reference=reference,
        timezone_name=settings.timezone,
    )

    # 仅对需要的帖子获取全文（由调用方控制）
    if fetch_full:
        full_content = _fetch_full_text(status, status_id, uid, client, clog, account.name)
        if full_content and len(full_content) > len(content):
            content = full_content

    return CollectedItem(
        source="雪球",
        author=account.name,
        title=title,
        url=url,
        published_at=published_at,
        content=content,
    )


# ---------------------------------------------------------------------------
# 全文获取（核心改进）
# ---------------------------------------------------------------------------

def _fetch_full_text(
    status: dict,
    status_id: str,
    uid: str,
    client: HttpClient,
    clog: CollectionLog,
    author: str,
) -> str:
    """从雪球详情接口获取文章全文。

    timeline API 返回的 text 是截断的 HTML 摘要，
    长文/专栏需要单独请求全文。

    优先使用 Playwright（绕过 WAF 最可靠），失败时回退到 HTTP 方式。
    """
    if not status_id:
        return ""

    # 判断是否需要获取全文
    has_title = bool(str(status.get("title") or "").strip())
    raw_text = str(status.get("text") or "")
    might_be_truncated = (
        has_title
        or "..." in raw_text[-30:]
        or "展开全文" in raw_text
        or "全文" in raw_text[-50:]
        or len(raw_text) > 400
    )
    if not might_be_truncated:
        return ""

    _polite_sleep(0.3, 0.8)  # 请求全文前短延迟

    # 方法 1（优先）: Playwright 浏览器内 fetch（绕过 WAF JS 质询，最可靠）
    if HAS_PLAYWRIGHT:
        try:
            log.debug(f"雪球 / {author}: 尝试 Playwright fetch status {status_id}")
            detail = fetch_status_detail(status_id)
            if isinstance(detail, dict) and not detail.get("error_code"):
                full_text = str(detail.get("text") or "")
                if not full_text:
                    # 可能嵌套在 data / status 下
                    for key in ("data", "status"):
                        inner = detail.get(key)
                        if isinstance(inner, dict):
                            full_text = str(inner.get("text") or "")
                            if full_text:
                                break
                if full_text:
                    result = clean_text(full_text)
                    if result:
                        log.debug(f"雪球 / {author}: Playwright 成功, 长度={len(result)}")
                        return result
        except Exception as exc:
            log.debug(f"雪球 / {author}: Playwright 失败: {exc}")

    # 方法 2: statuses/original/show.json（专栏/长文详情接口）
    headers = _xueqiu_headers(uid)
    headers["Referer"] = f"https://xueqiu.com/{uid}/{status_id}"

    try:
        detail_url = f"https://xueqiu.com/statuses/original/show.json?id={status_id}"
        payload = client.get_json(detail_url, headers=headers)
        if isinstance(payload, dict) and payload.get("error_code"):
            log.debug(f"雪球 / {author}: 详情接口返回错误 {payload.get('error_code')}")
        elif isinstance(payload, dict):
            for obj in [payload, payload.get("data", {}), payload.get("status", {})]:
                if not isinstance(obj, dict):
                    continue
                full_text = str(obj.get("text") or "")
                if full_text:
                    result = clean_text(full_text)
                    if result:
                        return result
    except Exception as exc:
        log.debug(f"雪球 / {author}: 详情接口 original/show 失败: {exc}")

    _polite_sleep(0.5, 1.0)

    # 方法 3: v4/statuses/show.json（新版接口）
    try:
        show_url = f"https://xueqiu.com/v4/statuses/show.json?id={status_id}"
        payload = client.get_json(show_url, headers=headers)
        full_text = ""
        if isinstance(payload, dict):
            inner = payload.get("data") or payload.get("status") or payload
            full_text = str(inner.get("text") or "")
        if full_text:
            result = clean_text(full_text)
            if result:
                return result
    except Exception as exc:
        log.debug(f"雪球 / {author}: 详情接口 v4/show 失败: {exc}")

    clog.add_warning(f"雪球 / {author}: 文章 {status_id} 全文获取失败，使用摘要")
    return ""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def extract_uid(url: str) -> str:
    patterns = [
        r"xueqiu\.com/u/(\d+)",
        r"xueqiu\.com/(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""
