from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, field_validator

EmailCriterion = Literal["task_completion", "organization", "language_use", "tone_and_register"]
EMAIL_CRITERIA: tuple[str, ...] = EmailCriterion.__args__


class ErrorType(StrEnum):
    VERB_TENSE = "verb_tense"
    SUBJECT_VERB_AGREEMENT = "subject_verb_agreement"
    ARTICLE = "article"
    PREPOSITION = "preposition"
    WORD_CHOICE = "word_choice"
    WORD_FORM = "word_form"
    PLURAL = "plural"
    SENTENCE_STRUCTURE = "sentence_structure"
    PUNCTUATION = "punctuation"
    SPELLING = "spelling"
    REGISTER = "register"
    OTHER = "other"


class CriterionRationale(BaseModel):
    criterion: EmailCriterion
    rationale: str


class Score(BaseModel):
    score: int
    criteria: list[CriterionRationale]

    @field_validator("score")
    @classmethod
    def in_range(cls, v: int) -> int:
        if not 0 <= v <= 5:
            raise ValueError("score must be between 0 and 5")
        return v

    @field_validator("criteria")
    @classmethod
    def covers_each_criterion_once(cls, v: list[CriterionRationale]) -> list[CriterionRationale]:
        if sorted(c.criterion for c in v) != sorted(EMAIL_CRITERIA):
            raise ValueError(f"criteria must cover each of {EMAIL_CRITERIA} exactly once")
        return v


class SentenceCorrection(BaseModel):
    original: str
    corrected: str
    reason: str
    error_types: list[ErrorType]


class Corrections(BaseModel):
    sentences: list[SentenceCorrection]
