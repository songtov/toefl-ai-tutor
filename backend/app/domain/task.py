from enum import StrEnum

from pydantic import BaseModel, field_validator


class TaskType(StrEnum):
    EMAIL = "write_an_email"


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
