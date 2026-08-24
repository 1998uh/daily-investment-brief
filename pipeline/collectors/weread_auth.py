from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import secrets
import time
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import quote
import webbrowser

import qrcode
import requests

from .weread_mobile import WeReadCredentialStore, WeReadCredentials


WEREAD_BASE = "https://i.weread.qq.com"
WX_APPID = "wxab9b71ad2b90ff34"
WX_SCOPE = "snsapi_userinfo,snsapi_timeline,snsapi_friend"
PROFILE_NAME = "eink-2.1.2"
DEVICE_NAME = "BOOX"
DEVICE_TYPE = 3
VERSION_HEADERS = {
    "baseapi": "30",
    "appver": "2.1.2.10245900",
    "basever": "2.1.2.10245900",
    "osver": "11",
    "channelId": "900",
    "User-Agent": (
        "WeRead/2.1.2 WRBrand/Onyx wr_eink "
        "Dalvik/2.1.0 (Linux; U; Android 11; BOOX Build/onyx)"
    ),
}


class WeReadAuthError(RuntimeError):
    pass


class QRExpiredError(WeReadAuthError):
    pass


class QRDeclinedError(WeReadAuthError):
    pass


@dataclass(frozen=True)
class QRRequest:
    uuid: str
    confirm_url: str
    qr_data_uri: str


@dataclass(frozen=True)
class PollResult:
    status: str
    errcode: int
    wx_code: str = ""


@dataclass(frozen=True)
class SessionInitResult:
    guest_token: str = ""
    sync_key: int = 0
    warnings: tuple[str, ...] = ()


def _digits(length: int) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def new_device_id() -> str:
    return "eink334691225" + str(secrets.randbits(63)).zfill(19)


def new_install_id() -> str:
    return "eink31" + _digits(26)


def signature(timestamp_ms: int, device_id: str, random_value: int) -> str:
    return hashlib.sha256(f"{timestamp_ms}{device_id}{random_value}".encode()).hexdigest()


def qr_data_uri(text: str) -> str:
    qr = qrcode.QRCode(version=None, box_size=8, border=3)
    qr.add_data(text)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


