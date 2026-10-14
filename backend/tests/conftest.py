import secrets
import time
from collections.abc import Iterator

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlmodel import Session

from app.application.llm import LLMResult, Usage
from app.domain.assessment import Corrections, DiscussionScore, Score
from app.infrastructure.chatgpt_auth import ChatGPTAuth, CredentialStore
from app.infrastructure.db import AuthSession, User
from app.interfaces.api import get_provider
from app.interfaces.deps import SESSION_COOKIE, hash_token
from app.main import create_app

ENCRYPTION_KEY = Fernet.generate_key().decode()

CANNED: dict[type[BaseModel], dict] = {
    Score: {
        "score": 3,
        "criteria": [
            {"criterion": "task_completion", "rationale": "Two of three covered."},
            {"criterion": "organization", "rationale": "Mostly logical."},
            {"criterion": "language_use", "rationale": "Some tense errors."},
            {"criterion": "tone_and_register", "rationale": "Polite."},
        ],
    },
    DiscussionScore: {
        "score": 4,
        "criteria": [
            {"criterion": "relevance_and_contribution", "rationale": "Adds a new point."},
            {"criterion": "development", "rationale": "One example."},
            {"criterion": "language_use", "rationale": "Minor slips."},
        ],
    },
    Corrections: {
        "sentences": [
            {
                "original": "I go there yesterday.",
                "corrected": "I went there yesterday.",
                "reason": "Past time needs past tense.",
                "error_types": ["verb_tense"],
            }
        ]
    },
}


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[type[BaseModel], str]] = []

    def complete[T: BaseModel](self, *, system: str, user: str, schema: type[T]) -> LLMResult[T]:
        self.calls.append((schema, user))
        return LLMResult(
            parsed=schema.model_validate(CANNED[schema]),
            model="fake-model",
            usage=Usage(input_tokens=100, output_tokens=50, cost_usd=0.001),
            latency_ms=5,
        )


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


def make_auth(store: CredentialStore) -> ChatGPTAuth:
    return ChatGPTAuth(
        store,
        host_id="urn:uuid:test-host",
        redirect_uri="http://127.0.0.1:1455/auth/callback",
        agent_name="toefl-ai-tutor",
        http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
        signing_key=lambda token: None,
    )


def sign_in_as(client: TestClient, subject: str) -> int:
    """Creates a user with a session and sends its cookie from `client`. Returns the user ID."""
    token = secrets.token_urlsafe(32)
    with Session(client.app.state.engine) as db:
        user = User(provider="chatgpt", subject=subject, email=f"{subject}@example.com")
        db.add(user)
        db.flush()
        db.add(
            AuthSession(token_hash=hash_token(token), user_id=user.id, expires_at=time.time() + 60)
        )
        db.commit()
        user_id = user.id
    client.cookies.set(SESSION_COOKIE, token)
    return user_id


@pytest.fixture
def client(provider: FakeProvider, tmp_path) -> Iterator[TestClient]:
    app = create_app(
        f"sqlite:///{tmp_path / 'test.db'}", encryption_key=ENCRYPTION_KEY, make_auth=make_auth
    )
    app.dependency_overrides[get_provider] = lambda: provider
    with TestClient(
        app, base_url="http://127.0.0.1", headers={"content-type": "application/json"}
    ) as c:
        sign_in_as(c, "user-1")
        yield c
