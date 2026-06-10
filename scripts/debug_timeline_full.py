"""分析更多 timeline 条目，重点看有 title 的长文和 text/description 差异。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.config import load_env
from pipeline.collectors.http import HttpClient

load_env()

uid = "1071814723"
client = HttpClient(cookie_env="XUEQIU_COOKIE")
headers = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": f"https://xueqiu.com/u/{uid}",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://xueqiu.com",
}

# 拉 20 条看更完整的画面
data = client.get_json(
    f"https://xueqiu.com/statuses/user_timeline.json?user_id={uid}&page=1&count=20",
    headers=headers,
)

statuses = data.get("statuses") or []
print(f"Total statuses returned: {len(statuses)}")
print()

for i, s in enumerate(statuses):
    sid = s.get("id")
    title = s.get("title", "")
    stype = s.get("type")
    truncated = s.get("truncated")
    text = s.get("text", "")
    desc = s.get("description", "")
    target = s.get("target", "")
    created = s.get("created_at")
    rt = s.get("retweeted_status")

    # 标记有 title 的（专栏/长文）
    marker = " *** HAS TITLE ***" if title else ""
    truncated_marker = " [TRUNCATED]" if truncated else ""

    print(f"--- [{i+1}] id={sid} type={stype}{marker}{truncated_marker} ---")
    if title:
        print(f"  title:     {title}")
    print(f"  text_len:  {len(text)}")
    print(f"  desc_len:  {len(desc)}")

    # 对比 text 和 desc
    if text and desc:
        if text == desc:
            print(f"  text==desc: YES")
        else:
            print(f"  text==desc: NO (text longer by {len(text)-len(desc)} chars)")
    elif not text and desc:
        print(f"  text: EMPTY, only desc available")
    elif text and not desc:
        print(f"  desc: EMPTY, only text available")

    if truncated:
        print(f"  truncated: True")
    if target:
        print(f"  target:    {target}")
    if rt:
        rt_text = rt.get("text", "")
        rt_desc = rt.get("description", "")
        print(f"  retweet:   id={rt.get('id')} text_len={len(rt_text)} desc_len={len(rt_desc)}")

    # 对于有 title 的条目，打印 text 前 500 字符
    if title and text:
        print(f"  text[:500]: {text[:500]}")
    elif title and not text and desc:
        print(f"  desc[:500]: {desc[:500]}")

    print()
