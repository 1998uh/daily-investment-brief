from __future__ import annotations

from datetime import datetime
import os
import re
from urllib import parse

from .accounts import Account
from .base import CollectedItem, CollectionLog
from .http import HttpClient, clean_text, compact_text
from ..cancel import raise_if_cancelled
from ..config import Settings
from ..datetime_utils import parse_datetime


def collect_weibo(
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
    uid = account.uid or extract_uid(account.url)
    if not uid:
        log.add_warning(f"微博 / {account.name}: 缺少 url 或 uid，已跳过")
        return []

    client = HttpClient(cookie_env="WEIBO_COOKIE")
    try:
        items = collect_weibo_web(
            client,
            account,
            uid=uid,
            window_start=window_start,
            window_end=window_end,
            settings=settings,
            limit=limit,
            include_undated=include_undated,
        )
        log.add_info(f"微博 / {account.name}: 采集 {len(items)} 条")
        return items
    except Exception as exc:
        log.add_warning(f"微博 / {account.name}: 网页接口失败，尝试移动端接口：{exc}")

    items = collect_weibo_mobile(
        client,
        account,
        uid=uid,
        window_start=window_start,
        window_end=window_end,
        settings=settings,
        limit=limit,
        include_undated=include_undated,
    )
    log.add_info(f"微博 / {account.name}: 采集 {len(items)} 条")
    return items


def collect_weibo_web(
    client: HttpClient,
    account: Account,
    *,
    uid: str,
    window_start: datetime,
    window_end: datetime,
    settings: Settings,
    limit: int,
    include_undated: bool,
) -> list[CollectedItem]:
    items: list[CollectedItem] = []
    page = 1

    while len(items) < limit and page <= 3:
        raise_if_cancelled()
        api_url = "https://weibo.com/ajax/statuses/mymblog?" + parse.urlencode(
            {"uid": uid, "page": page, "feature": "0"}
        )
        payload = client.get_json(api_url, headers=weibo_web_headers(uid))
        statuses = payload.get("data", {}).get("list", [])
        if not statuses:
            break

        for status in statuses:
            raise_if_cancelled()
            item = parse_mblog(status, account, uid, window_end, settings, client, web=True)
            if not item:
                continue
            if item.published_at is None:
                if include_undated:
                    items.append(item)
                continue
            if window_start <= item.published_at < window_end:
                items.append(item)
            if len(items) >= limit:
                break
        page += 1

    return items[:limit]


def collect_weibo_mobile(
    client: HttpClient,
    account: Account,
    *,
    uid: str,
    window_start: datetime,
    window_end: datetime,
    settings: Settings,
    limit: int,
    include_undated: bool,
) -> list[CollectedItem]:
    items: list[CollectedItem] = []
    page = 1

    while len(items) < limit and page <= 3:
        raise_if_cancelled()
        api_url = (
            "https://m.weibo.cn/api/container/getIndex"
            f"?type=uid&value={uid}&containerid=107603{uid}&page={page}"
        )
        payload = client.get_json(
            api_url,
            headers={
                "Referer": f"https://m.weibo.cn/u/{uid}",
                "Accept": "application/json, text/plain, */*",
            },
        )
        cards = payload.get("data", {}).get("cards", [])
        if not cards:
            break

        for card in cards:
            raise_if_cancelled()
            mblog = card.get("mblog")
            if not mblog:
                continue
            item = parse_mblog(mblog, account, uid, window_end, settings, client, web=False)
            if not item:
                continue
            if item.published_at is None:
                if include_undated:
                    items.append(item)
                continue
            if window_start <= item.published_at < window_end:
                items.append(item)
            if len(items) >= limit:
                break
        page += 1

    return items[:limit]


def parse_mblog(
    mblog: dict,
    account: Account,
    uid: str,
    reference: datetime,
    settings: Settings,
    client: HttpClient,
    web: bool,
) -> CollectedItem | None:
    raise_if_cancelled()
    text = str(mblog.get("text_raw") or "").strip()
    if not text:
        text = clean_text(str(mblog.get("text") or ""))
    mblog_id = str(mblog.get("id") or "")
    bid = str(mblog.get("bid") or mblog.get("mblogid") or "")

    if mblog.get("isLongText") and mblog_id:
        long_text = fetch_long_text(client, mblog_id, web=web)
        if long_text:
            text = long_text

    if not text:
        return None

    # 过滤低质量 / 投资无关内容
    if _is_junk_weibo(mblog, text):
        return None

    published_at = parse_datetime(
        mblog.get("created_at"),
        reference=reference,
        timezone_name=settings.timezone,
    )
    url = f"https://weibo.com/{uid}/{bid or mblog_id}" if (bid or mblog_id) else account.url
    title = compact_text(text, 48)
    return CollectedItem(
        source="微博",
        author=account.name,
        title=title,
        url=url,
        published_at=published_at,
        content=text,
    )


# ---------------------------------------------------------------------------
# 微博内容过滤
# ---------------------------------------------------------------------------

def _is_junk_weibo(mblog: dict, text: str) -> bool:
    """判断微博是否为回复、转发短评、过短内容或与投资无关的闲聊。"""
    stripped = text.strip()

    # 1. 过短（< 30 字），大概率无分析价值
    if len(stripped) < 30:
        return True

    # 2. 回复别人的微博（以 "回复@" 开头）且自身无实质内容
    if stripped.startswith("回复@") and len(stripped) < 200:
        return True

    # 3. 转发且自己没写多少内容
    retweeted = mblog.get("retweeted_status")
    if retweeted and len(stripped) < 100:
        return True

    # 4. 系统生成的低质量内容
    junk_prefixes = (
        "我刚刚关注了",
        "我刚打赏了",
        "我正在看",
        "转发微博",
        "分享图片",
        "分享视频",
    )
    if any(stripped.startswith(p) for p in junk_prefixes):
        return True

    # 5. 不含任何投资/市场关键词的短帖（< 300 字），大概率是闲聊
    #    长帖（>= 300 字）可能是深度分析，即使关键词不命中也保留
    if len(stripped) < 300 and not _has_investment_keywords(stripped):
        return True

    return False


# 投资/市场相关关键词（命中任一即视为相关）
_INVESTMENT_KEYWORDS = re.compile(
    r"股|基金|ETF|指数|A股|港股|美股|大盘|涨|跌|仓|持仓|抄底|估值|市盈|PE|PB|ROE"
    r"|板块|赛道|科技|半导体|芯片|新能源|医药|消费|白酒|银行|红利|债|利率"
    r"|盘前|盘后|开盘|收盘|看盘|成交|量能|缩量|放量|突破|回调|反弹|震荡|趋势"
    r"|投资|交易|买入|卖出|止损|止盈|收益|亏损|盈利|回撤|净值"
    r"|简报|研报|财报|年报|季报|业绩|营收|利润|分红"
    r"|央行|政策|降息|加息|CPI|GDP|PMI|监管|宏观|通胀|汇率|关税"
    r"|牛市|熊市|恒指|纳斯达克|标普|道琼斯|期货|黄金|原油|有色|PCB"
    r"|上证|深证|创业板|科创板|北证|港通|沪深",
    re.IGNORECASE,
)


def _has_investment_keywords(text: str) -> bool:
    return bool(_INVESTMENT_KEYWORDS.search(text))


def fetch_long_text(client: HttpClient, mblog_id: str, *, web: bool) -> str:
    raise_if_cancelled()
    if web:
        try:
            payload = client.get_json(
                f"https://weibo.com/ajax/statuses/longtext?id={mblog_id}",
                headers=weibo_web_headers(""),
            )
            return clean_text(str(payload.get("data", {}).get("longTextContent") or ""))
        except Exception:
            return ""
    try:
        payload = client.get_json(f"https://m.weibo.cn/statuses/extend?id={mblog_id}")
    except Exception:
        return ""
    return clean_text(str(payload.get("data", {}).get("longTextContent") or ""))


def extract_uid(url: str) -> str:
    patterns = [
        r"weibo\.com/u/(\d+)",
        r"weibo\.com/(\d+)",
        r"m\.weibo\.cn/u/(\d+)",
        r"m\.weibo\.cn/profile/(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def weibo_web_headers(uid: str) -> dict[str, str]:
    cookie = os.getenv("WEIBO_COOKIE", "")
    xsrf = ""
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("XSRF-TOKEN="):
            xsrf = part.split("=", 1)[1]
            break

    headers = {
        "Referer": f"https://weibo.com/u/{uid}" if uid else "https://weibo.com/",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
    }
    if xsrf:
        headers["X-XSRF-TOKEN"] = xsrf
    return headers