class WeReadAuthClient:
    def __init__(self, *, timeout: float = 25.0, session: requests.Session | None = None):
        self.timeout = float(timeout)
        self.session = session or requests.Session()

    @staticmethod
    def version_headers() -> dict[str, str]:
        return dict(VERSION_HEADERS)

    @staticmethod
    def auth_headers(credentials: WeReadCredentials) -> dict[str, str]:
        headers = dict(VERSION_HEADERS)
        headers.update({"vid": credentials.vid, "accessToken": credentials.access_token})
        return headers

    @staticmethod
    def _payload_error(payload: dict[str, Any]) -> tuple[int, str]:
        code = payload.get("errcode", payload.get("errCode", 0))
        try:
            code = int(code or 0)
        except (TypeError, ValueError):
            code = 0
        return code, str(payload.get("errmsg") or payload.get("errMsg") or "")

    def _json_response(self, response: requests.Response, label: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise WeReadAuthError(f"{label} 返回非 JSON 数据") from exc
        if not isinstance(payload, dict):
            raise WeReadAuthError(f"{label} 返回格式异常")
        return payload

    def request_qr(self) -> QRRequest:
        response = self.session.get(
            f"{WEREAD_BASE}/wxticket",
            params={"nonceStr": "weread"},
            headers=VERSION_HEADERS,
            timeout=self.timeout,
        )
        response.raise_for_status()
        ticket = self._json_response(response, "微信读书二维码 ticket")
        signature_value = ticket.get("signature")
        timestamp = ticket.get("timeStamp")
        if not isinstance(signature_value, str) or not signature_value or timestamp is None:
            code, message = self._payload_error(ticket)
            raise WeReadAuthError(f"微信读书二维码 ticket 获取失败: {code or ''} {message}".strip())

        response = self.session.get(
            "https://open.weixin.qq.com/connect/sdk/qrconnect",
            params={
                "appid": WX_APPID,
                "noncestr": "weread",
                "timestamp": str(timestamp),
                "scope": WX_SCOPE,
                "signature": signature_value,
            },
            headers={"User-Agent": VERSION_HEADERS["User-Agent"]},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = self._json_response(response, "微信二维码")
        try:
            errcode = int(payload.get("errcode", -1))
        except (TypeError, ValueError):
            errcode = -1
        uuid = payload.get("uuid")
        if errcode != 0 or not isinstance(uuid, str) or not uuid:
            raise WeReadAuthError(f"微信二维码生成失败: {errcode}")
        confirm_url = f"https://open.weixin.qq.com/connect/confirm?uuid={quote(uuid, safe='')}"
        return QRRequest(uuid=uuid, confirm_url=confirm_url, qr_data_uri=qr_data_uri(confirm_url))

    def poll_qr_once(
        self,
        uuid: str,
        *,
        last: int | None = None,
        timeout: float | None = None,
    ) -> PollResult:
        params: dict[str, Any] = {"f": "json", "uuid": uuid}
        if last is not None:
            params["last"] = str(last)
        response = self.session.get(
            "https://long.open.weixin.qq.com/connect/l/qrconnect",
            params=params,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout or min(self.timeout, 25.0),
        )
        response.raise_for_status()
        payload = self._json_response(response, "微信扫码状态")
        try:
            code = int(payload.get("wx_errcode", 0))
        except (TypeError, ValueError):
            code = 0
        wx_code = str(payload.get("wx_code") or "")
        if code == 405:
            if not wx_code:
                raise WeReadAuthError("扫码已确认，但微信没有返回登录 code")
            return PollResult("confirmed", code, wx_code)
        if code == 404:
            return PollResult("scanned", code)
        if code == 408:
            return PollResult("waiting", code)
        if code == 402:
            raise QRExpiredError("二维码已过期，请重新生成")
        if code == 403:
            raise QRDeclinedError("你在微信中取消了登录，请重新生成二维码")
        raise WeReadAuthError(f"未知扫码状态: {code}")

    def exchange_qr(self, wx_code: str, *, device_id: str | None = None) -> WeReadCredentials:
        device_id = device_id or new_device_id()
        timestamp = int(time.time() * 1000)
        random_value = secrets.randbelow(1000)
        body = {
            "appFirstInstall": 1,
            "code": wx_code,
            "deviceId": device_id,
            "deviceName": DEVICE_NAME,
            "installId": new_install_id(),
            "isAutoLogout": 0,
            "isFromQrcode": 1,
            "random": random_value,
            "signature": signature(timestamp, device_id, random_value),
            "timestamp": timestamp,
            "trackId": "",
            "deviceType": DEVICE_TYPE,
        }
        headers = {**VERSION_HEADERS, "Content-Type": "application/json; charset=UTF-8"}
        response = self.session.post(
            f"{WEREAD_BASE}/login",
            headers=headers,
            data=json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode(),
            timeout=self.timeout,
        )
        payload = self._json_response(response, "微信读书扫码登录")
        code, message = self._payload_error(payload)
        access_token = str(payload.get("accessToken") or "")
        refresh_token = str(payload.get("refreshToken") or "")
        if not response.ok or not access_token or not refresh_token:
            raise WeReadAuthError(f"微信读书登录失败: {code or response.status_code} {message}".strip())
        user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
        credentials = WeReadCredentials(
            vid=str(payload.get("vid") or ""),
            access_token=access_token,
            refresh_token=refresh_token,
            device_id=device_id,
            device_name=DEVICE_NAME,
            profile=PROFILE_NAME,
            skey=str(payload.get("skey") or ""),
            wx_access_token=str(payload.get("wxAccessToken") or ""),
            name=str(user.get("name") or ""),
            updated_at=str(int(time.time())),
        )
        if not credentials.vid.isdigit() or not credentials.access_token:
            raise WeReadAuthError("登录结果中的 VID 或 accessToken 无效")
        return credentials

    def refresh(self, credentials: WeReadCredentials) -> WeReadCredentials:
        if not credentials.refresh_token or not credentials.device_id:
            raise WeReadAuthError("当前凭证没有 refreshToken/deviceId，请重新扫码")
        timestamp = int(time.time() * 1000)
        random_value = secrets.randbelow(1000) + 1
        body = {
            "deviceId": credentials.device_id,
            "deviceName": credentials.device_name or DEVICE_NAME,
            "inBackground": 0,
            "kickType": 1,
            "random": random_value,
            "refCgi": "",
            "refreshToken": credentials.refresh_token,
            "signature": signature(timestamp, credentials.device_id, random_value),
            "timestamp": timestamp,
            "trackId": "",
            "deviceType": DEVICE_TYPE,
        }
        headers = {**VERSION_HEADERS, "Content-Type": "application/json; charset=UTF-8"}
        response = self.session.post(
            f"{WEREAD_BASE}/login",
            headers=headers,
            data=json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode(),
            timeout=self.timeout,
        )
        payload = self._json_response(response, "微信读书凭证续期")
        code, message = self._payload_error(payload)
        access_token = str(payload.get("accessToken") or "")
        if not response.ok or not access_token:
            raise WeReadAuthError(f"凭证续期失败: {code or response.status_code} {message}".strip())
        new_vid = str(payload.get("vid") or credentials.vid)
        if new_vid != credentials.vid:
            raise WeReadAuthError("续期返回了不同账号的 VID，已拒绝覆盖本地凭证")
        user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
        return WeReadCredentials(
            vid=credentials.vid,
            access_token=access_token,
            refresh_token=str(payload.get("refreshToken") or credentials.refresh_token),
            device_id=credentials.device_id,
            device_name=credentials.device_name or DEVICE_NAME,
            profile=credentials.profile or PROFILE_NAME,
            skey=str(payload.get("skey") or credentials.skey),
            wx_access_token=str(payload.get("wxAccessToken") or credentials.wx_access_token),
            guest_token=credentials.guest_token,
            sync_key=credentials.sync_key,
            name=str(user.get("name") or credentials.name),
            updated_at=str(int(time.time())),
        )

    def initialize_feature(self, credentials: WeReadCredentials) -> SessionInitResult:
        warnings: list[str] = []
        try:
            response = self.session.get(
                f"{WEREAD_BASE}/feature",
                params={"synckey": max(int(credentials.sync_key or 0), 0)},
                headers=self.auth_headers(credentials),
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = self._json_response(response, "微信读书 feature")
            code, message = self._payload_error(payload)
            if code:
                warnings.append(f"feature 初始化返回 {code}: {message}")
                return SessionInitResult(warnings=tuple(warnings))
            feature = payload.get("feature") if isinstance(payload.get("feature"), dict) else {}
            try:
                sync_key = int(payload.get("synckey") or 0)
            except (TypeError, ValueError):
                sync_key = 0
            return SessionInitResult(
                guest_token=str(feature.get("guest_token") or ""),
                sync_key=sync_key,
                warnings=tuple(warnings),
            )
        except Exception as exc:
            warnings.append(f"feature 初始化失败: {exc}")
            return SessionInitResult(warnings=tuple(warnings))


def login_mobile_interactive(
    *,
    store: WeReadCredentialStore | None = None,
    qr_path: Path | None = None,
    timeout_seconds: int = 300,
) -> WeReadCredentials:
    """Run the one-time QR login flow from the terminal without exposing tokens."""
    store = store or WeReadCredentialStore()
    client = WeReadAuthClient()
    qr = client.request_qr()
    target = qr_path or store.path.with_name("weread_login_qr.png")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(base64.b64decode(qr.qr_data_uri.split(",", 1)[1]))
    print(f"微信读书二维码已保存: {target}")
    print(f"如无法打开图片，可在浏览器打开确认地址: {qr.confirm_url}")
    try:
        webbrowser.open(target.resolve().as_uri())
    except Exception:
        pass

    deadline = time.time() + max(60, int(timeout_seconds))
    last: int | None = None
    while time.time() < deadline:
        try:
            poll = client.poll_qr_once(qr.uuid, last=last, timeout=20)
        except requests.Timeout:
            continue
        last = poll.errcode
        if poll.status == "scanned":
            print("已扫码，请在微信中确认登录。")
            continue
        if poll.status == "waiting":
            continue
        credentials = client.exchange_qr(poll.wx_code)
        init = client.initialize_feature(credentials)
        credentials = replace(
            credentials,
            guest_token=init.guest_token or credentials.guest_token,
            sync_key=init.sync_key or credentials.sync_key,
        )
        store.save(credentials)
        if init.warnings:
            print("登录成功，但 feature 初始化有提示: " + "；".join(init.warnings[:2]))
        else:
            print(f"微信读书移动凭证已保存: {store.path}")
        return credentials
    raise QRExpiredError("二维码登录超时，请重新运行 auth-login")
