"""深入分析 user_timeline 返回的数据结构，找出全文获取的可行路径。"""
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

data = client.get_json(
    f"https://xueqiu.com/statuses/user_timeline.json?user_id={uid}&page=1&count=3",
    headers=headers,
)

statuses = data.get("statuses") or []
for i, s in enumerate(statuses[:3]):
    print(f"========== Status {i+1} ==========")
    print(f"id:          {s.get('id')}")
    print(f"type:        {s.get('type')}")
    print(f"title:       [{s.get('title', '')}]")
    print(f"truncated:   {s.get('truncated')}")
    print(f"created_at:  {s.get('created_at')}")
    print(f"source_link: {s.get('source_link', '')}")
    print(f"rqtype:      {s.get('rqtype', '')}")

    # text 和 description 分别看
    text = s.get("text", "")
    desc = s.get("description", "")
    print(f"text len:    {len(text)}")
    print(f"desc len:    {len(desc)}")
    if text:
        print(f"text[:300]:  {text[:300]}")
    if desc:
        print(f"desc[:300]:  {desc[:300]}")

    # 看 target 字段
    target = s.get("target", "")
    if target:
        print(f"target:      {target}")

    # 看有没有 retweeted_status
    rt = s.get("retweeted_status")
    if rt:
        print(f"retweeted:   id={rt.get('id')} text_len={len(rt.get('text',''))} desc_len={len(rt.get('description',''))}")

    # 打印所有非空非标准字段的值
    skip = {'id','user_id','source','title','created_at','retweet_count','fav_count',
            'truncated','commentId','retweet_status_id','symbol_id','description',
            'type','source_link','edited_at','user','retweeted_status','answers',
            'rqtype','rqid','text'}
    extras = {k: v for k, v in s.items() if k not in skip and v}
    if extras:
        print(f"extras:      {json.dumps(extras, ensure_ascii=False, default=str)[:500]}")

    print()
