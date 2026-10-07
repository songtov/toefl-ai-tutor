import time

import httpx
from openai import APIConnectionError, APIStatusError, OpenAI
from pydantic import BaseModel

from app.application.llm import LLMResult, Usage
from app.config import Settings
from app.infrastructure.chatgpt_auth import RESOURCE, ChatGPTAuth

USAGE_LIMIT_CODE = "subscription_sharing_usage_limit_exceeded"


class PlanRequestError(Exception):
    def __init__(self, status_code: int, code: str, request_id: str | None = None) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.request_id = request_id


class ChatGPTPlanProvider:
    """Responses API on the signed-in user's ChatGPT plan (Sign in with ChatGPT)."""

    def __init__(
        self, settings: Settings, auth: ChatGPTAuth, http_client: httpx.Client | None = None
    ) -> None:
        if not settings.chatgpt_model:
            raise RuntimeError("CHATGPT_MODEL must be set in backend/.env")
        self._settings = settings
        self._auth = auth
        self._http_client = http_client

    def complete[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], temperature: float | None = None
    ) -> LLMResult[T]:
        # ChatGPT plan usage rejects `temperature`, so it is ignored.
        s = self._settings
        client = OpenAI(
            api_key=self._auth.access_token(),
            base_url=RESOURCE,
            max_retries=0,
            timeout=s.llm_timeout_s,
            http_client=self._http_client,
        )
        start = time.perf_counter()
        try:
            with client.responses.stream(
                model=s.chatgpt_model,
                instructions=system,
                input=[{"role": "user", "content": user}],
                text_format=schema,
                store=False,
            ) as stream:
                for event in stream:
                    if event.type in ("response.failed", "response.incomplete"):
                        error = event.response.error
                        raise PlanRequestError(
                            429 if error and error.code == USAGE_LIMIT_CODE else 502,
                            error.code if error else event.type.replace(".", "_"),
                        )
                response = stream.get_final_response()
        except APIStatusError as e:
            status = e.status_code if e.status_code in (401, 403, 429) else 502
            code = str(e.code or f"http_{e.status_code}")
            raise PlanRequestError(status, code, e.request_id) from e
        except APIConnectionError as e:
            raise PlanRequestError(502, "responses_unreachable") from e
        latency_ms = int((time.perf_counter() - start) * 1000)
        if response.output_parsed is None:
            raise RuntimeError(f"model returned no parsable output for {schema.__name__}")
        usage = response.usage
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0
        return LLMResult(
            parsed=response.output_parsed,
            model=response.model,
            usage=Usage(input_tokens, output_tokens, 0.0),
            latency_ms=latency_ms,
        )
