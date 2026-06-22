"""验证微博 WEIBO_COOKIE 是否有效。"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.config import load_env

load_env()

cookie = os.getenv("WEIBO_COOKIE", "")
print(f"WEIBO_COOKIE length: {len(cookie)}")

# 解析关键 token
xsrf = ""
sub_preview = ""
alf = ""
for part in cookie.split(";"):
    part = part.strip()
    if part.startswith("XSRF-TOKEN="):
        xsrf = part.split("=", 1)[1]
    if part.startswith("SUB="):
        sub_preview = part.split("=", 1)[1][:20] + "..."
    if part.startswith("ALF="):
        alf = part.split("=", 1)[1]

print(f"XSRF-TOKEN: {xsrf[:30] if xsrf else 'NOT FOUND'}")
print(f"SUB: {sub_preview if sub_preview else 'NOT FOUND'}")
if alf:
    import time
    expire_ts = int(alf)
    now = int(time.time())
    remaining = expire_ts - now
    print(f"ALF (登录过期时间戳): {alf} => {'已过期' if remaining < 0 else f'还剩 {remaining//86400} 天'}")
print()

import urllib.request

uid = "2014433131"  # 唐史主任司马迁
url = f"https://weibo.com/ajax/statuses/mymblog?uid={uid}&page=1&feature=0"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Referer": f"https://weibo.com/u/{uid}",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "Cookie": cookie,
}
if xsrf:
    headers["X-XSRF-TOKEN"] = xsrf

print(f"Testing URL: {url}")
req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        print(f"HTTP {resp.status}, body length: {len(body)}")
        if body.startswith("{"):
            data = json.loads(body)
            print(f"JSON keys: {list(data.keys())}")
            statuses = data.get("data", {}).get("list", [])
            print(f"Statuses count: {len(statuses)}")
            if statuses:
                s = statuses[0]
                print(f"First post: created_at={s.get('created_at')}")
                print(f"  text: {str(s.get('text_raw', ''))[:80]}")
                print()
                print("==> Cookie 有效，可以正常抓取微博数据")
            else:
                print(f"API response: {json.dumps(data, ensure_ascii=False)[:400]}")
                ok_val = data.get("ok")
                if ok_val == -100 or "login" in str(data).lower():
                    print()
                    print("==> Cookie 已失效，需要重新登录获取")
                else:
                    print()
                    print("==> 返回空数据，可能 Cookie 失效或该账号无最近动态")
        else:
            print(f"NOT JSON, first 300: {body[:300]}")
            if "login" in body.lower() or "登录" in body:
                print()
                print("==> Cookie 已失效，页面跳转到了登录页")
except Exception as e:
    print(f"Request failed: {type(e).__name__}: {e}")
