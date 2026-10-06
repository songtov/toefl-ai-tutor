from collections.abc import Iterator
from datetime import datetime
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.application import tools
from app.application.agent import (
    FIXED_PLAN_REASON,
    AgentLoop,
    Step,
    ToolRegistry,
    fixed_session_plan,
)
from app.application.llm import LLMProvider, LLMResult
from app.config import Settings, get_settings
from app.domain.assessment import Corrections, CriterionRationale, Score, SentenceCorrection
from app.domain.task import EmailTask
from app.infrastructure.codex_cli_provider import CodexCLIProvider
from app.infrastructure.db import DEFAULT_USER_ID, Response, Result, StudySession, Task
from app.infrastructure.openai_provider import OpenAIAPIProvider

router = APIRouter()


def get_db(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as db:
        yield db


def get_provider(settings: Annotated[Settings, Depends(get_settings)]) -> LLMProvider:
    try:
        if settings.llm_provider == "codex_cli":
            return CodexCLIProvider(settings)
        return OpenAIAPIProvider(settings)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e


def get_agent(
    provider: Annotated[LLMProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentLoop:
    registry = ToolRegistry()
    registry.register(
        "generate_task",
        partial(tools.generate_task, provider, temperature=settings.llm_task_temperature),
    )
    registry.register("score_response", partial(tools.score_response, provider))
    registry.register("correct_errors", partial(tools.correct_errors, provider))
    return AgentLoop(registry, max_steps=settings.agent_max_steps, timeout_s=settings.llm_timeout_s)


Db = Annotated[Session, Depends(get_db)]
Agent = Annotated[AgentLoop, Depends(get_agent)]


class TaskOut(BaseModel):
    id: int
    type: str
    difficulty: str
    content: EmailTask
    directions: str


class SessionOut(BaseModel):
    id: int
    plan_reason: str
    task_ids: list[int]
    cost_usd: float


class SessionSummaryOut(BaseModel):
    id: int
    started_at: datetime
    task_count: int
    answered_count: int


class AnswerIn(BaseModel):
    text: str


class UsageOut(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_usd: float


class AnswerOut(BaseModel):
    result_id: int
    score: int
    criteria: list[CriterionRationale]
    corrections: list[SentenceCorrection]
    usage: UsageOut


class TaskDetailOut(TaskOut):
    answer_text: str | None
    result: AnswerOut | None


class SessionDetailOut(BaseModel):
    id: int
    plan_reason: str
    started_at: datetime
    tasks: list[TaskDetailOut]


def _answer_out(result: Result) -> AnswerOut:
    return AnswerOut(
        result_id=result.id,
        score=result.score,
        criteria=result.rubric,
        corrections=result.corrections,
        usage=UsageOut(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=result.cost_usd,
        ),
    )


def _task_out(task: Task) -> TaskOut:
    content = EmailTask.model_validate(task.content)
    return TaskOut(
        id=task.id,
        type=task.type,
        difficulty=task.difficulty,
        content=content,
        directions=content.directions(),
    )


@router.post("/sessions", status_code=201)
def start_session(db: Db, agent: Agent) -> SessionOut:
    plan = fixed_session_plan()
    outputs = []
    for step in plan:
        run = agent.run([Step(step.tool, {**step.args, "avoid": [o.parsed for o in outputs]})])
        if run.stopped:
            raise HTTPException(504, run.stopped)
        outputs.append(run.outputs[0])

    session = StudySession(
        user_id=DEFAULT_USER_ID,
        plan=[{"tool": s.tool, "args": s.args} for s in plan],
        plan_reason=FIXED_PLAN_REASON,
    )
    db.add(session)
    db.flush()
    tasks = []
    for step, out in zip(plan, outputs, strict=True):
        tasks.append(
            Task(
                session_id=session.id,
                user_id=DEFAULT_USER_ID,
                type=step.args["task_type"],
                difficulty=step.args["difficulty"],
                target_weakness=step.args["target_weakness"],
                content=out.parsed.model_dump(),
            )
        )
        session.cost_usd += out.usage.cost_usd
    db.add_all(tasks)
    db.commit()
    return SessionOut(
        id=session.id,
        plan_reason=session.plan_reason,
        task_ids=[t.id for t in tasks],
        cost_usd=session.cost_usd,
    )


@router.get("/sessions")
def list_sessions(db: Db) -> list[SessionSummaryOut]:
    sessions = db.exec(
        select(StudySession)
        .where(StudySession.user_id == DEFAULT_USER_ID)
        .order_by(col(StudySession.id).desc())
    ).all()
    out = []
    for session in sessions:
        task_ids = db.exec(select(Task.id).where(Task.session_id == session.id)).all()
        answered = db.exec(
            select(Response.task_id).where(col(Response.task_id).in_(task_ids)).distinct()
        ).all()
        out.append(
            SessionSummaryOut(
                id=session.id,
                started_at=session.started_at,
                task_count=len(task_ids),
                answered_count=len(answered),
            )
        )
    return out


@router.get("/sessions/{session_id}")
def get_session(session_id: int, db: Db) -> SessionDetailOut:
    session = db.get(StudySession, session_id)
    if session is None or session.user_id != DEFAULT_USER_ID:
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
                result=_answer_out(result) if result else None,
            )
        )
    return SessionDetailOut(
        id=session.id,
        plan_reason=session.plan_reason,
        started_at=session.started_at,
        tasks=details,
    )


@router.get("/sessions/{session_id}/next")
def next_task(session_id: int, db: Db) -> TaskOut:
    session = db.get(StudySession, session_id)
    if session is None or session.user_id != DEFAULT_USER_ID:
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


@router.post("/tasks/{task_id}/answer")
def answer_task(task_id: int, body: AnswerIn, db: Db, agent: Agent) -> AnswerOut:
    task = db.get(Task, task_id)
    if task is None or task.user_id != DEFAULT_USER_ID:
        raise HTTPException(404, "task not found")
    if not body.text.strip():
        raise HTTPException(422, "answer is empty")
    if db.exec(select(Response).where(Response.task_id == task_id)).first():
        raise HTTPException(409, "task already answered")

    content = EmailTask.model_validate(task.content)
    run = agent.run(
        [
            Step("score_response", {"task": content, "text": body.text}),
            Step("correct_errors", {"text": body.text}),
        ]
    )
    if run.stopped:
        raise HTTPException(504, run.stopped)
    scored: LLMResult[Score]
    corrected: LLMResult[Corrections]
    scored, corrected = run.outputs

    response = Response(task_id=task_id, user_id=DEFAULT_USER_ID, text=body.text)
    db.add(response)
    db.flush()
    usage = UsageOut(
        input_tokens=scored.usage.input_tokens + corrected.usage.input_tokens,
        output_tokens=scored.usage.output_tokens + corrected.usage.output_tokens,
        cost_usd=scored.usage.cost_usd + corrected.usage.cost_usd,
    )
    result = Result(
        response_id=response.id,
        user_id=DEFAULT_USER_ID,
        score=scored.parsed.score,
        rubric=[c.model_dump() for c in scored.parsed.criteria],
        corrections=[c.model_dump(mode="json") for c in corrected.parsed.sentences],
        model=scored.model,
        prompt_version=f"{tools.SCORE_PROMPT_VERSION}+{tools.CORRECT_PROMPT_VERSION}",
        latency_ms=scored.latency_ms + corrected.latency_ms,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=usage.cost_usd,
    )
    db.add(result)
    session = db.get(StudySession, task.session_id)
    session.cost_usd += usage.cost_usd
    db.commit()
    return AnswerOut(
        result_id=result.id,
        score=scored.parsed.score,
        criteria=scored.parsed.criteria,
        corrections=corrected.parsed.sentences,
        usage=usage,
    )
