from app.config import Settings, get_settings
from app.domain.task import EmailTask
from app.infrastructure.chatgpt_plan_provider import ChatGPTPlanProvider
from app.interfaces.api import get_provider


def test_demo_scenario(client, provider):
    created = client.post("/sessions")
    assert created.status_code == 201
    session = created.json()
    assert session["plan_reason"]
    assert len(session["task_ids"]) == 3

    task = client.get(f"/sessions/{session['id']}/next").json()
    assert task["type"] == "write_an_email"
    assert "Ms. Park" in task["directions"]
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


def test_session_list_and_detail(client):
    first = client.post("/sessions").json()
    second = client.post("/sessions").json()
    answered_id = second["task_ids"][0]
    client.post(f"/tasks/{answered_id}/answer", json={"text": "I go there yesterday."})

    listed = client.get("/sessions").json()
    assert [s["id"] for s in listed] == [second["id"], first["id"]]
    assert [(s["task_count"], s["answered_count"]) for s in listed] == [(3, 1), (3, 0)]

    detail = client.get(f"/sessions/{second['id']}").json()
    assert [t["id"] for t in detail["tasks"]] == second["task_ids"]
    done, pending = detail["tasks"][0], detail["tasks"][1]
    assert done["answer_text"] == "I go there yesterday."
    assert done["result"]["score"] == 3
    assert done["result"]["corrections"][0]["corrected"] == "I went there yesterday."
    assert pending["answer_text"] is None and pending["result"] is None

    assert client.get("/sessions/999").status_code == 404


def test_answer_twice_rejected(client):
    task_id = client.post("/sessions").json()["task_ids"][0]
    assert client.post(f"/tasks/{task_id}/answer", json={"text": "Hi."}).status_code == 200
    assert client.post(f"/tasks/{task_id}/answer", json={"text": "Hi."}).status_code == 409


def test_set_tasks_avoid_earlier_ones(client, provider):
    client.post("/sessions")
    generated = [(user, temp) for schema, user, temp in provider.calls if schema is EmailTask]
    assert len(generated) == 3
    assert "Ms. Park" not in generated[0][0]
    assert all("Ms. Park" in user for user, _ in generated[1:])
    assert {temp for _, temp in generated} == {get_settings().llm_task_temperature}


def test_unknown_session_and_task(client):
    assert client.get("/sessions/999/next").status_code == 404
    assert client.post("/tasks/999/answer", json={"text": "hi"}).status_code == 404


def test_empty_answer_rejected(client):
    session = client.post("/sessions").json()
    task_id = session["task_ids"][0]
    assert client.post(f"/tasks/{task_id}/answer", json={"text": "  "}).status_code == 422


def test_rejects_untrusted_host(client):
    assert client.get("/sessions", headers={"host": "evil.example"}).status_code == 400


def test_writes_require_json(client):
    form = {"content-type": "application/x-www-form-urlencoded"}
    assert client.post("/sessions", headers=form).status_code == 415
    assert client.post("/auth/logout", headers=form).status_code == 415


def test_auth_status_and_login(client):
    assert client.get("/auth/status").json() == {
        "signed_in": False,
        "email": None,
        "plan_enabled": False,
    }
    url = client.post("/auth/login").json()["authorize_url"]
    assert url.startswith("https://auth.openai.com/api/accounts/authorize?")


def test_callback_redirects_only_to_frontend(client):
    client.post("/auth/login")
    response = client.get(
        "/auth/callback",
        params={"state": "forged", "code": "c"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "http://127.0.0.1:3000/?auth=invalid_state"


def test_signed_out_provider_returns_401(client, auth):
    provider = ChatGPTPlanProvider(Settings(chatgpt_model="gpt-test"), auth)
    client.app.dependency_overrides[get_provider] = lambda: provider
    response = client.post("/sessions")
    assert response.status_code == 401
    assert response.json() == {"detail": "sign_in_required"}
