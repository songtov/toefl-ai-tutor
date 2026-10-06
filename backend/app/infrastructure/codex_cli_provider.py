import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel

from app.application.llm import LLMResult, Usage
from app.config import Settings


class CodexCLIProvider:
    """Calls the official Codex CLI, which authenticates with the user's ChatGPT login."""

    def __init__(self, settings: Settings) -> None:
        if shutil.which(settings.codex_bin) is None:
            raise RuntimeError(f"Codex CLI not found: {settings.codex_bin} (run `codex login`)")
        self._settings = settings

    def complete[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], temperature: float | None = None
    ) -> LLMResult[T]:
        # Codex CLI exposes no temperature setting, so `temperature` is ignored.
        s = self._settings
        with tempfile.TemporaryDirectory() as workdir:
            schema_path = Path(workdir) / "schema.json"
            schema_path.write_text(json.dumps(to_strict_json_schema(schema)))
            cmd = [
                s.codex_bin, "exec", "--json", "--ephemeral", "--skip-git-repo-check",
                "--ignore-user-config", "--ignore-rules", "--sandbox", "read-only",
                "--cd", workdir, "--output-schema", str(schema_path),
            ]  # fmt: skip
            if s.codex_model:
                cmd += ["--model", s.codex_model]
            prompt = f"<instructions>\n{system}\n</instructions>\n\n<input>\n{user}\n</input>"
            start = time.perf_counter()
            proc = subprocess.run(
                [*cmd, "-"], input=prompt, capture_output=True, text=True, timeout=s.llm_timeout_s
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
        if proc.returncode != 0:
            raise RuntimeError(f"codex exec failed: {proc.stderr.strip()[-500:]}")

        message, usage = None, {}
        for line in proc.stdout.splitlines():
            event = json.loads(line)
            if event.get("type") == "item.completed" and event["item"]["type"] == "agent_message":
                message = event["item"]["text"]
            elif event.get("type") == "turn.completed":
                usage = event["usage"]
        if message is None:
            raise RuntimeError(f"codex returned no message for {schema.__name__}")
        return LLMResult(
            parsed=schema.model_validate_json(message),
            model=f"codex:{s.codex_model or 'default'}",
            usage=Usage(usage.get("input_tokens", 0), usage.get("output_tokens", 0), 0.0),
            latency_ms=latency_ms,
        )
