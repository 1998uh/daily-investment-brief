"""调试抖音章节数据结构"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.collectors.douyin import _fetch_user_posts

# 超级辉的 sec_user_id
sec_user_id = "MS4wLjABAAAAslofpLxb1ccBf6x1QC-hBZA8v4QpNg6GQjf8HQGQMiY"

print("正在获取视频列表...")
result = _fetch_user_posts(sec_user_id, max_cursor=0)

if not result:
    print("获取失败")
    sys.exit(1)

aweme_list = result.get("aweme_list") or []
print(f"获取到 {len(aweme_list)} 个视频\n")

# 遍历所有视频，找到有章节信息的
for idx, video in enumerate(aweme_list, 1):
    desc = video.get("desc", "")
    aweme_id = video.get("aweme_id", "")
    chapter_info = video.get("recommend_chapter_info")

    if chapter_info:
        print(f"=== 视频 {idx}: {desc[:50]}... ===")
        print(f"视频ID: {aweme_id}")
        print(f"URL: https://www.douyin.com/video/{aweme_id}")
        print("\n=== recommend_chapter_info 结构 ===")
        print(json.dumps(chapter_info, ensure_ascii=False, indent=2))
        print("\n" + "=" * 80 + "\n")

print(f"共找到 {sum(1 for v in aweme_list if v.get('recommend_chapter_info'))} 个有章节信息的视频")
