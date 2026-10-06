import json
import stat

import pytest

from app.config import Settings
from app.domain.task import EmailTask
from app.infrastructure.codex_cli_provider import CodexCLIProvider

TASK = {"situation": "s", "recipient": "r", "requirements": ["a", "b", "c"]}


def _fake_codex(tmp_path, stdout: str, exit_code: int = 0) -> str:
    out = tmp_path / "out.jsonl"
    out.write_text(stdout)
    script = tmp_path / "codex"
    script.write_text(f"#!/bin/sh\ncat > /dev/null\ncat {out}\nexit {exit_code}\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def _events(*events: dict) -> str:
    return "\n".join(json.dumps(e) for e in events) + "\n"


def test_parses_message_and_usage(tmp_path):
    stdout = _events(
        {"type": "thread.started", "thread_id": "t"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(TASK)}},
        {"type": "turn.completed", "usage": {"input_tokens": 120, "output_tokens": 30}},
    )
    provider = CodexCLIProvider(Settings(_env_file=None, codex_bin=_fake_codex(tmp_path, stdout)))
    result = provider.complete(system="sys", user="u", schema=EmailTask)
    assert result.parsed == EmailTask(**TASK)
    assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 30)
    assert result.usage.cost_usd == 0.0


def test_invalid_output_fails_schema_validation(tmp_path):
    bad = {**TASK, "requirements": ["only one"]}
    stdout = _events(
        {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(bad)}},
    )
    provider = CodexCLIProvider(Settings(_env_file=None, codex_bin=_fake_codex(tmp_path, stdout)))
    with pytest.raises(ValueError):
        provider.complete(system="sys", user="u", schema=EmailTask)


def test_nonzero_exit_raises(tmp_path):
    codex = _fake_codex(tmp_path, "", exit_code=1)
    provider = CodexCLIProvider(Settings(_env_file=None, codex_bin=codex))
    with pytest.raises(RuntimeError, match="codex exec failed"):
        provider.complete(system="sys", user="u", schema=EmailTask)


def test_missing_binary_raises():
    with pytest.raises(RuntimeError, match="not found"):
        CodexCLIProvider(Settings(_env_file=None, codex_bin="/nonexistent/codex"))
