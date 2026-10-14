import hmac
import secrets
import time
from typing import Annotated
from urllib.parse import urlencode

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlmodel import select

from app.config import Settings, get_settings
from app.infrastructure.chatgpt_auth import LOGIN_TTL_S, AuthError
from app.infrastructure.db import AuthSession, User
from app.interfaces.deps import (
    SESSION_COOKIE,
    Auth,
    Cipher,
    CurrentUser,
    Db,
    MaybeUser,
    hash_token,
)

router = APIRouter(prefix="/auth")

PROVIDER = "chatgpt"
SESSION_TTL_S = 30 * 24 * 3600
LOGIN_STATE_COOKIE = "login_state"
# Remembers this browser's last account so signing in again reuses its ChatGPT registration.
LAST_USER_COOKIE = "last_user"
LAST_USER_TTL_S = 365 * 24 * 3600


class AuthStatusOut(BaseModel):
    signed_in: bool
    email: str | None
    plan_enabled: bool


class LoginOut(BaseModel):
    authorize_url: str


class LogoutOut(BaseModel):
    revoked: bool


def _set_cookie(response: Response, key: str, value: str, max_age: int) -> None:
    response.set_cookie(key, value, max_age=max_age, httponly=True, samesite="lax")


def _last_user_id(request: Request, cipher: Cipher) -> int | None:
    try:
        return int(cipher.decrypt(request.cookies.get(LAST_USER_COOKIE, "")))
    except (InvalidToken, ValueError):
        return None


def _end_session(request: Request, db: Db) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    session = db.get(AuthSession, hash_token(token)) if token else None
    if session is not None:
        db.delete(session)
        db.commit()


@router.get("/status")
def auth_status(user: MaybeUser, auth: Auth) -> AuthStatusOut:
    if user is None:
        return AuthStatusOut(signed_in=False, email=None, plan_enabled=False)
    credentials = auth.status(user.id)
    plan_enabled = credentials is not None and credentials.signed_in and credentials.plan_enabled
    return AuthStatusOut(signed_in=True, email=user.email, plan_enabled=plan_enabled)


@router.post("/login")
def login(
    request: Request, response: Response, user: MaybeUser, auth: Auth, cipher: Cipher
) -> LoginOut:
    user_id = user.id if user else _last_user_id(request, cipher)
    authorize_url, state = auth.start_login(user_id)
    # Binds the callback to this browser so another browser's callback cannot sign it in.
    _set_cookie(response, LOGIN_STATE_COOKIE, state, LOGIN_TTL_S)
    return LoginOut(authorize_url=authorize_url)


@router.get("/callback")
def callback(
    request: Request,
    auth: Auth,
    db: Db,
    cipher: Cipher,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    params = dict(request.query_params)
    token = None
    try:
        expected = request.cookies.get(LOGIN_STATE_COOKIE, "").encode()
        if not expected or not hmac.compare_digest(params.get("state", "").encode(), expected):
            raise AuthError("invalid_state")
        credentials = auth.complete_login(params)
        user = db.exec(
            select(User).where(User.provider == PROVIDER, User.subject == credentials.subject)
        ).first()
        if user is None:
            user = User(provider=PROVIDER, subject=credentials.subject)
        user.email = credentials.email
        db.add(user)
        db.commit()
        db.refresh(user)
        auth.save(user.id, credentials)

        _end_session(request, db)
        token = secrets.token_urlsafe(32)
        db.add(
            AuthSession(
                token_hash=hash_token(token),
                user_id=user.id,
                expires_at=time.time() + SESSION_TTL_S,
            )
        )
        db.commit()
        result = "ok"
    except AuthError as e:
        result = e.code
    redirect = RedirectResponse(f"{settings.frontend_url}/?{urlencode({'auth': result})}", 303)
    redirect.delete_cookie(LOGIN_STATE_COOKIE)
    if token:
        _set_cookie(redirect, SESSION_COOKIE, token, SESSION_TTL_S)
        last_user = cipher.encrypt(str(user.id).encode()).decode()
        _set_cookie(redirect, LAST_USER_COOKIE, last_user, LAST_USER_TTL_S)
    return redirect


@router.post("/logout")
def logout(
    request: Request, response: Response, user: CurrentUser, auth: Auth, db: Db
) -> LogoutOut:
    revoked = auth.logout(user.id)
    _end_session(request, db)
    response.delete_cookie(SESSION_COOKIE)
    return LogoutOut(revoked=revoked)
