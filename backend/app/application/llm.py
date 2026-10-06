from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    parsed: T
    model: str
    usage: Usage
    latency_ms: int


class LLMProvider(Protocol):
    def complete[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], temperature: float | None = None
    ) -> LLMResult[T]: ...
