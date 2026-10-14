import pytest
from pydantic import ValidationError

from app.domain.assessment import Score
from app.domain.task import AcademicDiscussionTask, BuildSentenceTask, EmailTask, Post

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


def test_build_sentence_needs_one_chunk_per_blank():
    with pytest.raises(ValidationError):
        BuildSentenceTask(context="c", template="I _ _ it.", answer=["like"], distractors=[])


def test_build_sentence_accepts_only_offered_chunks():
    task = BuildSentenceTask(
        context="c", template="I _ _ it.", answer=["really", "like"], distractors=["likes"]
    )
    assert task.sentence(["really", "like"]) == "I really like it."
    assert task.fits(["really", "likes"])
    assert not task.fits(["really", "really"])
    assert not task.fits(["really"])


def test_academic_discussion_requires_two_students():
    post = Post(name="n", post="p")
    with pytest.raises(ValidationError):
        AcademicDiscussionTask(course="c", professor=post, students=[post])
