"""抖音平台数据采集器

通过 Playwright 浏览器自动化方式采集抖音用户视频列表。
浏览器自动处理所有签名参数（a_bogus、msToken、verifyFp 等），无需手动破解算法。

依赖：需要 pip install playwright && playwright install chromium
"""
from __future__ import annotations

from datetime import datetime
import logging
import os
import re
from typing import Any

from .accounts import Account
from .base import CollectedItem, CollectionLog
from .browser import HAS_PLAYWRIGHT, browser_launch_kwargs, default_profile_dir
from .http import clean_text, compact_text
from ..cancel import raise_if_cancelled
from ..config import Settings
from ..datetime_utils import parse_datetime

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 抖音 API 端点
# ---------------------------------------------------------------------------

_DOUYIN_BASE = "https://www.douyin.com"
_DOUYIN_USER_POST_API = _DOUYIN_BASE + "/aweme/v1/web/aweme/post/"


# ---------------------------------------------------------------------------
# 主采集逻辑
# ---------------------------------------------------------------------------

def collect_douyin(
    account: Account,
    *,
    window_start: datetime,
    window_end: datetime,
    settings: Settings,
    limit: int,
    include_undated: bool,
    log: CollectionLog,
) -> list[CollectedItem]:
    """采集抖音用户视频列表"""
    raise_if_cancelled()

    if not HAS_PLAYWRIGHT:
        log.add_warning(f"抖音 / {account.name}: Playwright 未安装，已跳过")
        return []

    sec_user_id = account.uid or extract_sec_user_id(account.url)
    if not sec_user_id:
        log.add_warning(f"抖音 / {account.name}: 缺少 uid 或 url，已跳过")
        return []

    items: list[CollectedItem] = []
    max_cursor = 0
    page = 1
    max_pages = 10

    while len(items) < limit and page <= max_pages:
        raise_if_cancelled()

        try:
            data = _fetch_user_posts(sec_user_id, max_cursor)
            if not data:
                log.add_warning(f"抖音 / {account.name}: 第 {page} 页请求失败")
                break

            aweme_list = data.get("aweme_list") or []
            if not aweme_list:
                break

            page_timestamps: list[datetime | None] = []
            for aweme in aweme_list:
                raise_if_cancelled()
                if len(items) >= limit:
                    break

                item = _parse_aweme(aweme, account, window_end, settings)
                if not item:
                    continue

                page_timestamps.append(item.published_at)

                if item.published_at is None:
                    if include_undated:
                        items.append(item)
                    continue

                if window_start <= item.published_at < window_end:
                    items.append(item)

            # 判断是否需要继续翻页
            dated = [t for t in page_timestamps if t is not None]
            if dated and all(t < window_start for t in dated):
                break

            # 检查是否还有下一页
            if not data.get("has_more"):
                break

            max_cursor = data.get("max_cursor", 0)
            if max_cursor == 0:
                break

            page += 1

        except Exception as exc:
            log.add_warning(f"抖音 / {account.name}: 第 {page} 页采集失败: {exc}")
            break

    log.add_info(f"抖音 / {account.name}: 采集 {len(items)} 条")
    return items[:limit]


# ---------------------------------------------------------------------------
# 数据获取
# ---------------------------------------------------------------------------

