from __future__ import annotations

import os
from pathlib import Path
import re


PLATFORM_COOKIE_ENV = {
    "xueqiu": "XUEQIU_COOKIE",
    "weibo": "WEIBO_COOKIE",
    "douyin": "DOUYIN_COOKIE",
}

ROOT = Path(__file__).resolve().parents[2]


def platform_cookie_file(platform: str, environ: dict[str, str] | None = None) -> Path:
    """Resolve the secret file that the collectors read for this platform."""
    env = environ if environ is not None else os.environ
    env_name = PLATFORM_COOKIE_ENV.get(platform)
    if not env_name:
        raise ValueError(f"unsupported cookie platform: {platform}")
    configured = str(env.get(f"{env_name}_FILE", "") or "").strip()
    if configured:
        return Path(configured)
    return ROOT / "secrets" / f"{platform}_cookie.txt"


def cookie_header_from_items(cookies: list[dict]) -> str:
    """Build a Cookie header from Playwright cookie items, keeping first values."""
    seen: dict[str, str] = {}
    for cookie in cookies:
        name = str(cookie.get("name") or "")
        value = str(cookie.get("value") or "")
        if name and name not in seen:
            seen[name] = value
    return "; ".join(f"{name}={value}" for name, value in seen.items())


def browser_cookies_from_header(cookie: str, domain: str) -> list[dict]:
    """Convert a Cookie header into Playwright add_cookies items."""
    items: list[dict] = []
    for part in (cookie or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name.strip():
            items.append(
                {
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": domain,
                    "path": "/",
                }
            )
    return items

_SECRET_PATTERN = re.compile(
    r"(?i)(xq_a_token|sessionid_ss|sessionid|wr_skey|wr_vid|wr_rt|odin_tt|ttwid|"
    r"u|SUB|ALF|SSOLoginState|XSRF-TOKEN|WEIBO_COOKIE|DOUYIN_COOKIE|WEREAD_COOKIE)"
    r"\s*=\s*[^;\s]+"
)


def cookie_file_env(platform: str) -> str:
    env_name = PLATFORM_COOKIE_ENV.get(platform)
    if not env_name:
        raise ValueError(f"unsupported cookie platform: {platform}")
    return f"{env_name}_FILE"


def load_platform_cookie(platform: str, *, environ: dict[str, str] | None = None) -> str:
    """Read a platform cookie without logging or exposing its value.

    Explicit environment values win over a mounted file so local development and
    container secret mounts can use the same collector code.
    """
    env = environ if environ is not None else os.environ
    env_name = PLATFORM_COOKIE_ENV.get(platform)
    if not env_name:
        raise ValueError(f"unsupported cookie platform: {platform}")
    value = str(env.get(env_name, "") or "").strip()
    if value:
        return value
    configured = str(env.get(cookie_file_env(platform), "") or "").strip()
    if not configured:
        return ""
    try:
        return Path(configured).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


def inject_platform_cookie_files(
    environ: dict[str, str] | None = None,
    *,
    prefer_file: bool = False,
) -> None:
    """Populate process environment from configured cookie files when needed."""
    env = environ if environ is not None else os.environ
    for platform, env_name in PLATFORM_COOKIE_ENV.items():
        if not prefer_file and str(env.get(env_name, "") or "").strip():
            continue
        file_path = str(env.get(cookie_file_env(platform), "") or "").strip()
        if prefer_file and file_path:
            try:
                cookie = Path(file_path).read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError):
                cookie = ""
        else:
            cookie = load_platform_cookie(platform, environ=env)
        if prefer_file and file_path:
            # Clear a rotated/deleted secret too; never retain a revoked value
            # from an earlier daemon pass in the process environment.
            env[env_name] = cookie
        elif cookie:
            env[env_name] = cookie


def redact_secret_text(value: object) -> str:
    """Remove cookie-like values before errors enter logs or health records."""
    text = str(value or "")
    text = _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    return re.sub(r"(?i)(cookie|authorization)\s*[:=]\s*[^\s,;]+", r"\1=<redacted>", text)


def platform_cookie_is_usable(platform: str, cookie: str) -> bool:
    """Check the minimum login token before treating a secret as configured."""
    required = {
        "xueqiu": ("xq_a_token",),
        "weibo": ("SUB",),
        "douyin": ("sessionid", "sessionid_ss"),
    }.get(platform)
    if not required:
        raise ValueError(f"unsupported cookie platform: {platform}")
    names = {
        part.strip().split("=", 1)[0]
        for part in (cookie or "").split(";")
        if "=" in part
    }
    return any(name in names for name in required)
