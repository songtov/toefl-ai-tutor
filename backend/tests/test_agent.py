import time

from app.application.agent import AgentLoop, Step, ToolRegistry


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("echo", lambda x: x)
    registry.register("slow", lambda: time.sleep(1))
    return registry


def test_runs_plan_in_order():
    run = AgentLoop(_registry(), max_steps=12, timeout_s=1).run(
        [Step("echo", {"x": 1}), Step("echo", {"x": 2})]
    )
    assert run.outputs == [1, 2]
    assert run.stopped is None


def test_stops_safely_at_max_steps():
    plan = [Step("echo", {"x": i}) for i in range(5)]
    run = AgentLoop(_registry(), max_steps=3, timeout_s=1).run(plan)
    assert run.outputs == [0, 1, 2]
    assert "max_steps" in run.stopped


def test_stops_on_timeout():
    run = AgentLoop(_registry(), max_steps=12, timeout_s=0.05).run(
        [Step("slow"), Step("echo", {"x": 1})]
    )
    assert run.outputs == []
    assert "timed out" in run.stopped
