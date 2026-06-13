from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

import agent.auth as _auth_mod
from agent.auth import create_token, hash_password, verify_password
from agent.config import AgentSettings
from agent.db import create_user, get_user_by_username
from agent.dependencies import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Module-level dummy hash for constant-time comparison (timing attack fix).
# bcrypt is slow by design; computing once at import is fine.
_DUMMY_HASH = _auth_mod.hash_password("dummy-constant-time-placeholder")


def _settings(request: Request) -> AgentSettings:
    return request.app.state.settings


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/register")
async def register(body: RegisterRequest, request: Request):
    cfg = _settings(request)
    existing = await get_user_by_username(cfg.db_path, body.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")
    user = await create_user(cfg.db_path, body.username, body.email, hash_password(body.password))
    return {"id": user["id"], "username": user["username"]}


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    cfg = _settings(request)
    user = await get_user_by_username(cfg.db_path, body.username)
    hash_to_check = user["password_hash"] if user else _DUMMY_HASH
    password_ok = verify_password(body.password, hash_to_check)
    if not user or not password_ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token({"sub": user["id"]})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=cfg.jwt_expire_minutes * 60,
    )
    return {"access_token": token, "token_type": "bearer"}


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    user = await get_current_user(request)
    cfg = _settings(request)
    token = create_token({"sub": user["id"]})
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="lax",
                        max_age=cfg.jwt_expire_minutes * 60)
    return {"access_token": token, "token_type": "bearer"}
