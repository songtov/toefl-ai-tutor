from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.config import Settings
from app.infrastructure.chatgpt_auth import ChatGPTAuth
from app.infrastructure.chatgpt_plan_provider import ChatGPTPlanProvider
from app.infrastructure.db import Task, User
from app.infrastructure.task_bank import load_email_sets, load_email_tasks
from app.interfaces.api import get_provider
from app.main import create_app
from tests.conftest import ENCRYPTION_KEY, sign_in_as
from tests.test_chatgpt_auth import CLIENT_ID, KEY, FakeOpenAI


def test_demo_scenario(client, provider):
    created = client.post("/sets/1/session")
    assert created.status_code == 200
    session = created.json()
    assert session["plan_reason"]
    assert len(session["task_ids"]) == 3

    task = client.get(f"/sessions/{session['id']}/next").json()
    assert task["type"] == "write_an_email"
    first_id = load_email_sets()[1].task_ids[0]
    assert task["content"] == load_email_tasks()[first_id].task.model_dump()
    assert len(task["content"]["requirements"]) == 3

    answered = client.post(f"/tasks/{task['id']}/answer", json={"text": "I go there yesterday."})
    assert answered.status_code == 200
    body = answered.json()
    assert body["score"] == 3
    assert {c["criterion"] for c in body["criteria"]} == {
        "task_completion",
        "organization",
        "language_use",
        "tone_and_register",
    }
    assert body["corrections"][0]["error_types"] == ["verb_tense"]
    assert body["usage"] == {"input_tokens": 200, "output_tokens": 100, "cost_usd": 0.002}

    for task_id in session["task_ids"][1:]:
        client.post(f"/tasks/{task_id}/answer", json={"text": "Hello."})
    assert client.get(f"/sessions/{session['id']}/next").status_code == 404


def test_set_list_and_detail(client):
    sets = load_email_sets()
    listed = client.get("/sets").json()
    assert [s["id"] for s in listed] == list(sets)
    assert all(s["session_id"] is None and s["answered_count"] == 0 for s in listed)

    session = client.post("/sets/2/session").json()
    client.post(f"/tasks/{session['task_ids'][0]}/answer", json={"text": "I go there yesterday."})

    listed = {s["id"]: s for s in client.get("/sets").json()}
    assert listed[2] == {"id": 2, "task_count": 3, "session_id": session["id"], "answered_count": 1}
    assert listed[1]["session_id"] is None

    detail = client.get(f"/sessions/{session['id']}").json()
    assert [t["id"] for t in detail["tasks"]] == session["task_ids"]
    done, pending = detail["tasks"][0], detail["tasks"][1]
    assert done["answer_text"] == "I go there yesterday."
    assert done["result"]["score"] == 3
    assert done["result"]["corrections"][0]["corrected"] == "I went there yesterday."
    assert pending["answer_text"] is None and pending["result"] is None

    assert client.get("/sessions/999").status_code == 404


def test_answer_twice_rejected(client):
    task_id = client.post("/sets/1/session").json()["task_ids"][0]
    assert client.post(f"/tasks/{task_id}/answer", json={"text": "Hi."}).status_code == 200
    assert client.post(f"/tasks/{task_id}/answer", json={"text": "Hi."}).status_code == 409


def test_opening_a_set_reuses_its_session_without_llm(client, provider):
    first = client.post("/sets/3/session").json()
    again = client.post("/sets/3/session").json()
    assert again == first
    assert provider.calls == []

    with Session(client.app.state.engine) as db:
        bank_ids = db.exec(select(Task.bank_id).order_by(col(Task.id))).all()
    assert bank_ids == load_email_sets()[3].task_ids

    assert client.post("/sets/999/session").status_code == 404


def test_unknown_session_and_task(client):
    assert client.get("/sessions/999/next").status_code == 404
    assert client.post("/tasks/999/answer", json={"text": "hi"}).status_code == 404


def test_empty_answer_rejected(client):
    session = client.post("/sets/1/session").json()
    task_id = session["task_ids"][0]
    assert client.post(f"/tasks/{task_id}/answer", json={"text": "  "}).status_code == 422


def test_rejects_untrusted_host(client):
    assert client.get("/sets", headers={"host": "evil.example"}).status_code == 400


def test_writes_require_json(client):
    form = {"content-type": "application/x-www-form-urlencoded"}
    assert client.post("/sets/1/session", headers=form).status_code == 415
    assert client.post("/auth/logout", headers=form).status_code == 415


def test_auth_status_and_login(client):
    assert client.get("/auth/status").json() == {
        "signed_in": True,
        "email": "user-1@example.com",
        "plan_enabled": False,
    }
    url = client.post("/auth/login").json()["authorize_url"]
    assert url.startswith("https://auth.openai.com/api/accounts/authorize?")

    client.cookies.clear()
    assert client.get("/auth/status").json() == {
        "signed_in": False,
        "email": None,
        "plan_enabled": False,
    }


