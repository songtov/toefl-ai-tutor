from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, create_engine

DEFAULT_USER_ID = 1


def _now() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True)
    password_hash: str = ""
    role: str = "learner"


class StudySession(SQLModel, table=True):
    __tablename__ = "sessions"
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    plan: list[dict[str, Any]] = Field(sa_column=Column(JSON))
    plan_reason: str
    started_at: datetime = Field(default_factory=_now)
    cost_usd: float = 0.0


class Task(SQLModel, table=True):
    __tablename__ = "tasks"
    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="sessions.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    type: str
    difficulty: str
    target_weakness: str | None = None
    content: dict[str, Any] = Field(sa_column=Column(JSON))


class Response(SQLModel, table=True):
    __tablename__ = "responses"
    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="tasks.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    text: str
    visibility: str = "private"
    created_at: datetime = Field(default_factory=_now)


class Result(SQLModel, table=True):
    __tablename__ = "results"
    id: int | None = Field(default=None, primary_key=True)
    response_id: int = Field(foreign_key="responses.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    score: int
    rubric: list[dict[str, Any]] = Field(sa_column=Column(JSON))
    corrections: list[dict[str, Any]] = Field(sa_column=Column(JSON))
    model: str
    prompt_version: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


def make_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        if db.get(User, DEFAULT_USER_ID) is None:
            db.add(User(id=DEFAULT_USER_ID, email="me@localhost"))
            db.commit()
