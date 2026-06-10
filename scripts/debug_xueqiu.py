"""调试雪球 API 端点，找出哪些接口可用、返回什么格式。

用法:
    python scripts/debug_xueqiu.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.config import load_env
from pipeline.collectors.http import HttpClient

# 先加载 .env
load_env()

UID = "1071814723"  # 诸葛孔暗

client = HttpClient(cookie_env="XUEQIU_COOKIE")
cookie = os.getenv("XUEQIU_COOKIE", "")
print(f"Cookie: {'SET (' + str(len(cookie)) + ' chars)' if cookie else 'NOT SET'}")
print()

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": f"https://xueqiu.com/u/{UID}",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://xueqiu.com",
}


def test_endpoint(label, url, headers=None, is_json=True):
    print(f"=== {label} ===")
    print(f"  URL: {url}")
    h = headers or HEADERS
    try:
        raw = client.get_text(url, headers=h)
        print(f"  Response length: {len(raw)}")
        if is_json:
            try:
                data = json.loads(raw)
                print(f"  Top keys: {list(data.keys())[:15]}")
                if "error_code" in data:
                    print(f"  ERROR: code={data.get('error_code')} msg={data.get('error_description','')}")
                # 尝试找 statuses/list
                items = data.get("statuses") or data.get("list") or data.get("data") or []
                if isinstance(items, list) and items:
                    print(f"  Items count: {len(items)}")
                    s = items[0]
                    print(f"  First item keys: {list(s.keys())[:20]}")
                    print(f"    id={s.get('id')}, title=[{s.get('title','')}], text_len={len(s.get('text',''))}")
                elif isinstance(items, dict):
                    print(f"  Data keys: {list(items.keys())[:15]}")
                    text = items.get("text", "")
                    if text:
                        print(f"  text length: {len(text)}")
                return data
            except json.JSONDecodeError:
                print(f"  NOT JSON! First 300 chars: {raw[:300]}")
        else:
            print(f"  First 500 chars: {raw[:500]}")
            # 找关键 class
            for kw in ["article-content", "status-content", "article__bd", "detail__bd"]:
                if kw in raw:
                    print(f"  Found class: {kw}")
            # 找 JSON text 字段
            m = re.search(r'"text"\s*:\s*"(.{0,80})', raw)
            if m:
                print(f"  JSON text field found (first 120): {m.group()[:120]}...")
            return raw
    except Exception as e:
        print(f"  FAILED: {e}")
        return None
    finally:
        print()


# 1. 正常时间线
data = test_endpoint(
    "user_timeline (正常工作的)",
    f"https://xueqiu.com/statuses/user_timeline.json?user_id={UID}&page=1&count=5",
)

# 获取一个 status_id
sid = ""
if data:
    statuses = data.get("statuses") or data.get("list") or []
    if statuses:
        sid = str(statuses[0].get("id", ""))
        print(f"Using status_id: {sid}")
        print()

# 2. original/timeline（专栏/原创）
test_endpoint(
    "original/timeline (专栏时间线)",
    f"https://xueqiu.com/statuses/original/timeline.json?user_id={UID}&page=1&count=5",
)

# 3. v4 user_timeline
test_endpoint(
    "v4/user_timeline",
    f"https://xueqiu.com/v4/statuses/user_timeline.json?user_id={UID}&page=1&count=5",
)

# 4. search/status (type=11 长文)
test_endpoint(
    "query/search/status type=11 (长文)",
    f"https://xueqiu.com/query/v1/symbol/search/status.json?u={UID}&count=5&comment=0&hl=0&source=all&sort=time&page=1&type=11",
)

# 5. search/status (type=0 全部)
test_endpoint(
    "query/search/status type=0 (全部)",
    f"https://xueqiu.com/query/v1/symbol/search/status.json?u={UID}&count=5&comment=0&hl=0&source=all&sort=time&page=1&type=0",
)

if sid:
    # 6-8. 全文获取三种方法
    test_endpoint(
        "original/show (全文方法1)",
        f"https://xueqiu.com/statuses/original/show.json?id={sid}",
    )
    test_endpoint(
        "v4/statuses/show (全文方法2)",
        f"https://xueqiu.com/v4/statuses/show.json?id={sid}",
    )
    test_endpoint(
        f"HTML page (全文方法3)",
        f"https://xueqiu.com/{UID}/{sid}",
        headers={"Accept": "text/html", "Referer": f"https://xueqiu.com/u/{UID}"},
        is_json=False,
    )

    # 9. statuses/show.json (不带 original 或 v4 前缀)
    test_endpoint(
        "statuses/show (无前缀)",
        f"https://xueqiu.com/statuses/show.json?id={sid}",
    )

print("Done.")
