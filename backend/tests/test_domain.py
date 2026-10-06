import pytest
from pydantic import ValidationError

from app.domain.assessment import Score
from app.domain.task import EmailTask

CRITERIA = [
    {"criterion": c, "rationale": "r"}
    for c in ("task_completion", "organization", "language_use", "tone_and_register")
]


def test_email_task_requires_three_requirements():
    with pytest.raises(ValidationError):
        EmailTask(situation="s", recipient="r", requirements=["a", "b"])


@pytest.mark.parametrize("score", [-1, 6])
def test_score_out_of_range_rejected(score):
    with pytest.raises(ValidationError):
        Score(score=score, criteria=CRITERIA)


def test_score_must_cover_every_criterion_once():
    with pytest.raises(ValidationError):
        Score(score=3, criteria=CRITERIA[:3] + CRITERIA[:1])
