import json

import httpx
import pytest

from app.config import Settings
from app.domain.assessment import Score
from app.infrastructure.chatgpt_plan_provider import ChatGPTPlanProvider, PlanRequestError
from tests.conftest import CANNED


class FakeAuth:
    def access_token(self) -> str:
        return "access-token"


def _response(status: str, text: str = "", error: dict | None = None) -> dict:
    output = [
        {
            "type": "message",
            "id": "msg_1",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }
    ]
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "model": "gpt-test",
        "status": status,
        "error": error,
        "output": output if text else [],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "usage": {
            "input_tokens": 12,
            "output_tokens": 34,
            "total_tokens": 46,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


def _sse(*events: dict) -> bytes:
    return b"".join(
        f"event: {e['type']}\ndata: {json.dumps({**e, 'sequence_number': i})}\n\n".encode()
        for i, e in enumerate(events)
    )


def _provider(handler) -> tuple[ChatGPTPlanProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    provider = ChatGPTPlanProvider(
        Settings(chatgpt_model="gpt-test"),
        FakeAuth(),
        http_client=httpx.Client(transport=httpx.MockTransport(record)),
    )
    return provider, seen


def test_streams_structured_output_without_storing():
    text = json.dumps(CANNED[Score])
    message = {"type": "message", "id": "msg_1", "role": "assistant", "status": "in_progress"}
    part = {"type": "output_text", "text": "", "annotations": []}
    where = {"item_id": "msg_1", "output_index": 0, "content_index": 0}
    # Mirrors the ChatGPT plan stream: text arrives in deltas; response.completed has no output.
    body = _sse(
        {"type": "response.created", "response": _response("in_progress")},
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {**message, "content": []},
        },
        {"type": "response.content_part.added", **where, "part": part},
        {"type": "response.output_text.delta", **where, "delta": text, "logprobs": []},
        {"type": "response.output_text.done", **where, "text": text, "logprobs": []},
        {"type": "response.completed", "response": _response("completed")},
    )
    provider, seen = _provider(
        lambda r: httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})
    )
    result = provider.complete(system="rate", user="essay", schema=Score, temperature=0.9)

    assert result.parsed.score == 3
    assert (result.usage.input_tokens, result.usage.output_tokens) == (12, 34)
    request = seen[0]
    assert str(request.url) == "https://api.openai.com/v1/responses"
    assert request.headers["authorization"] == "Bearer access-token"
    sent = json.loads(request.content)
    assert sent["store"] is False and sent["stream"] is True
    assert sent["instructions"] == "rate"
    assert sent["input"] == [{"role": "user", "content": "essay"}]
    assert sent["text"]["format"]["type"] == "json_schema"
    assert "temperature" not in sent


def test_failed_stream_maps_usage_limit():
    error = {"code": "subscription_sharing_usage_limit_exceeded", "message": "limit"}
    body = _sse(
        {"type": "response.created", "response": _response("in_progress")},
        {"type": "response.failed", "response": _response("failed", error=error)},
    )
    provider, _ = _provider(
        lambda r: httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})
    )
    with pytest.raises(PlanRequestError) as e:
        provider.complete(system="s", user="u", schema=Score)
    assert (e.value.status_code, e.value.code) == (429, error["code"])


@pytest.mark.parametrize(
    "status, body, expected",
    [
        (429, {"error": {"code": "subscription_sharing_usage_limit_exceeded"}}, 429),
        (401, {"detail": "not accepted"}, 401),
        (400, {"error": {"code": "subscription_sharing_unsupported_capability"}}, 502),
    ],
)
def test_admission_errors_mapped(status, body, expected):
    provider, _ = _provider(lambda r: httpx.Response(status, json=body))
    with pytest.raises(PlanRequestError) as e:
        provider.complete(system="s", user="u", schema=Score)
    assert e.value.status_code == expected


def test_requires_model():
    with pytest.raises(RuntimeError, match="CHATGPT_MODEL"):
        ChatGPTPlanProvider(Settings(chatgpt_model=""), FakeAuth())
