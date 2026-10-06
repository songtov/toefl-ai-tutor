import time

from openai import OpenAI
from pydantic import BaseModel

from app.application.llm import LLMResult, Usage
from app.config import Settings


class OpenAIAPIProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key or not settings.openai_model:
            raise RuntimeError("OPENAI_API_KEY and OPENAI_MODEL must be set in backend/.env")
        self._client = OpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_s)
        self._settings = settings

    def complete[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], temperature: float | None = None
    ) -> LLMResult[T]:
        s = self._settings
        if s.llm_temperature is None:
            extra = {}
        else:
            extra = {"temperature": s.llm_temperature if temperature is None else temperature}
        start = time.perf_counter()
        response = self._client.responses.parse(
            model=s.openai_model,
            instructions=system,
            input=user,
            text_format=schema,
            **extra,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        if response.output_parsed is None:
            raise RuntimeError(f"model returned no parsable output for {schema.__name__}")
        usage = response.usage
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0
        cost = (
            input_tokens * s.price_input_per_mtok + output_tokens * s.price_output_per_mtok
        ) / 1_000_000
        return LLMResult(
            parsed=response.output_parsed,
            model=response.model,
            usage=Usage(input_tokens, output_tokens, cost),
            latency_ms=latency_ms,
        )