def _fetch_user_posts(sec_user_id: str, max_cursor: int = 0) -> dict[str, Any] | None:
    """通过 Playwright 浏览器获取抖音用户视频列表

    浏览器自动处理所有反爬参数，无需手动计算签名。
    """
    if not HAS_PLAYWRIGHT:
        return None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    # 构造 API URL（只需基础参数，签名由浏览器自动处理）
    api_url = (
        f"{_DOUYIN_USER_POST_API}"
        f"?device_platform=webapp"
        f"&aid=6383"
        f"&channel=channel_pc_web"
        f"&sec_user_id={sec_user_id}"
        f"&max_cursor={max_cursor}"
        f"&locate_query=false"
        f"&show_live_replay_strategy=1"
        f"&need_time_list=1"
        f"&time_list_query=0"
        f"&whale_cut_token="
        f"&cut_version=1"
        f"&count=18"
        f"&publish_video_strategy_type=2"
        f"&from_user_page=1"
        f"&update_version_code=170400"
        f"&pc_client_type=1"
        f"&version_code=290100"
        f"&version_name=29.1.0"
    )

    profile_dir = default_profile_dir("douyin")
    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        launch_kwargs = browser_launch_kwargs("douyin", headless=True)
        context = pw.chromium.launch_persistent_context(
            str(profile_dir),
            **launch_kwargs,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
            ),
        )

        try:
            page = context.pages[0] if context.pages else context.new_page()

            # 先访问用户主页，建立浏览器会话
            user_page_url = f"https://www.douyin.com/user/{sec_user_id}"
            page.goto(user_page_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)  # 等待页面加载

            # 在浏览器环境中执行 fetch，继承所有 cookie 和签名
            result = page.evaluate("""async (url) => {
                try {
                    const resp = await fetch(url, {
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json, text/plain, */*',
                            'X-Requested-With': 'XMLHttpRequest',
                        }
                    });
                    if (!resp.ok) {
                        return {_error: `HTTP ${resp.status}`};
                    }
                    const text = await resp.text();
                    try {
                        return JSON.parse(text);
                    } catch(e) {
                        return {_error: 'not JSON', _body: text.substring(0, 200)};
                    }
                } catch(e) {
                    return {_error: e.toString()};
                }
            }""", api_url)

            if isinstance(result, dict) and result.get("_error"):
                log.debug(f"抖音 fetch 失败: {result['_error']}")
                return None

            return result

        finally:
            context.close()


# ---------------------------------------------------------------------------
# 数据解析
# ---------------------------------------------------------------------------

def _parse_aweme(
    aweme: dict,
    account: Account,
    reference: datetime,
    settings: Settings,
) -> CollectedItem | None:
    """解析单条抖音视频数据"""
    aweme_id = str(aweme.get("aweme_id") or "")
    if not aweme_id:
        return None

    # 标题/描述
    desc = str(aweme.get("desc") or "").strip()
    if not desc:
        return None

    title = compact_text(desc, 48)

    # URL
    url = f"https://www.douyin.com/video/{aweme_id}"

    # 发布时间
    create_time = aweme.get("create_time", 0)
    published_at: datetime | None = None
    if create_time:
        try:
            published_at = datetime.fromtimestamp(int(create_time), tz=reference.tzinfo)
        except (ValueError, OSError):
            pass

    # 统计数据
    statistics = aweme.get("statistics") or {}
    digg_count = statistics.get("digg_count", 0)
    comment_count = statistics.get("comment_count", 0)
    share_count = statistics.get("share_count", 0)

    # 构造内容：描述 + 统计信息
    content_parts = [desc]
    if digg_count or comment_count or share_count:
        stats = f"点赞: {digg_count}, 评论: {comment_count}, 分享: {share_count}"
        content_parts.append(stats)

    # 添加话题标签
    text_extra = aweme.get("text_extra") or []
    hashtags = []
    for extra in text_extra:
        if extra.get("type") == 1:  # type=1 表示话题标签
            hashtag_name = extra.get("hashtag_name", "")
            if hashtag_name:
                hashtags.append(f"#{hashtag_name}")
    if hashtags:
        content_parts.append(" ".join(hashtags))

    # 提取分章节内容（如果有）
    chapter_content = _extract_chapter_info(aweme)
    if chapter_content:
        content_parts.append("\n" + chapter_content)
    else:
        # 没有章节信息时，尝试音频转录
        transcript = _transcribe_video_if_enabled(url)
        if transcript:
            content_parts.append("\n## 音频转录")
            content_parts.append(transcript)

    content = "\n\n".join(content_parts)

    return CollectedItem(
        source="抖音",
        author=account.name,
        title=title,
        url=url,
        published_at=published_at,
        content=clean_text(content),
        provider="douyin_web",
    )


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _extract_chapter_info(aweme: dict) -> str:
    """提取视频的章节推荐信息（如果有）"""
    chapter = aweme.get("recommend_chapter_info") or {}
    if not chapter:
        return ""

    parts = []

    # 内容摘要
    abstract = chapter.get("chapter_abstract")
    if abstract and abstract.strip():
        parts.append("## 内容摘要")
        parts.append(abstract.strip())

    # 分章节内容
    chapters = chapter.get("recommend_chapter_list") or []
    if chapters:
        parts.append("## 视频章节")

        for chapter_item in chapters:
            title = str(chapter_item.get("desc") or "").strip()
            if not title:
                continue

            # 章节标题
            chapter_parts = [f"### {title}"]

            # 时间戳（转换为分:秒格式）
            timestamp = chapter_item.get("timestamp", 0)
            if timestamp:
                minutes = timestamp // 60000
                seconds = (timestamp % 60000) // 1000
                chapter_parts.append(f"**时间**: {minutes:02d}:{seconds:02d}")

            # 章节详情
            detail = str(chapter_item.get("detail") or "").strip()
            if detail:
                chapter_parts.append(detail)

            # 要点列表
            points = chapter_item.get("points") or []
            if points:
                for point in points:
                    point_desc = str(point.get("desc") or "").strip()
                    point_detail = str(point.get("detail") or "").strip()

                    if point_desc:
                        chapter_parts.append(point_desc)

                    if point_detail:
                        # 处理多行详情，保持原有格式
                        detail_lines = point_detail.strip().split('\n')
                        for line in detail_lines:
                            line = line.strip()
                            if line:
                                chapter_parts.append(f"  {line}")

            parts.append("\n".join(chapter_parts))

    return "\n\n".join(parts) if parts else ""


