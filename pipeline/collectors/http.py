from __future__ import annotations

from http.cookiejar import CookieJar
import html2text
import json
import os
import re
import socket
from urllib import parse, request

from ..cancel import raise_if_cancelled


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class HttpClient:
    def __init__(self, *, cookie_env: str = "", timeout: int = 30) -> None:
        self.cookie_env = cookie_env
        self.timeout = timeout
        self.cookie_jar = CookieJar()
        self.opener = request.build_opener(request.HTTPCookieProcessor(self.cookie_jar))

    def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        raise_if_cancelled()
        # 设置 socket 级默认超时，防止 SSL 握手无限卡死
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self.timeout)
        try:
            req = self._request(url, headers=headers)
            raise_if_cancelled()
            with self.opener.open(req, timeout=self.timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        finally:
            socket.setdefaulttimeout(old_timeout)

    def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> dict:
        return json.loads(self.get_text(url, headers=headers))

    def _request(self, url: str, *, headers: dict[str, str] | None = None) -> request.Request:
        merged = dict(DEFAULT_HEADERS)
        merged.update(headers or {})
        if self.cookie_env and os.getenv(self.cookie_env):
            merged["Cookie"] = os.getenv(self.cookie_env, "")
        return request.Request(url, headers=merged)


# ---------------------------------------------------------------------------
# HTML → Markdown / 纯文本转换器
# ---------------------------------------------------------------------------

# 主转换器：保留链接和加粗等格式，对 LLM 摘要最友好
_h2t = html2text.HTML2Text()
_h2t.ignore_links = False
_h2t.ignore_images = True
_h2t.body_width = 0
_h2t.ignore_emphasis = False

# 纯文本转换器：用于标题提取等不需要 Markdown 格式的场景
_h2t_plain = html2text.HTML2Text()
_h2t_plain.ignore_links = True
_h2t_plain.ignore_images = True
_h2t_plain.body_width = 0
_h2t_plain.ignore_emphasis = True


def strip_html(html: str) -> str:
    """将 HTML 转为 Markdown 格式（保留链接和加粗等格式信息）。"""
    return _h2t.handle(html).strip()


def _strip_html_plain(html: str) -> str:
    """将 HTML 转为纯文本（不保留 Markdown 格式，用于标题提取等场景）。"""
    return _h2t_plain.handle(html).strip()


def extract_title(html: str) -> str:
    patterns = [
        r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']',
        r'<meta\s+name=["\']twitter:title["\']\s+content=["\'](.*?)["\']',
        r"<title[^>]*>(.*?)</title>",
        r'<h1[^>]*id=["\']activity-name["\'][^>]*>(.*?)</h1>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if match:
            return " ".join(_strip_html_plain(match.group(1)).split())
    return ""


def absolute_url(base_url: str, maybe_url: str) -> str:
    return parse.urljoin(base_url, maybe_url)


def clean_text(value: str) -> str:
    """将 HTML 内容转为 Markdown 并去除首尾空白。"""
    return strip_html(value)


def compact_text(value: str, max_len: int = 120) -> str:
    text = " ".join(value.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
