from __future__ import annotations

import pytest
from agent.auth import hash_password, verify_password, create_token, decode_token


def test_hash_is_bcrypt():
    h = hash_password("secret")
    assert h.startswith("$2b$")


def test_verify_correct_password():
    h = hash_password("secret")
    assert verify_password("secret", h) is True


def test_verify_wrong_password():
    h = hash_password("secret")
    assert verify_password("wrong", h) is False


def test_create_and_decode_token():
    token = create_token({"sub": "user-123"})
    claims = decode_token(token)
    assert claims["sub"] == "user-123"


def test_decode_invalid_token_raises():
    with pytest.raises(ValueError):
        decode_token("not.a.token")


def test_create_token_rejects_nonpositive_expiry():
    with pytest.raises(ValueError):
        create_token({"sub": "x"}, expires_minutes=0)
    with pytest.raises(ValueError):
        create_token({"sub": "x"}, expires_minutes=-5)
