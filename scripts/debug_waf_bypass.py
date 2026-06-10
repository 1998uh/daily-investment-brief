"""测试不同 headers 组合请求雪球文章页面，找出绕过 WAF 的方式。"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.config import load_env
from pipeline.collectors.http import HttpClient

load_env()

uid = "1071814723"
# type=3 的专栏文章
article_id = "302267251"
page_url = f"https://xueqiu.com/{uid}/{article_id}"
cookie = os.getenv("XUEQIU_COOKIE", "")

client = HttpClient(cookie_env="XUEQIU_COOKIE")

print(f"Testing article page: {page_url}")
print(f"Cookie length: {len(cookie)}")
print()

# 方案 1: 完整浏览器 headers（像真实浏览器访问）
tests = [
    ("Full browser headers", {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Referer": f"https://xueqiu.com/u/{uid}",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }),
    ("Minimal - just Accept html", {
        "Accept": "text/html",
        "Referer": f"https://xueqiu.com/u/{uid}",
    }),
    ("XHR style with Accept html", {
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": f"https://xueqiu.com/u/{uid}",
        "X-Requested-With": "XMLHttpRequest",
    }),
    ("API detail - statuses/show with full headers", {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": f"https://xueqiu.com/{uid}/{article_id}",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://xueqiu.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }),
]

for label, headers in tests:
    print(f"=== {label} ===")
    try:
        if "statuses/show" in label:
            url = f"https://xueqiu.com/statuses/original/show.json?id={article_id}"
        else:
            url = page_url
        print(f"  URL: {url}")
        raw = client.get_text(url, headers=headers)
        print(f"  Response length: {len(raw)}")

        is_waf = "aliyun_waf" in raw or "_waf_" in raw
        print(f"  WAF blocked: {is_waf}")

        if not is_waf:
            # 看看返回了什么
            if raw.strip().startswith("{"):
                data = json.loads(raw)
                print(f"  JSON keys: {list(data.keys())[:10]}")
                text = ""
                for key_path in [["text"], ["data", "text"], ["status", "text"]]:
                    obj = data
                    for k in key_path:
                        obj = obj.get(k, {}) if isinstance(obj, dict) else {}
                    if isinstance(obj, str) and obj:
                        text = obj
                        break
                if text:
                    print(f"  FULL TEXT FOUND! length={len(text)}")
                    from pipeline.collectors.http import clean_text
                    cleaned = clean_text(text)
                    print(f"  Cleaned length: {len(cleaned)}")
                    print(f"  First 300: {cleaned[:300]}")
            else:
                # HTML - 搜索内容
                for kw in ["article-content", "status-content", "article__bd",
                           "detail__bd", "article__content", "status__content"]:
                    if kw in raw:
                        print(f"  Found class: {kw}")

                # 试图从 HTML 提取 text JSON
                m = re.search(r'"text"\s*:\s*"((?:[^"\\]|\\.){50,})"', raw, re.DOTALL)
                if m:
                    print(f"  JSON text field found, raw length: {len(m.group(1))}")
                    try:
                        decoded = m.group(1).encode("utf-8").decode("unicode_escape", errors="replace")
                        from pipeline.collectors.http import clean_text
                        cleaned = clean_text(decoded)
                        print(f"  Cleaned length: {len(cleaned)}")
                        print(f"  First 200: {cleaned[:200]}")
                    except Exception as e:
                        print(f"  Decode failed: {e}")
                else:
                    print(f"  No text JSON in HTML")
                    # 打印一部分看看结构
                    print(f"  First 500: {raw[:500]}")
        else:
            print(f"  (WAF HTML page returned)")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
    print()

print("Done.")
