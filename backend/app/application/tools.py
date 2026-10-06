from collections.abc import Sequence

from app.application.llm import LLMProvider, LLMResult
from app.domain.assessment import Corrections, ErrorType, Score
from app.domain.rubric import EMAIL_RUBRIC
from app.domain.task import EmailTask, TaskType

GENERATE_TASK_PROMPT_VERSION = "email-generate-v2"
SCORE_PROMPT_VERSION = "email-score-v1"
CORRECT_PROMPT_VERSION = "email-correct-v1"


def generate_task(
    provider: LLMProvider,
    *,
    task_type: TaskType,
    difficulty: str,
    target_weakness: str | None,
    avoid: Sequence[EmailTask] = (),
    temperature: float | None = None,
) -> LLMResult[EmailTask]:
    if task_type is not TaskType.EMAIL:
        raise ValueError(f"unsupported task type: {task_type}")
    focus = f" Give the learner chances to practice: {target_weakness}." if target_weakness else ""
    if avoid:
        taken = "\n".join(f"- To {t.recipient}: {t.situation}" for t in avoid)
        focus += (
            "\n\nThese tasks are already in the set. Write a clearly different one: a different "
            f"setting, purpose, and recipient (new first and last name, new role):\n{taken}"
        )
    return provider.complete(
        system=(
            "You write original practice prompts in the style of the TOEFL 'Write an Email' task. "
            "Never reuse official ETS items. The situation is 2-3 sentences from everyday campus, "
            "work, or community life. The recipient is a specific person with a name and role. "
            "Give exactly three requirements, each a short imperative (e.g. 'Explain why ...')."
        ),
        user=f"Difficulty: {difficulty}.{focus}",
        schema=EmailTask,
        temperature=temperature,
    )


def score_response(provider: LLMProvider, *, task: EmailTask, text: str) -> LLMResult[Score]:
    return provider.complete(
        system=f"You are a strict, consistent TOEFL writing rater.\n\n{EMAIL_RUBRIC}",
        user=f"Task:\n{task.directions()}\n\nLearner's email:\n{text}",
        schema=Score,
    )


def correct_errors(provider: LLMProvider, *, text: str) -> LLMResult[Corrections]:
    tags = ", ".join(e.value for e in ErrorType)
    return provider.complete(
        system=(
            "You are an English writing coach. List only the sentences that contain errors. "
            "For each, give the original sentence verbatim, a minimally edited correction, a "
            f"one-sentence reason, and one or more error types from: {tags}."
        ),
        user=text,
        schema=Corrections,
    )
