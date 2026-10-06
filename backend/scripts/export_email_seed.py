"""Export the latest answered Email tasks to evals/email_seed.jsonl for later human labeling."""

import json
import sys
from pathlib import Path

from sqlmodel import Session, col, select

from app.config import get_settings
from app.infrastructure.db import Response, Result, Task, make_engine

OUT = Path(__file__).resolve().parents[1] / "evals" / "email_seed.jsonl"


def main(limit: int) -> None:
    engine = make_engine(get_settings().database_url)
    with Session(engine) as db:
        rows = db.exec(
            select(Task, Response, Result)
            .where(Task.id == Response.task_id, Response.id == Result.response_id)
            .order_by(col(Result.id).desc())
            .limit(limit)
        ).all()
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w") as f:
        for task, response, result in reversed(rows):
            case = {
                "task": task.content,
                "answer": response.text,
                "model_score": result.score,
                "model_rubric": result.rubric,
                "model_corrections": result.corrections,
                "model": result.model,
                "prompt_version": result.prompt_version,
                "human_score": None,
            }
            f.write(json.dumps(case, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} cases to {OUT}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
