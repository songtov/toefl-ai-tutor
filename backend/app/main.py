from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.infrastructure.db import init_db, make_engine
from app.interfaces.api import router


def create_app(database_url: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = make_engine(database_url or get_settings().database_url)
        init_db(app.state.engine)
        yield

    app = FastAPI(title="english-ai-tutor", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
