"""抖音视频音频转文字模块

优先使用 API 返回的音频 URL 直接下载，如果失败则回退到 yt-dlp。
"""
import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# 全局模型缓存，避免每次转录都重新加载
_whisper_model = None


def _get_whisper_model():
    """获取或初始化 Whisper 模型（懒加载）"""
    global _whisper_model
    if _whisper_model is None:
        model_size = os.getenv("WHISPER_MODEL_SIZE", "small")
        device = os.getenv("WHISPER_DEVICE", "cpu")
        log.debug(f"初始化 Whisper 模型: {model_size} on {device}")
        _whisper_model = WhisperModel(model_size, device=device, compute_type="int8")
    return _whisper_model


def transcribe_audio_from_url(audio_url: str) -> str:
    """从音频 URL 下载并转录

    Args:
        audio_url: 音频文件 URL

    Returns:
        转录的文字内容，失败返回空字符串
    """
    if not HAS_WHISPER:
        log.warning("faster-whisper 未安装，跳过音频转录")
        return ""

    if not HAS_REQUESTS:
        log.warning("requests 未安装，跳过音频转录")
        return ""

    audio_path = None
    try:
        # 创建临时文件用于存储音频
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            audio_path = tmp.name

        # 下载音频文件
        log.debug(f"下载音频: {audio_url}")
        response = requests.get(audio_url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        response.raise_for_status()

        with open(audio_path, "wb") as f:
            f.write(response.content)

        # 转录音频
        log.debug(f"转录音频: {audio_path}")
        model = _get_whisper_model()
        segments, info = model.transcribe(audio_path, language="zh", beam_size=5)

        # 拼接所有片段
        text = " ".join(seg.text.strip() for seg in segments)
        log.debug(f"转录完成，共 {len(text)} 字符")

        return text

    except Exception as exc:
        log.warning(f"音频转录失败: {exc}")
        return ""

    finally:
        # 清理临时文件
        if audio_path and Path(audio_path).exists():
            try:
                os.remove(audio_path)
            except Exception:
                pass


def transcribe_douyin_video(video_url: str, *, cookie_file: Path | None = None) -> str:
    """下载抖音视频音频并转录为文字（回退方案，使用 yt-dlp）

    Args:
        video_url: 抖音视频 URL
        cookie_file: 可选的 Cookie 文件路径（Netscape 格式）

    Returns:
        转录的文字内容，失败返回空字符串
    """
    if not HAS_WHISPER:
        log.warning("faster-whisper 未安装，跳过音频转录")
        return ""

    try:
        import yt_dlp
    except ImportError:
        log.warning("yt-dlp 未安装，跳过音频转录")
        return ""

    audio_path = None
    try:
        # 创建临时文件用于存储音频
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            audio_path = tmp.name

        # 使用 yt-dlp 下载音频
        log.debug(f"下载音频 (yt-dlp): {video_url}")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": audio_path,
            "quiet": True,
            "no_warnings": True,
            "extract_audio": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }],
        }

        if cookie_file and cookie_file.exists():
            ydl_opts["cookiefile"] = str(cookie_file)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # 检查文件是否存在
        if not Path(audio_path).exists():
            log.warning(f"音频下载失败: {video_url}")
            return ""

        # 转录音频
        log.debug(f"转录音频: {audio_path}")
        model = _get_whisper_model()
        segments, info = model.transcribe(audio_path, language="zh", beam_size=5)

        # 拼接所有片段
        text = " ".join(seg.text.strip() for seg in segments)
        log.debug(f"转录完成，共 {len(text)} 字符")

        return text

    except Exception as exc:
        log.warning(f"音频转录失败: {exc}")
        return ""

    finally:
        # 清理临时文件
        if audio_path and Path(audio_path).exists():
            try:
                os.remove(audio_path)
            except Exception:
                pass


def export_cookies_from_profile(profile_dir: Path, output_path: Path) -> bool:
    """从 Playwright profile 导出 Cookie 为 Netscape 格式供 yt-dlp 使用

    Args:
        profile_dir: Playwright 持久化 profile 目录
        output_path: 输出的 Cookie 文件路径

    Returns:
        是否成功导出
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False

    try:
        with sync_playwright() as pw:
            from ..collectors.browser import browser_launch_kwargs
            launch_kwargs = browser_launch_kwargs("douyin", headless=True)
            context = pw.chromium.launch_persistent_context(str(profile_dir), **launch_kwargs)

            try:
                cookies = context.cookies(["https://www.douyin.com"])

                # 写入 Netscape 格式
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("# Netscape HTTP Cookie File\n")
                    for c in cookies:
                        domain = c.get("domain", "")
                        flag = "TRUE" if domain.startswith(".") else "FALSE"
                        path = c.get("path", "/")
                        secure = "TRUE" if c.get("secure") else "FALSE"
                        expires = str(int(c.get("expires", 0)))
                        name = c.get("name", "")
                        value = c.get("value", "")
                        f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")

                return True
            finally:
                context.close()

    except Exception as exc:
        log.debug(f"导出 Cookie 失败: {exc}")
        return False
