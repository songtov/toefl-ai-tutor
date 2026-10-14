import random
from collections.abc import Collection, Sequence

from app.domain.task import BankedEmailTask

SET_SIZE = 3
PLAN_REASON = f"{SET_SIZE} Write an Email tasks from the task bank, unseen ones first."


def pick_email_tasks(
    bank: Sequence[BankedEmailTask], seen_ids: Collection[str], k: int = SET_SIZE
) -> list[BankedEmailTask]:
    """Picks `k` distinct tasks, preferring ones the learner has not seen yet."""
    unseen = [t for t in bank if t.id not in seen_ids]
    seen = [t for t in bank if t.id in seen_ids]
    if len(unseen) >= k:
        return random.sample(unseen, k)
    return random.sample(unseen, len(unseen)) + random.sample(seen, k - len(unseen))
