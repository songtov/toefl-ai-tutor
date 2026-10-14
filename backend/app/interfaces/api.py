import random
from datetime import datetime
from functools import partial
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import col, select

from app.application import tools
from app.application.agent import AgentLoop, Step, ToolRegistry
from app.application.llm import LLMProvider, LLMResult
from app.config import Settings, get_settings
from app.domain.assessment import Corrections, SentenceCorrection
from app.domain.task import CONTENT_MODELS, BuildSentenceTask, TaskContent, TaskType
from app.infrastructure.chatgpt_plan_provider import ChatGPTPlanProvider
from app.infrastructure.db import Response, Result, StudySession, Task
from app.infrastructure.openai_provider import OpenAIAPIProvider
from app.infrastructure.task_bank import load_bank, load_sets
from app.interfaces.deps import Auth, CurrentUser, Db

router = APIRouter()


def get_provider(
    settings: Annotated[Settings, Depends(get_settings)], auth: Auth, user: CurrentUser
) -> LLMProvider:
    try:
        if settings.llm_provider == "chatgpt_plan":
            return ChatGPTPlanProvider(settings, partial(auth.access_token, user.id))
        return OpenAIAPIProvider(settings)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e


def get_agent(
    provider: Annotated[LLMProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentLoop:
    registry = ToolRegistry()
    registry.register("score_response", partial(tools.score_response, provider))
    registry.register("score_discussion", partial(tools.score_discussion, provider))
    registry.register("correct_errors", partial(tools.correct_errors, provider))
    return AgentLoop(registry, max_steps=settings.agent_max_steps, timeout_s=settings.llm_timeout_s)


Agent = Annotated[AgentLoop, Depends(get_agent)]


class TaskOut(BaseModel):
    id: int
    type: str
    difficulty: str
    content: dict[str, Any]
    directions: str


class SessionOut(BaseModel):
    id: int
    plan_reason: str
    task_ids: list[int]
    cost_usd: float


class SetOut(BaseModel):
    id: int
    task_count: int
    session_id: int | None
    answered_count: int


class AnswerIn(BaseModel):
    text: str = ""
    chunks: list[str] | None = None


class UsageOut(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_usd: float


class CriterionOut(BaseModel):
    criterion: str
    rationale: str


class AnswerOut(BaseModel):
    result_id: int
    score: int
    max_score: int
    criteria: list[CriterionOut]
    corrections: list[SentenceCorrection]
    correct_answer: str | None
    usage: UsageOut


class TaskDetailOut(TaskOut):
    answer_text: str | None
    result: AnswerOut | None


class SessionDetailOut(BaseModel):
    id: int
    plan_reason: str
    started_at: datetime
    tasks: list[TaskDetailOut]


SCORE_STEPS = {
    TaskType.EMAIL: ("score_response", tools.SCORE_PROMPT_VERSION),
    TaskType.ACADEMIC_DISCUSSION: ("score_discussion", tools.DISCUSSION_SCORE_PROMPT_VERSION),
}
BUILD_SENTENCE_VERSION = "build-sentence-exact-v1"


def _content(task: Task) -> TaskContent:
    return CONTENT_MODELS[TaskType(task.type)].model_validate(task.content)


def _answer_out(result: Result, task: Task) -> AnswerOut:
    content = _content(task)
    is_sentence = isinstance(content, BuildSentenceTask)
    return AnswerOut(
        result_id=result.id,
        score=result.score,
        max_score=1 if is_sentence else 5,
        criteria=result.rubric,
        corrections=result.corrections,
        correct_answer=content.sentence(content.answer) if is_sentence else None,
        usage=UsageOut(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=result.cost_usd,
        ),
    )


def _task_out(task: Task) -> TaskOut:
    content = _content(task)
    public = content.model_dump()
    if isinstance(content, BuildSentenceTask):
        # The answer stays on the server; the learner sees the chunks in a fixed shuffled order.
        chunks = content.chunks()
        public = {
            "context": content.context,
            "template": content.template,
            "chunks": random.Random(task.id).sample(chunks, len(chunks)),
        }
    return TaskOut(
        id=task.id,
        type=task.type,
        difficulty=task.difficulty,
        content=public,
        directions=content.directions(),
    )


def _answered_count(db: Db, session_id: int) -> int:
    task_ids = select(Task.id).where(Task.session_id == session_id)
    return len(
        db.exec(
            select(Response.task_id).where(col(Response.task_id).in_(task_ids)).distinct()
        ).all()
    )


@router.get("/sets")
def list_sets(db: Db, user: CurrentUser) -> list[SetOut]:
    sessions = {
        s.bank_set_id: s
        for s in db.exec(
            select(StudySession).where(
                StudySession.user_id == user.id, col(StudySession.bank_set_id).is_not(None)
            )
        ).all()
    }
    out = []
    for task_set in load_sets().values():
        session = sessions.get(task_set.id)
        out.append(
            SetOut(
                id=task_set.id,
                task_count=len(task_set.task_ids),
                session_id=session.id if session else None,
                answered_count=_answered_count(db, session.id) if session else 0,
            )
        )
    return out


@router.post("/sets/{set_id}/session")
def open_set(set_id: int, db: Db, user: CurrentUser) -> SessionOut:
    """Returns the user's session for a set, creating it the first time the set is opened."""
    task_set = load_sets().get(set_id)
    if task_set is None:
        raise HTTPException(404, "set not found")
    session = db.exec(
        select(StudySession).where(
            StudySession.user_id == user.id, StudySession.bank_set_id == set_id
        )
    ).first()
    if session is None:
        bank = load_bank()
        session = StudySession(
            user_id=user.id,
            plan=[{"bank_id": i} for i in task_set.task_ids],
            plan_reason=f"Set {set_id}: a fixed Writing section from the task bank.",
            bank_set_id=set_id,
        )
        db.add(session)
        db.flush()
        db.add_all(
            Task(
                session_id=session.id,
                user_id=user.id,
                type=bank[i].type,
                difficulty=bank[i].difficulty,
                bank_id=i,
                content=bank[i].content.model_dump(),
            )
            for i in task_set.task_ids
        )
        db.commit()
    task_ids = db.exec(
        select(Task.id).where(Task.session_id == session.id).order_by(col(Task.id))
    ).all()
    return SessionOut(
        id=session.id,
        plan_reason=session.plan_reason,
        task_ids=list(task_ids),
        cost_usd=session.cost_usd,
    )


@router.get("/sessions/{session_id}")
def get_session(session_id: int, db: Db, user: CurrentUser) -> SessionDetailOut:
    session = db.get(StudySession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(404, "session not found")
    tasks = db.exec(select(Task).where(Task.session_id == session_id).order_by(col(Task.id))).all()
    details = []
    for task in tasks:
        response = db.exec(
            select(Response).where(Response.task_id == task.id).order_by(col(Response.id).desc())
        ).first()
        result = (
            db.exec(select(Result).where(Result.response_id == response.id)).first()
            if response
            else None
        )
        details.append(
            TaskDetailOut(
                **_task_out(task).model_dump(),
                answer_text=response.text if response else None,
                result=_answer_out(result, task) if result else None,
            )
        )
    return SessionDetailOut(
        id=session.id,
        plan_reason=session.plan_reason,
        started_at=session.started_at,
        tasks=details,
    )


@router.get("/sessions/{session_id}/next")
def next_task(session_id: int, db: Db, user: CurrentUser) -> TaskOut:
    session = db.get(StudySession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(404, "session not found")
    answered = select(Response.task_id)
    task = db.exec(
        select(Task)
        .where(Task.session_id == session_id, col(Task.id).not_in(answered))
        .order_by(col(Task.id))
    ).first()
    if task is None:
        raise HTTPException(404, "no remaining tasks")
    return _task_out(task)


def _save(db: Db, task: Task, text: str, **result_fields: Any) -> Result:
    response = Response(task_id=task.id, user_id=task.user_id, text=text)
    db.add(response)
    db.flush()
    result = Result(response_id=response.id, user_id=task.user_id, **result_fields)
    db.add(result)
    db.get(StudySession, task.session_id).cost_usd += result.cost_usd
    db.commit()
    return result


@router.post("/tasks/{task_id}/answer")
def answer_task(
    task_id: int, body: AnswerIn, db: Db, agent: Agent, user: CurrentUser
) -> AnswerOut:
    task = db.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(404, "task not found")
    if db.exec(select(Response).where(Response.task_id == task_id)).first():
        raise HTTPException(409, "task already answered")
    content = _content(task)

    if isinstance(content, BuildSentenceTask):
        if body.chunks is None or not content.fits(body.chunks):
            raise HTTPException(422, "fill every blank with the offered chunks")
        result = _save(
            db,
            task,
            content.sentence(body.chunks),
            score=int(body.chunks == content.answer),
            rubric=[],
            corrections=[],
            model="exact_match",
            prompt_version=BUILD_SENTENCE_VERSION,
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
        )
        return _answer_out(result, task)

    if not body.text.strip():
        raise HTTPException(422, "answer is empty")
    score_step, score_version = SCORE_STEPS[TaskType(task.type)]
    run = agent.run(
        [
            Step(score_step, {"task": content, "text": body.text}),
            Step("correct_errors", {"text": body.text}),
        ]
    )
    if run.stopped:
        raise HTTPException(504, run.stopped)
    scored: LLMResult[Any]
    corrected: LLMResult[Corrections]
    scored, corrected = run.outputs
    result = _save(
        db,
        task,
        body.text,
        score=scored.parsed.score,
        rubric=[c.model_dump() for c in scored.parsed.criteria],
        corrections=[c.model_dump(mode="json") for c in corrected.parsed.sentences],
        model=scored.model,
        prompt_version=f"{score_version}+{tools.CORRECT_PROMPT_VERSION}",
        latency_ms=scored.latency_ms + corrected.latency_ms,
        input_tokens=scored.usage.input_tokens + corrected.usage.input_tokens,
        output_tokens=scored.usage.output_tokens + corrected.usage.output_tokens,
        cost_usd=scored.usage.cost_usd + corrected.usage.cost_usd,
    )
    return _answer_out(result, task)
