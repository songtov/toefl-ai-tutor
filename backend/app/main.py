from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.infrastructure.chatgpt_auth import (
    AuthError,
    ChatGPTAuth,
    CredentialStore,
    EncryptedCredentialStore,
    load_host_id,
)
from app.infrastructure.chatgpt_plan_provider import PlanRequestError
from app.infrastructure.db import init_db, make_engine
from app.infrastructure.task_bank import load_sets
from app.interfaces import auth_api
from app.interfaces.api import router
from app.interfaces.security import require_json_for_writes

ALLOWED_HOSTS = ["127.0.0.1", "localhost", "backend"]
AUTH_ERROR_STATUS = {"sign_in_required": 401, "plan_not_enabled": 403}


def _make_auth(store: CredentialStore) -> ChatGPTAuth:
    settings = get_settings()
    return ChatGPTAuth(
        store,
        host_id=load_host_id(Path(settings.chatgpt_auth_dir)),
        redirect_uri=f"http://127.0.0.1:{settings.oauth_callback_port}/auth/callback",
        agent_name=settings.agent_name,
        http=httpx.Client(timeout=settings.llm_timeout_s),
    )


def create_app(
    database_url: str | None = None,
    encryption_key: str | None = None,
    make_auth: Callable[[CredentialStore], ChatGPTAuth] = _make_auth,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        key = encryption_key or settings.token_encryption_key
        if not key:
            raise RuntimeError("TOKEN_ENCRYPTION_KEY must be set in backend/.env")
        app.state.engine = make_engine(database_url or settings.database_url)
        init_db(app.state.engine)
        load_sets()
        app.state.fernet = Fernet(key)
        app.state.auth = make_auth(EncryptedCredentialStore(app.state.engine, app.state.fernet))
        yield

    app = FastAPI(
        title="english-ai-tutor",
        lifespan=lifespan,
        dependencies=[Depends(require_json_for_writes)],
    )
    # Rejects DNS-rebinding requests, which would otherwise reach this API from other sites.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.include_router(router)
    app.include_router(auth_api.router)

    @app.exception_handler(AuthError)
    def auth_error(_: Request, e: AuthError) -> JSONResponse:
        return JSONResponse({"detail": e.code}, AUTH_ERROR_STATUS.get(e.code, 502))

    @app.exception_handler(PlanRequestError)
    def plan_error(_: Request, e: PlanRequestError) -> JSONResponse:
        return JSONResponse({"detail": e.code, "request_id": e.request_id}, e.status_code)

    return app


app = create_app()