def extract_sec_user_id(url: str) -> str:
    """从抖音用户主页 URL 中提取 sec_user_id

    支持格式：
    - https://www.douyin.com/user/MS4wLjABAAAA...
    """
    if not url:
        return ""

    # 匹配 /user/{sec_user_id} 格式
    match = re.search(r"douyin\.com/user/([A-Za-z0-9_\-]+)", url)
    if match:
        return match.group(1)

    return ""


def _transcribe_video_if_enabled(video_url: str) -> str:
    """如果启用了转录功能，转录视频音频为文字

    通过环境变量 DOUYIN_ENABLE_TRANSCRIBE=1 启用
    """
    if not os.getenv("DOUYIN_ENABLE_TRANSCRIBE", "").strip() == "1":
        return ""

    try:
        from .transcribe import transcribe_douyin_video, export_cookies_from_profile
        from pathlib import Path
        import tempfile

        # 导出 Cookie 供 yt-dlp 使用
        profile_dir = default_profile_dir("douyin")
        cookie_file = None

        if profile_dir.exists():
            cookie_file = Path(tempfile.gettempdir()) / "douyin_cookies.txt"
            if export_cookies_from_profile(profile_dir, cookie_file):
                log.debug(f"Cookie 已导出到: {cookie_file}")
            else:
                cookie_file = None

        # 转录音频
        transcript = transcribe_douyin_video(video_url, cookie_file=cookie_file)

        # 清理临时 Cookie 文件
        if cookie_file and cookie_file.exists():
            try:
                cookie_file.unlink()
            except Exception:
                pass

        return transcript

    except ImportError:
        log.debug("音频转录模块未安装，跳过转录")
        return ""
    except Exception as exc:
        log.debug(f"音频转录失败: {exc}")
        return ""


def login_douyin_profile() -> None:
    """打开浏览器让用户登录抖音账号

    登录后的 Cookie 会保存在持久化 profile 中，后续采集自动使用。
    """
    if not HAS_PLAYWRIGHT:
        raise RuntimeError("Playwright is not installed. Run: pip install -e .[collect]")

    from .browser import login_persistent_profile
    login_persistent_profile("douyin")
