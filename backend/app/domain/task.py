from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, field_validator, model_validator

BLANK = "_"


class TaskType(StrEnum):
    BUILD_SENTENCE = "build_a_sentence"
    EMAIL = "write_an_email"
    ACADEMIC_DISCUSSION = "academic_discussion"


class EmailTask(BaseModel):
    situation: str
    recipient: str
    requirements: list[str]

    @field_validator("requirements")
    @classmethod
    def exactly_three(cls, v: list[str]) -> list[str]:
        if len(v) != 3:
            raise ValueError("an email task needs exactly 3 requirements")
        return v

    def directions(self) -> str:
        items = "\n".join(f"- {r}" for r in self.requirements)
        return (
            f"{self.situation}\n\n"
            f"Write an email to {self.recipient}. In your email, do the following:\n{items}\n\n"
            "Write 80-120 words in complete sentences."
        )


class BuildSentenceTask(BaseModel):
    context: str
    template: str
    answer: list[str]
    distractors: list[str]

    @model_validator(mode="after")
    def one_chunk_per_blank(self) -> "BuildSentenceTask":
        if self.template.split().count(BLANK) != len(self.answer):
            raise ValueError("the template needs one blank per answer chunk")
        return self

    def chunks(self) -> list[str]:
        return self.answer + self.distractors

    def fits(self, chunks: Sequence[str]) -> bool:
        """True if `chunks` fills every blank using only the offered chunks."""
        return len(chunks) == len(self.answer) and not Counter(chunks) - Counter(self.chunks())

    def sentence(self, chunks: Sequence[str]) -> str:
        filled = iter(chunks)
        return " ".join(next(filled) if w == BLANK else w for w in self.template.split())

    def directions(self) -> str:
        return f"Make an appropriate sentence.\n\n{self.context}\n{self.template}"


class Post(BaseModel):
    name: str
    post: str


class AcademicDiscussionTask(BaseModel):
    course: str
    professor: Post
    students: list[Post]

    @field_validator("students")
    @classmethod
    def exactly_two(cls, v: list[Post]) -> list[Post]:
        if len(v) != 2:
            raise ValueError("an academic discussion task needs exactly 2 student posts")
        return v

    def directions(self) -> str:
        posts = "\n\n".join(f"{p.name}: {p.post}" for p in [self.professor, *self.students])
        return (
            f"Your professor is teaching a class on {self.course}. "
            "Write a post responding to the professor's question.\n\n"
            "In your response, you should do the following:\n"
            "- Express and support your opinion.\n"
            "- Make a contribution to the discussion in your own words.\n\n"
            "An effective response will contain at least 100 words.\n\n"
            f"{posts}"
        )


TaskContent = EmailTask | BuildSentenceTask | AcademicDiscussionTask

CONTENT_MODELS: dict[TaskType, type[TaskContent]] = {
    TaskType.BUILD_SENTENCE: BuildSentenceTask,
    TaskType.EMAIL: EmailTask,
    TaskType.ACADEMIC_DISCUSSION: AcademicDiscussionTask,
}

# Mirrors the TOEFL iBT Writing section: 10 Build a Sentence items, then one of each writing task.
SET_LAYOUT: tuple[TaskType, ...] = (TaskType.BUILD_SENTENCE,) * 10 + (
    TaskType.EMAIL,
    TaskType.ACADEMIC_DISCUSSION,
)


@dataclass(frozen=True)
class BankTask:
    id: str
    type: TaskType
    difficulty: str
    content: TaskContent


class TaskSet(BaseModel):
    id: int
    task_ids: list[str]
