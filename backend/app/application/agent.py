from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any

from app.domain.task import TaskType


@dataclass(frozen=True)
class Step:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRun:
    outputs: list[Any]
    stopped: str | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, fn: Callable[..., Any]) -> None:
        self._tools[name] = fn

    def get(self, name: str) -> Callable[..., Any]:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]


class AgentLoop:
    def __init__(self, registry: ToolRegistry, *, max_steps: int, timeout_s: float) -> None:
        self.registry = registry
        self.max_steps = max_steps
        self.timeout_s = timeout_s

    def run(self, plan: list[Step]) -> AgentRun:
        run = AgentRun(outputs=[])
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            for i, step in enumerate(plan):
                if i >= self.max_steps:
                    run.stopped = f"max_steps ({self.max_steps}) reached"
                    break
                future = executor.submit(self.registry.get(step.tool), **step.args)
                try:
                    run.outputs.append(future.result(timeout=self.timeout_s))
                except FutureTimeout:
                    run.stopped = f"{step.tool} timed out after {self.timeout_s}s"
                    break
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        return run


SET_SIZE = 3
FIXED_PLAN_REASON = f"Sprint 1 fixed plan: {SET_SIZE} Write an Email tasks at medium difficulty."


def fixed_session_plan() -> list[Step]:
    return [
        Step(
            "generate_task",
            {"task_type": TaskType.EMAIL, "difficulty": "medium", "target_weakness": None},
        )
        for _ in range(SET_SIZE)
    ]
