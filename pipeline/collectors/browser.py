"""通过 Playwright 无头浏览器绕过阿里云 WAF 获取雪球 API 数据。

策略：先访问雪球首页通过 WAF JS 质询，然后在浏览器上下文中
用 fetch() 请求 API 端点，继承 WAF 颁发的所有 cookie。

可选依赖：需要 pip install playwright && playwright install chromium。
未安装时 HAS_PLAYWRIGHT=False，所有函数返回空值，不影响其他功能。

线程安全：Playwright sync API 基于 greenlet，必须在创建它的同一线程中
调用。本模块使用专用后台线程 + 队列实现线程安全，任意线程可调用
fetch_json / fetch_status_detail。
"""
from __future__ import annotations

import logging
import os
import queue
import threading
from typing import Any

log = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


# ---------------------------------------------------------------------------
# 专用 Playwright 线程：所有浏览器操作在这个线程中执行
# ---------------------------------------------------------------------------

_request_q: queue.Queue[tuple[str, threading.Event, list]] = queue.Queue()
_thread: threading.Thread | None = None
_thread_lock = threading.Lock()
_shutdown = False


def _pw_worker() -> None:
    """Playwright 专用线程的主循环。

    在此线程中初始化浏览器、通过 WAF、处理所有 fetch 请求。
    """
    browser = None
    context = None
    page = None
    waf_passed = False

    try:
        pw = sync_playwright().start()
        # 允许通过环境变量指定本地已有的 Chromium/Chrome 可执行文件，
        # 避免 playwright 版本与已下载浏览器版本号不一致时报“浏览器未安装”。
        launch_kwargs: dict[str, Any] = {"headless": True}
        exe_path = os.getenv("XUEQIU_CHROME_PATH", "")
        if exe_path:
            launch_kwargs["executable_path"] = exe_path
        browser = pw.chromium.launch(**launch_kwargs)
        log.debug("Playwright worker: Chromium 已启动")

        # 设置 cookie
        cookie = os.getenv("XUEQIU_COOKIE", "")
        cookies = []
        for part in cookie.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                cookies.append({
                    "name": k.strip(),
                    "value": v.strip(),
                    "domain": ".xueqiu.com",
                    "path": "/",
                })

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
        )
        if cookies:
            context.add_cookies(cookies)

        page = context.new_page()

        # 处理请求队列
        while True:
            try:
                item = _request_q.get(timeout=1.0)
            except queue.Empty:
                if _shutdown:
                    break
                continue

            api_url, event, result_box = item
            if api_url == "__SHUTDOWN__":
                event.set()
                break

            # 首次使用时通过 WAF
            if not waf_passed:
                try:
                    log.debug("Playwright worker: 访问雪球首页通过 WAF ...")
                    page.goto(
                        "https://xueqiu.com/",
                        timeout=30000,
                        wait_until="domcontentloaded",
                    )
                    page.wait_for_timeout(3000)
                    waf_passed = True
                    log.debug("Playwright worker: WAF 已通过")
                except Exception as exc:
                    log.warning(f"Playwright worker: WAF 失败: {exc}")
                    result_box.append(None)
                    event.set()
                    continue

            # 执行 fetch
            try:
                result = page.evaluate("""async (url) => {
                    try {
                        const resp = await fetch(url, {
                            headers: {
                                'Accept': 'application/json, text/plain, */*',
                                'X-Requested-With': 'XMLHttpRequest',
                            }
                        });
                        if (!resp.ok) return {_error: `HTTP ${resp.status}`};
                        const text = await resp.text();
                        try { return JSON.parse(text); }
                        catch(e) { return {_error: 'not JSON', _body: text.substring(0, 200)}; }
                    } catch(e) {
                        return {_error: e.toString()};
                    }
                }""", api_url)

                if isinstance(result, dict) and result.get("_error"):
                    log.debug(f"Playwright fetch 失败: {api_url} -> {result['_error']}")
                    result_box.append(None)
                else:
                    result_box.append(result)
            except Exception as exc:
                log.debug(f"Playwright evaluate 失败: {exc}")
                result_box.append(None)

            event.set()

    except Exception as exc:
        log.warning(f"Playwright worker 线程异常: {exc}")
        # 清空队列中等待的请求
        while not _request_q.empty():
            try:
                _, event, result_box = _request_q.get_nowait()
                result_box.append(None)
                event.set()
            except queue.Empty:
                break
    finally:
        for obj in [page, context, browser]:
            if obj:
                try:
                    obj.close()
                except Exception:
                    pass
        log.debug("Playwright worker: 已退出")


def _ensure_worker() -> None:
    """确保 Playwright worker 线程已启动。"""
    global _thread
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(target=_pw_worker, daemon=True, name="playwright-worker")
        _thread.start()


# ---------------------------------------------------------------------------
# 公开接口（线程安全，可从任意线程调用）
# ---------------------------------------------------------------------------

def fetch_json(api_url: str) -> dict | None:
    """在浏览器上下文中用 fetch() 请求雪球 API，返回 JSON dict。

    利用浏览器已通过 WAF 质询的身份，继承所有 cookie 和会话状态。
    通过专用线程 + 队列实现线程安全。
    """
    if not HAS_PLAYWRIGHT:
        return None

    _ensure_worker()

    event = threading.Event()
    result_box: list[Any] = []
    _request_q.put((api_url, event, result_box))
    event.wait(timeout=30)  # 最多等 30 秒

    return result_box[0] if result_box else None


def fetch_status_detail(status_id: str) -> dict | None:
    """获取单条雪球 status 的详情（含全文）。"""
    url = f"https://xueqiu.com/statuses/show.json?id={status_id}"
    return fetch_json(url)


def close_browser() -> None:
    """关闭浏览器（进程退出时调用）。"""
    global _shutdown
    _shutdown = True
    if _thread is not None and _thread.is_alive():
        event = threading.Event()
        _request_q.put(("__SHUTDOWN__", event, []))
        event.wait(timeout=10)
