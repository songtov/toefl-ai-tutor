from functools import cache
from pathlib import Path

from app.domain.task import BankedEmailTask, EmailSet

CONTENT_DIR = Path(__file__).resolve().parents[1] / "content"


def _lines(name: str) -> list[str]:
    return [line for line in (CONTENT_DIR / name).read_text().splitlines() if line.strip()]


@cache
def load_email_tasks() -> dict[str, BankedEmailTask]:
    tasks = [BankedEmailTask.model_validate_json(line) for line in _lines("email_tasks.jsonl")]
    by_id = {t.id: t for t in tasks}
    if len(by_id) != len(tasks):
        raise ValueError("email task bank has duplicate ids")
    return by_id


@cache
def load_email_sets() -> dict[int, EmailSet]:
    sets = [EmailSet.model_validate_json(line) for line in _lines("email_sets.jsonl")]
    task_ids = [i for s in sets for i in s.task_ids]
    if len({s.id for s in sets}) != len(sets):
        raise ValueError("email sets have duplicate ids")
    if len(task_ids) != len(set(task_ids)) or set(task_ids) != load_email_tasks().keys():
        raise ValueError("email sets must use every bank task exactly once")
    return {s.id: s for s in sets}
