from functools import cache
from pathlib import Path

from app.domain.task import BankedEmailTask

CONTENT_DIR = Path(__file__).resolve().parents[1] / "content"


@cache
def load_email_tasks() -> tuple[BankedEmailTask, ...]:
    lines = (CONTENT_DIR / "email_tasks.jsonl").read_text().splitlines()
    tasks = tuple(BankedEmailTask.model_validate_json(line) for line in lines if line.strip())
    if len({t.id for t in tasks}) != len(tasks):
        raise ValueError("email task bank has duplicate ids")
    return tasks
