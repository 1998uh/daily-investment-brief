from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .http import HttpClient
from ..config import ROOT


MOBILE_BASE = "https://i.weread.qq.com"
DEFAULT_CREDENTIALS_PATH = ROOT / "data" / "weread_credentials.json"


def credentials_path() -> Path:
    configured = os.getenv("WEREAD_CREDENTIALS_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_CREDENTIALS_PATH


class WeReadError(RuntimeError):
    """Base error for the private WeRead mobile protocol."""


class AuthExpiredError(WeReadError):
    """The access token is no longer accepted."""


class RiskControlError(WeReadError):
    """The account or session was rate limited or needs manual verification."""


class FetcherError(WeReadError):
    """The upstream response could not be parsed or classified."""


class _HttpStatusError(WeReadError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"HTTP {status}")


@dataclass(frozen=True)
class WeReadCredentials:
    vid: str
    access_token: str
    refresh_token: str = ""
    device_id: str = ""
    profile: str = "eink-2.1.2"
    device_name: str = "BOOX"
    skey: str = ""
    wx_access_token: str = ""
    guest_token: str = ""
    sync_key: int = 0
    name: str = ""
    updated_at: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "WeReadCredentials":
        return cls(
            vid=str(payload.get("vid") or ""),
            access_token=str(payload.get("accessToken") or payload.get("access_token") or ""),
            refresh_token=str(
                payload.get("refreshToken") or payload.get("refresh_token") or ""
            ),
            device_id=str(payload.get("deviceId") or payload.get("device_id") or ""),
            profile=str(payload.get("profile") or "eink-2.1.2"),
            device_name=str(payload.get("deviceName") or payload.get("device_name") or "BOOX"),
            skey=str(payload.get("skey") or ""),
            wx_access_token=str(
                payload.get("wxAccessToken") or payload.get("wx_access_token") or ""
            ),
            guest_token=str(payload.get("guestToken") or payload.get("guest_token") or ""),
            sync_key=int(payload.get("syncKey") or payload.get("sync_key") or 0),
            name=str(payload.get("name") or ""),
            updated_at=str(payload.get("updatedAt") or payload.get("updated_at") or ""),
        )

    def to_payload(self) -> dict[str, str]:
        return {
            "vid": self.vid,
            "accessToken": self.access_token,
            "refreshToken": self.refresh_token,
            "deviceId": self.device_id,
            "profile": self.profile,
            "deviceName": self.device_name,
            "skey": self.skey,
            "wxAccessToken": self.wx_access_token,
            "guestToken": self.guest_token,
            "syncKey": self.sync_key,
            "name": self.name,
            "updatedAt": self.updated_at or datetime.now(timezone.utc).isoformat(),
        }

    def usable(self) -> bool:
        return bool(self.vid and self.access_token)


class WeReadCredentialStore:
    def __init__(self, path: Path | None = None):
        self.path = path or credentials_path()

    def load(self) -> WeReadCredentials | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise FetcherError(f"读取微信读书凭证失败: {exc}") from exc
        if not isinstance(payload, dict):
            raise FetcherError("微信读书凭证格式无效")
        credentials = WeReadCredentials.from_payload(payload)
        return credentials if credentials.usable() else None

    def save(self, credentials: WeReadCredentials) -> None:
        if not credentials.usable():
            raise ValueError("vid 和 access_token 不能为空")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(credentials.to_payload(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


@dataclass(frozen=True)
class ArticleMetadata:
    review_id: str
    book_id: str
    title: str
    publish_at: datetime | None
    url: str = ""
    summary: str = ""
    author: str = ""
    raw: dict[str, Any] | None = None


def _timestamp(value: Any) -> datetime | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        number = int(float(value))
        if number > 10**12:
            number //= 1000
        return datetime.fromtimestamp(number, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return ""


def _article_from_entry(entry: dict[str, Any], book_id: str) -> ArticleMetadata | None:
    review = entry
    nested = entry.get("subReviews") or []
    if nested and isinstance(nested[0], dict):
        candidate = nested[0]
        review = candidate.get("review") or candidate
    if not isinstance(review, dict):
        return None

    mp_info = review.get("mpInfo") or review.get("mp_info") or {}
    if not isinstance(mp_info, dict):
        mp_info = {}
    review_id = str(
        _first(review, "reviewId", "review_id")
        or _first(entry, "reviewId", "review_id")
        or ""
    )
    if not review_id:
        return None
    title = str(_first(mp_info, "title") or _first(review, "title") or _first(entry, "title"))
    url = str(_first(mp_info, "doc_url", "docUrl", "url", "link"))
    publish_value = _first(
        mp_info,
        "time",
        "publishTime",
        "publish_time",
    ) or _first(review, "createTime", "create_time", "publishTime", "publish_time") or _first(
        entry, "createTime", "create_time"
    )
    return ArticleMetadata(
        review_id=review_id,
        book_id=book_id,
        title=title,
        publish_at=_timestamp(publish_value),
        url=url,
        summary=str(
            _first(review, "summary", "abstract")
            or _first(mp_info, "summary", "abstract")
        ),
        author=str(
            _first(review, "author", "nickname")
            or _first(mp_info, "author", "nickname")
        ),
        raw=entry,
    )


def parse_articles_payload(payload: dict[str, Any], book_id: str) -> list[ArticleMetadata]:
    entries = payload.get("data")
    if not isinstance(entries, list):
        entries = payload.get("reviews") or payload.get("articles") or []
    if not isinstance(entries, list):
        raise FetcherError("微信读书文章列表响应格式无效")
    articles: list[ArticleMetadata] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        article = _article_from_entry(entry, book_id)
        if article and article.review_id not in seen:
            articles.append(article)
            seen.add(article.review_id)
    return articles


def _raise_for_payload(payload: dict[str, Any]) -> None:
    code = payload.get("errCode") or payload.get("errcode") or 0
    try:
        code = int(code)
    except (TypeError, ValueError):
        code = 0
    if code == -2012:
        raise AuthExpiredError("微信读书 AccessToken 已失效（-2012）")
    if code in {-2041, -2010}:
        raise RiskControlError(f"微信读书会话需要人工处理（{code}）")
    if code:
        raise FetcherError(f"微信读书接口返回业务错误（{code}）")


def classify_http_error(error: HTTPError) -> None:
    """Preserve WeRead business errors returned inside non-2xx HTTP responses."""
    try:
        raw = error.read()
        payload = json.loads(raw.decode("utf-8", errors="replace")) if raw else None
    except (OSError, ValueError, AttributeError):
        payload = None
    if isinstance(payload, dict):
        _raise_for_payload(payload)
    if error.code in {401, 403}:
        raise AuthExpiredError(f"微信读书认证失效（{error.code}）") from error
    if error.code == 429:
        raise RiskControlError("微信读书请求过于频繁（429）") from error
    raise FetcherError(f"微信读书接口 HTTP {error.code}: {error.reason}") from error


class _DefaultTransport:
    def __init__(self):
        self.client = HttpClient(timeout=30)

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        url = f"{MOBILE_BASE}{path}?{urlencode(params)}"
        try:
            return self.client.get_json(url, headers=headers)
        except HTTPError as exc:
            classify_http_error(exc)

    def post_json(
        self,
        path: str,
        *,
        body: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        request = Request(
            f"{MOBILE_BASE}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except HTTPError as exc:
            classify_http_error(exc)


_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0


class WeReadMobileClient:
    def __init__(
        self,
        *,
        vid: str = "",
        access_token: str = "",
        credentials: WeReadCredentials | None = None,
        transport: Any | None = None,
        min_interval: float = 2.0,
    ):
        if credentials:
            vid = credentials.vid
            access_token = credentials.access_token
        self.credentials = credentials or WeReadCredentials(vid=vid, access_token=access_token)
        self.vid = vid
        self.access_token = access_token
        self.transport = transport or _DefaultTransport()
        self.min_interval = max(0.0, min_interval)

    def _headers(self) -> dict[str, str]:
        from .weread_auth import VERSION_HEADERS

        return {
            **VERSION_HEADERS,
            "vid": self.vid,
            "accessToken": self.access_token,
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        global _LAST_REQUEST_AT
        with _REQUEST_LOCK:
            wait = self.min_interval - (time.monotonic() - _LAST_REQUEST_AT)
            if wait > 0:
                time.sleep(wait)
            try:
                payload = self.transport.get_json(path, params=params, headers=self._headers())
            except _HttpStatusError as exc:
                if exc.status in {401, 403}:
                    raise AuthExpiredError(f"微信读书认证失效（{exc.status}）") from exc
                raise
            except HTTPError as exc:
                classify_http_error(exc)
            except RuntimeError as exc:
                match = re.search(r"HTTP\s+(\d+)", str(exc), re.IGNORECASE)
                if match and int(match.group(1)) in {401, 403}:
                    raise AuthExpiredError(f"微信读书认证失效（{match.group(1)}）") from exc
                if match and int(match.group(1)) == 429:
                    raise RiskControlError("微信读书请求过于频繁（429）") from exc
                raise
            finally:
                _LAST_REQUEST_AT = time.monotonic()
        if not isinstance(payload, dict):
            raise FetcherError("微信读书接口响应不是 JSON 对象")
        _raise_for_payload(payload)
        return payload

    def get_articles(
        self,
        book_id: str,
        *,
        count: int = 20,
        synckey: int | str | None = None,
        offset: int | None = None,
    ) -> list[ArticleMetadata]:
        params: dict[str, Any] = {"bookId": book_id, "count": count}
        if synckey is not None:
            params["synckey"] = synckey
        elif offset is not None:
            params["offset"] = offset
        payload = self._get_json("/mp/chapters", params)
        return parse_articles_payload(payload, book_id)

    def fetch_recent_articles(self, book_id: str, *, limit: int = 20) -> list[ArticleMetadata]:
        articles: list[ArticleMetadata] = []
        offset = 0
        first = True
        while len(articles) < limit:
            page = self.get_articles(
                book_id,
                count=min(20, limit - len(articles)),
                # synckey=0 is rejected by the API as -2041; a positive cursor
                # asks for the latest chapters from the beginning.
                synckey=1 if first else None,
                offset=None if first else offset,
            )
            first = False
            if not page:
                break
            articles.extend(page)
            if len(page) < 20:
                break
            offset += len(page)
        return articles[:limit]

    def resolve_article_url(self, review_id: str) -> str:
        payload = self._get_json("/review/single", {"reviewId": review_id})
        review = payload.get("review") or payload.get("data") or payload
        if not isinstance(review, dict):
            return ""
        mp_info = review.get("mpInfo") or review.get("mp_info") or {}
        if not isinstance(mp_info, dict):
            return ""
        return str(_first(mp_info, "doc_url", "docUrl", "url", "link"))

    def refresh(self) -> WeReadCredentials:
        """Refresh the session once; callers decide whether to retry the original request."""
        if not self.credentials.refresh_token:
            raise AuthExpiredError("微信读书没有可用 RefreshToken")
        if isinstance(self.transport, _DefaultTransport):
            from .weread_auth import WeReadAuthClient

            try:
                refreshed = WeReadAuthClient().refresh(self.credentials)
            except Exception as exc:
                raise AuthExpiredError(f"微信读书凭证续期失败: {exc}") from exc
            self.credentials = refreshed
            self.vid = refreshed.vid
            self.access_token = refreshed.access_token
            return refreshed
        post_json = getattr(self.transport, "post_json", None)
        if not callable(post_json):
            raise FetcherError("当前传输层不支持微信读书凭证续期")
        payload = post_json(
            "/login",
            body={
                "refreshToken": self.credentials.refresh_token,
                "deviceId": self.credentials.device_id,
                "vid": self.credentials.vid,
                "profile": self.credentials.profile,
            },
            headers=self._headers(),
        )
        if not isinstance(payload, dict):
            raise FetcherError("微信读书续期响应格式无效")
        _raise_for_payload(payload)
        refreshed_payload = (
            payload.get("data") if isinstance(payload.get("data"), dict) else payload
        )
        refreshed = WeReadCredentials.from_payload(refreshed_payload)
        if not refreshed.usable():
            raise AuthExpiredError("微信读书续期未返回有效凭证")
        self.credentials = replace(refreshed, profile=self.credentials.profile)
        self.vid = self.credentials.vid
        self.access_token = self.credentials.access_token
        return self.credentials
