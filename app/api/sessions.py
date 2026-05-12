from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.content_registry.registry import registry
from app.domain.events import CoachIntentEvent, LearnerTextEvent, TranscriptEvent
from app.domain.session import Session, SessionCreate
from app.roles.turn_role import get_llm_client, run_turn
from app.store import sessions as sessions_store

router = APIRouter(prefix="/sessions", tags=["sessions"])

_DEFAULT_GOAL = "warm_up"


class AppendEventRequest(BaseModel):
    event: TranscriptEvent


class EndSessionRequest(BaseModel):
    summary_md: str = ""


class TurnRequest(BaseModel):
    text: str


class TurnResponse(BaseModel):
    utterance: str
    turn_signal: dict


def _derive_intent(session: Session) -> CoachIntentEvent:
    for event in reversed(session.transcript):
        if isinstance(event, CoachIntentEvent):
            return event
    reg = registry()
    program = reg.program(session.program_id)
    skill_id = None
    if program and program.mandatory_skill_ids:
        skill_id = program.mandatory_skill_ids[0]
    elif program and program.skill_ids:
        skill_id = program.skill_ids[0]
    return CoachIntentEvent(goal=_DEFAULT_GOAL, skill_id=skill_id)


@router.post("", response_model=Session, status_code=201)
async def create_session(body: SessionCreate) -> Session:
    return await sessions_store.insert(body)


@router.get("/{session_id}", response_model=Session)
async def get_session(session_id: str) -> Session:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/{session_id}/events", status_code=204)
async def append_event(session_id: str, body: AppendEventRequest) -> None:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await sessions_store.append_event(session_id, body.event)


@router.post("/{session_id}/end", response_model=Session)
async def end_session(session_id: str, body: EndSessionRequest) -> Session:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return await sessions_store.end(session_id, body.summary_md)


@router.post("/{session_id}/turn", response_model=TurnResponse)
async def session_turn(
    session_id: str,
    body: TurnRequest,
    llm_client=Depends(get_llm_client),
) -> TurnResponse:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    intent = _derive_intent(session)
    if intent.skill_id is None:
        raise HTTPException(status_code=422, detail="No skill available for this session")

    skill = registry().skill(intent.skill_id)
    if skill is None:
        raise HTTPException(status_code=422, detail=f"Skill '{intent.skill_id}' not found in registry")

    await sessions_store.append_event(session_id, CoachIntentEvent(
        goal=intent.goal,
        skill_id=intent.skill_id,
        difficulty_hint=intent.difficulty_hint,
        tone_note=intent.tone_note,
        rationale=intent.rationale,
    ))
    await sessions_store.append_event(session_id, LearnerTextEvent(text=body.text))

    session = await sessions_store.get(session_id)
    utterance_event, signal_event = await run_turn(
        intent=intent,
        skill=skill,
        transcript_window=session.transcript,
        learner_text=body.text,
        llm_client=llm_client,
    )

    await sessions_store.append_event(session_id, utterance_event)
    await sessions_store.append_event(session_id, signal_event)

    return TurnResponse(
        utterance=utterance_event.text,
        turn_signal=signal_event.model_dump(mode="json"),
    )
