from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from agent.config import get_agent_settings

_DEFAULT_ALGORITHM = "HS256"
_DEFAULT_EXPIRE_MINUTES = 10080  # 7 days


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _get_secret_and_algo() -> tuple[str, str]:
    try:
        settings = get_agent_settings()
        secret = settings.jwt_secret
        algorithm = settings.jwt_algorithm or _DEFAULT_ALGORITHM
    except Exception:
        secret = "test-secret-key-not-for-production"
        algorithm = _DEFAULT_ALGORITHM
    return secret, algorithm


def create_token(data: dict[str, Any], expires_minutes: int | None = None) -> str:
    secret, algorithm = _get_secret_and_algo()
    if expires_minutes is None:
        try:
            settings = get_agent_settings()
            expires_minutes = settings.jwt_expire_minutes
        except Exception:
            expires_minutes = _DEFAULT_EXPIRE_MINUTES
    payload = dict(data)
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(token: str) -> dict[str, Any]:
    secret, algorithm = _get_secret_and_algo()
    try:
        return jwt.decode(token, secret, algorithms=[algorithm])
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc
