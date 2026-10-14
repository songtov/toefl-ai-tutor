import json
from functools import cache
from pathlib import Path

from app.domain.task import CONTENT_MODELS, SET_LAYOUT, BankTask, TaskSet, TaskType

CONTENT_DIR = Path(__file__).resolve().parents[1] / "content"
BANK_FILES = {
    TaskType.BUILD_SENTENCE: "build_sentence_tasks.jsonl",
    TaskType.EMAIL: "email_tasks.jsonl",
    TaskType.ACADEMIC_DISCUSSION: "academic_discussion_tasks.jsonl",
}


def _lines(name: str) -> list[str]:
    return [line for line in (CONTENT_DIR / name).read_text().splitlines() if line.strip()]


@cache
def load_bank() -> dict[str, BankTask]:
    tasks = []
    for task_type, name in BANK_FILES.items():
        for line in _lines(name):
            row = json.loads(line)
            tasks.append(
                BankTask(
                    id=row.pop("id"),
                    type=task_type,
                    difficulty=row.pop("difficulty"),
                    content=CONTENT_MODELS[task_type].model_validate(row),
                )
            )
    by_id = {t.id: t for t in tasks}
    if len(by_id) != len(tasks):
        raise ValueError("task bank has duplicate ids")
    return by_id


@cache
def load_sets() -> dict[int, TaskSet]:
    sets = [TaskSet.model_validate_json(line) for line in _lines("sets.jsonl")]
    bank = load_bank()
    task_ids = [i for s in sets for i in s.task_ids]
    if len({s.id for s in sets}) != len(sets):
        raise ValueError("sets have duplicate ids")
    if len(task_ids) != len(set(task_ids)) or not set(task_ids) <= bank.keys():
        raise ValueError("sets must use existing bank tasks, each at most once")
    for s in sets:
        if tuple(bank[i].type for i in s.task_ids) != SET_LAYOUT:
            raise ValueError(f"set {s.id} does not follow the Writing section layout")
    return {s.id: s for s in sets}
