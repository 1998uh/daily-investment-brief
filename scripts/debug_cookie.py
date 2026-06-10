"""最小化测试：验证 XUEQIU_COOKIE 是否生效。"""
import os
import json
import sys
from urllib import request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.config import load_env

# 先加载 .env
load_env()

cookie = os.getenv("XUEQIU_COOKIE", "")
print(f"XUEQIU_COOKIE length: {len(cookie)}")
print(f"XUEQIU_COOKIE first 80 chars: {cookie[:80]}...")
print(f"XUEQIU_COOKIE last 40 chars: ...{cookie[-40:]}")
print()

# 检查是否包含关键 token
has_xq_a = "xq_a_token=" in cookie
has_u = "u=" in cookie
print(f"Contains xq_a_token: {has_xq_a}")
print(f"Contains u=: {has_u}")
print()

# 最简单的请求
uid = "1071814723"
url = f"https://xueqiu.com/statuses/user_timeline.json?user_id={uid}&page=1&count=1"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": f"https://xueqiu.com/u/{uid}",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://xueqiu.com",
    "Cookie": cookie,
}

print(f"Request URL: {url}")
print(f"Request headers:")
for k, v in headers.items():
    if k == "Cookie":
        print(f"  {k}: {v[:60]}...")
    else:
        print(f"  {k}: {v}")
print()

req = request.Request(url, headers=headers)
try:
    with request.urlopen(req, timeout=15) as resp:
        status = resp.status
        ct = resp.headers.get("Content-Type", "")
        body = resp.read().decode("utf-8", errors="replace")
        print(f"HTTP {status}, Content-Type: {ct}")
        print(f"Body length: {len(body)}")
        if body.startswith("{"):
            data = json.loads(body)
            print(f"JSON keys: {list(data.keys())}")
            if data.get("error_code"):
                print(f"API error: {data.get('error_code')} {data.get('error_description','')}")
            else:
                statuses = data.get("statuses") or []
                print(f"Statuses count: {len(statuses)}")
                if statuses:
                    s = statuses[0]
                    print(f"First: id={s.get('id')} title=[{s.get('title','')}]")
        else:
            print(f"NOT JSON, first 200: {body[:200]}")
except Exception as e:
    print(f"Request failed: {type(e).__name__}: {e}")
