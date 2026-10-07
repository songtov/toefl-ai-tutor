from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.application.llm import LLMResult, Usage
from app.domain.assessment import Corrections, Score
from app.domain.task import EmailTask
from app.infrastructure.chatgpt_auth import ChatGPTAuth, CredentialStore
from app.interfaces.api import get_provider
from app.main import create_app

CANNED: dict[type[BaseModel], dict] = {
    EmailTask: {
        "situation": "Your study group meeting was moved to a room you cannot find.",
        "recipient": "Ms. Park, the library coordinator",
        "requirements": [
            "Explain the problem",
            "Ask where the room is",
            "Suggest how signs could help",
        ],
    },
    Score: {
        "score": 3,
        "criteria": [
            {"criterion": "task_completion", "rationale": "Two of three covered."},
            {"criterion": "organization", "rationale": "Mostly logical."},
            {"criterion": "language_use", "rationale": "Some tense errors."},
            {"criterion": "tone_and_register", "rationale": "Polite."},
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
        self.calls: list[tuple[type[BaseModel], str, float | None]] = []

    def complete[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], temperature: float | None = None
    ) -> LLMResult[T]:
        self.calls.append((schema, user, temperature))
        return LLMResult(
            parsed=schema.model_validate(CANNED[schema]),
            model="fake-model",
            usage=Usage(input_tokens=100, output_tokens=50, cost_usd=0.001),
            latency_ms=5,
        )


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def auth(tmp_path) -> ChatGPTAuth:
    return ChatGPTAuth(
        CredentialStore(tmp_path / "auth"),
        redirect_uri="http://127.0.0.1:1455/auth/callback",
        agent_name="toefl-ai-tutor",
        http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
        signing_key=lambda token: None,
    )


@pytest.fixture
def client(provider: FakeProvider, auth: ChatGPTAuth, tmp_path) -> Iterator[TestClient]:
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}", auth=auth)
    app.dependency_overrides[get_provider] = lambda: provider
    with TestClient(
        app, base_url="http://127.0.0.1", headers={"content-type": "application/json"}
    ) as c:
        yield c
