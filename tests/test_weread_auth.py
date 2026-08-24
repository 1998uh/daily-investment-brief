import base64
import json

from pipeline.collectors.weread_auth import (
    DEVICE_NAME,
    DEVICE_TYPE,
    PROFILE_NAME,
    WeReadAuthClient,
    WeReadCredentials,
    new_device_id,
    qr_data_uri,
    signature,
)


def test_mobile_auth_helpers_generate_expected_shapes():
    device_id = new_device_id()

    assert device_id.startswith("eink334691225")
    assert device_id[len("eink334691225") :].isdigit()
    assert len(signature(123, device_id, 7)) == 64
    encoded = qr_data_uri("https://example.test/confirm")
    assert encoded.startswith("data:image/png;base64,")
    base64.b64decode(encoded.split(",", 1)[1])


def test_exchange_qr_sends_eink_profile_and_maps_credentials():
    class Response:
        ok = True
        status_code = 200

        def json(self):
            return {
                "vid": "123456",
                "accessToken": "access-1",
                "refreshToken": "refresh-1",
                "skey": "skey-1",
                "user": {"name": "测试账号"},
            }

        def raise_for_status(self):
            return None

    class Session:
        def __init__(self):
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return Response()

    session = Session()
    credentials = WeReadAuthClient(session=session).exchange_qr("wx-code", device_id="device-1")

    assert credentials.vid == "123456"
    assert credentials.access_token == "access-1"
    assert credentials.refresh_token == "refresh-1"
    assert credentials.device_id == "device-1"
    body = json.loads(session.calls[0][1]["data"])
    assert body["code"] == "wx-code"
    assert body["deviceName"] == DEVICE_NAME
    assert body["deviceType"] == DEVICE_TYPE
    assert credentials.profile == PROFILE_NAME


def test_refresh_rejects_changed_vid_and_preserves_account_identity():
    class Response:
        ok = True
        status_code = 200

        def json(self):
            return {"vid": "different", "accessToken": "new-access"}

    class Session:
        def post(self, url, **kwargs):
            return Response()

    credentials = WeReadCredentials(
        vid="123456",
        access_token="old-access",
        refresh_token="refresh-1",
        device_id="device-1",
    )

    try:
        WeReadAuthClient(session=Session()).refresh(credentials)
    except RuntimeError as exc:
        assert "不同账号" in str(exc)
    else:
        raise AssertionError("refresh should reject a changed VID")
