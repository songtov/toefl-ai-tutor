from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.infrastructure.chatgpt_auth import AuthError, ChatGPTAuth

router = APIRouter(prefix="/auth")


def get_auth(request: Request) -> ChatGPTAuth:
    return request.app.state.auth


Auth = Annotated[ChatGPTAuth, Depends(get_auth)]


class AuthStatusOut(BaseModel):
    signed_in: bool
    email: str | None
    plan_enabled: bool


class LoginOut(BaseModel):
    authorize_url: str


class LogoutOut(BaseModel):
    revoked: bool


@router.get("/status")
def auth_status(auth: Auth) -> AuthStatusOut:
    credentials = auth.status()
    if credentials is None or not credentials.signed_in:
        return AuthStatusOut(signed_in=False, email=None, plan_enabled=False)
    return AuthStatusOut(
        signed_in=True, email=credentials.email, plan_enabled=credentials.plan_enabled
    )


@router.post("/login")
def login(auth: Auth) -> LoginOut:
    return LoginOut(authorize_url=auth.start_login())


@router.get("/callback")
def callback(
    request: Request, auth: Auth, settings: Annotated[Settings, Depends(get_settings)]
) -> RedirectResponse:
    try:
        auth.complete_login(dict(request.query_params))
        result = "ok"
    except AuthError as e:
        result = e.code
    return RedirectResponse(f"{settings.frontend_url}/?{urlencode({'auth': result})}", 303)


@router.post("/logout")
def logout(auth: Auth) -> LogoutOut:
    return LogoutOut(revoked=auth.logout())
