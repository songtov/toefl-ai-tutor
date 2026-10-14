from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlalchemy.engine import Engine
from sqlmodel import Field, SQLModel, create_engine


def _now() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    __tablename__ = "users"
    # Emails can repeat across sign-in providers and ChatGPT workspaces, so the identity is
    # the provider's subject.
    __table_args__ = (UniqueConstraint("provider", "subject"),)
    id: int | None = Field(default=None, primary_key=True)
    provider: str
    subject: str
    email: str = ""
    password_hash: str = ""
    role: str = "learner"


class AuthSession(SQLModel, table=True):
    __tablename__ = "auth_sessions"
    token_hash: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    expires_at: float


class ChatGPTCredential(SQLModel, table=True):
    __tablename__ = "chatgpt_credentials"
    user_id: int = Field(foreign_key="users.id", primary_key=True)
    ciphertext: str


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
