"""测试抖音视频音频转录功能"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 启用转录功能
os.environ["DOUYIN_ENABLE_TRANSCRIBE"] = "1"

from pipeline.collectors.transcribe import transcribe_audio_from_url, transcribe_douyin_video, export_cookies_from_profile
from pipeline.collectors.browser import default_profile_dir


def test_direct_audio_transcribe():
    """测试直接从音频 URL 转录"""
    print("=" * 60)
    print("Test 1: Direct Audio URL Transcription")
    print("=" * 60)

    # 使用示例音频 URL（从 API 响应中提取）
    audio_url = "https://sf11-cdn-tos.douyinstatic.com/obj/ies-music/7673530475079895854.mp3"

    print(f"Audio URL: {audio_url}")
    print("Downloading and transcribing...")
    print("(This may take 30-60 seconds depending on audio length)")
    print()

    try:
        transcript = transcribe_audio_from_url(audio_url)

        if transcript:
            print(f"[OK] Transcription successful")
            print(f"Length: {len(transcript)} characters")
            print("\nTranscript preview (first 500 chars):")
            print("-" * 60)
            print(transcript[:500])
            if len(transcript) > 500:
                print("...")
            print("-" * 60)
            return True
        else:
            print("[FAIL] Transcription returned empty result")
            return False

    except Exception as exc:
        print(f"[FAIL] Transcription failed: {exc}")
        import traceback
        traceback.print_exc()
        return False


def test_cookie_export():
    """测试 Cookie 导出"""
    print("\n" + "=" * 60)
    print("Test 2: Export Cookies from Playwright Profile")
    print("=" * 60)

    profile_dir = default_profile_dir("douyin")
    if not profile_dir.exists():
        print(f"[SKIP] Profile directory does not exist: {profile_dir}")
        print("Run: python -m pipeline auth-login --platform douyin")
        return False

    output_path = Path("douyin_cookies.txt")
    success = export_cookies_from_profile(profile_dir, output_path)

    if success and output_path.exists():
        print(f"[OK] Cookies exported to: {output_path}")
        print(f"File size: {output_path.stat().st_size} bytes")

        # 显示前几行
        lines = output_path.read_text(encoding="utf-8").split("\n")[:5]
        print("First 5 lines:")
        for line in lines:
            print(f"  {line[:80]}")

        output_path.unlink()
        return True
    else:
        print("[FAIL] Cookie export failed")
        return False


def test_ytdlp_transcribe():
    """测试 yt-dlp 方案转录（回退方案）"""
    print("\n" + "=" * 60)
    print("Test 3: Transcribe via yt-dlp (Fallback)")
    print("=" * 60)

    # 使用超级辉的一个视频（短视频，快速测试）
    video_url = "https://www.douyin.com/video/7505641163321134387"

    print(f"Video URL: {video_url}")
    print("Downloading audio via yt-dlp and transcribing...")
    print("(This may take 30-60 seconds depending on video length)")
    print()

    profile_dir = default_profile_dir("douyin")
    cookie_file = None

    if profile_dir.exists():
        cookie_file = Path("douyin_cookies_temp.txt")
        if export_cookies_from_profile(profile_dir, cookie_file):
            print(f"[OK] Cookies exported for yt-dlp")
        else:
            cookie_file = None

    try:
        transcript = transcribe_douyin_video(video_url, cookie_file=cookie_file)

        if transcript:
            print(f"[OK] Transcription successful")
            print(f"Length: {len(transcript)} characters")
            print("\nTranscript preview (first 500 chars):")
            print("-" * 60)
            print(transcript[:500])
            if len(transcript) > 500:
                print("...")
            print("-" * 60)
            return True
        else:
            print("[FAIL] Transcription returned empty result")
            print("Possible reasons:")
            print("  - yt-dlp failed to download audio")
            print("  - faster-whisper not installed")
            print("  - Cookie authentication required")
            return False

    except Exception as exc:
        print(f"[FAIL] Transcription failed: {exc}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        if cookie_file and cookie_file.exists():
            try:
                cookie_file.unlink()
            except Exception:
                pass


def main():
    print("\nDouyin Video Transcription Test\n")

    # Check dependencies
    try:
        import faster_whisper
        print("[OK] faster-whisper is installed")
    except ImportError:
        print("[FAIL] faster-whisper not installed")
        print("Run: pip install faster-whisper")
        return

    try:
        import requests
        print("[OK] requests is installed")
    except ImportError:
        print("[FAIL] requests not installed")
        print("Run: pip install requests")
        return

    print()

    # Run tests
    test_direct_audio_transcribe()
    test_cookie_export()
    # test_ytdlp_transcribe()  # 可选：测试回退方案


if __name__ == "__main__":
    main()