def test_callback_redirects_only_to_frontend(client):
    client.post("/auth/login")
    response = client.get(
        "/auth/callback",
        params={"state": "forged", "code": "c"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "http://127.0.0.1:3000/?auth=invalid_state"


def test_signed_out_provider_returns_401(client):
    auth = client.app.state.auth
    provider = ChatGPTPlanProvider(Settings(chatgpt_model="gpt-test"), lambda: auth.access_token(1))
    client.app.dependency_overrides[get_provider] = lambda: provider
    task_id = client.post("/sets/1/session").json()["task_ids"][0]
    response = client.post(f"/tasks/{task_id}/answer", json={"text": "Hi."})
    assert response.status_code == 401
    assert response.json() == {"detail": "sign_in_required"}


def test_requests_without_session_return_401(client):
    task_id = client.post("/sets/1/session").json()["task_ids"][0]
    client.cookies.clear()
    for method, path in [
        ("GET", "/sets"),
        ("POST", "/sets/1/session"),
        ("GET", "/sessions/1"),
        ("GET", "/sessions/1/next"),
        ("POST", f"/tasks/{task_id}/answer"),
        ("POST", "/auth/logout"),
    ]:
        response = client.request(method, path, json={"text": "Hi."})
        assert response.status_code == 401, path
        assert response.json() == {"detail": "sign_in_required"}


def test_users_cannot_see_each_others_data(client):
    session = client.post("/sets/1/session").json()
    task_id = session["task_ids"][0]

    sign_in_as(client, "user-2")
    assert all(s["session_id"] is None for s in client.get("/sets").json())
    assert client.get(f"/sessions/{session['id']}").status_code == 404
    assert client.get(f"/sessions/{session['id']}/next").status_code == 404
    assert client.post(f"/tasks/{task_id}/answer", json={"text": "Hi."}).status_code == 404


@pytest.fixture
def server() -> FakeOpenAI:
    return FakeOpenAI()


@pytest.fixture
def oauth_client(server, tmp_path):
    def make_auth(store):
        return ChatGPTAuth(
            store,
            host_id="urn:uuid:test-host",
            redirect_uri="http://127.0.0.1:1455/auth/callback",
            agent_name="toefl-ai-tutor",
            http=httpx.Client(transport=httpx.MockTransport(server.handle)),
            signing_key=lambda token: KEY.public_key(),
        )

    app = create_app(
        f"sqlite:///{tmp_path / 'test.db'}", encryption_key=ENCRYPTION_KEY, make_auth=make_auth
    )
    with TestClient(
        app, base_url="http://127.0.0.1", headers={"content-type": "application/json"}
    ) as c:
        yield c


def _sign_in_with_chatgpt(client: TestClient, server: FakeOpenAI) -> dict[str, str]:
    url = client.post("/auth/login").json()["authorize_url"]
    params = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    server.nonce = params["nonce"]
    response = client.get(
        "/auth/callback",
        params={"code": "c", "state": params["state"], "client_id": CLIENT_ID},
        follow_redirects=False,
    )
    assert response.headers["location"] == "http://127.0.0.1:3000/?auth=ok"
    return params


def test_chatgpt_sign_in_creates_account_and_session(oauth_client, server):
    params = _sign_in_with_chatgpt(oauth_client, server)
    assert params["client_id"] == "dynamic_agent_client"
    assert oauth_client.get("/auth/status").json() == {
        "signed_in": True,
        "email": "me@example.com",
        "plan_enabled": True,
    }
    assert oauth_client.get("/sets").status_code == 200

    assert oauth_client.post("/auth/logout").json() == {"revoked": True}
    assert oauth_client.get("/sets").status_code == 401

    # The same browser signs in again with the saved registration and gets the same account.
    params = _sign_in_with_chatgpt(oauth_client, server)
    assert params["client_id"] == CLIENT_ID
    assert params["login_hint"] == "me@example.com"
    with Session(oauth_client.app.state.engine) as db:
        users = db.exec(select(User)).all()
    assert [(u.provider, u.subject, u.email) for u in users] == [
        ("chatgpt", "user-1", "me@example.com")
    ]


def test_callback_requires_the_browser_that_started_login(oauth_client, server):
    url = oauth_client.post("/auth/login").json()["authorize_url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    oauth_client.cookies.clear()
    response = oauth_client.get(
        "/auth/callback",
        params={"code": "c", "state": state, "client_id": CLIENT_ID},
        follow_redirects=False,
    )
    assert response.headers["location"] == "http://127.0.0.1:3000/?auth=invalid_state"
    assert server.requests == []
