import hashlib
import time
from collections.abc import Iterator
from typing import Annotated

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from app.infrastructure.chatgpt_auth import ChatGPTAuth
from app.infrastructure.db import AuthSession, User

SESSION_COOKIE = "session"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_db(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as db:
        yield db


def get_auth(request: Request) -> ChatGPTAuth:
    return request.app.state.auth


def get_fernet(request: Request) -> Fernet:
    return request.app.state.fernet


Db = Annotated[Session, Depends(get_db)]
Auth = Annotated[ChatGPTAuth, Depends(get_auth)]
Cipher = Annotated[Fernet, Depends(get_fernet)]


def optional_user(request: Request, db: Db) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    session = db.get(AuthSession, hash_token(token))
    if session is None or session.expires_at < time.time():
        return None
    return db.get(User, session.user_id)


def current_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise HTTPException(401, "sign_in_required")
    return user


MaybeUser = Annotated[User | None, Depends(optional_user)]
CurrentUser = Annotated[User, Depends(current_user)]
