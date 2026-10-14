from app.application.llm import LLMProvider, LLMResult
from app.domain.assessment import Corrections, DiscussionScore, ErrorType, Score
from app.domain.rubric import DISCUSSION_RUBRIC, EMAIL_RUBRIC
from app.domain.task import AcademicDiscussionTask, EmailTask

SCORE_PROMPT_VERSION = "email-score-v1"
DISCUSSION_SCORE_PROMPT_VERSION = "discussion-score-v1"
CORRECT_PROMPT_VERSION = "email-correct-v1"


def score_response(provider: LLMProvider, *, task: EmailTask, text: str) -> LLMResult[Score]:
    return provider.complete(
        system=f"You are a strict, consistent TOEFL writing rater.\n\n{EMAIL_RUBRIC}",
        user=f"Task:\n{task.directions()}\n\nLearner's email:\n{text}",
        schema=Score,
    )


def score_discussion(
    provider: LLMProvider, *, task: AcademicDiscussionTask, text: str
) -> LLMResult[DiscussionScore]:
    return provider.complete(
        system=f"You are a strict, consistent TOEFL writing rater.\n\n{DISCUSSION_RUBRIC}",
        user=f"Task:\n{task.directions()}\n\nLearner's post:\n{text}",
        schema=DiscussionScore,
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
