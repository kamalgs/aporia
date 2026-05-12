from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.content_registry.registry import registry
from app.domain.events import CoachIntentEvent, LearnerTextEvent, TranscriptEvent
from app.domain.session import Session, SessionCreate
from app.roles.session_role import get_session_llm_client, run_session
from app.roles.state_updater import apply_turn_signal
from app.roles.trigger_policy import should_run_session_role
from app.roles.turn_role import get_llm_client, run_turn
from app.store import learners as learners_store
from app.store import sessions as sessions_store

router = APIRouter(prefix="/sessions", tags=["sessions"])


class AppendEventRequest(BaseModel):
    event: TranscriptEvent


class EndSessionRequest(BaseModel):
    summary_md: str = ""


class TurnRequest(BaseModel):
    text: str


class TurnResponse(BaseModel):
    utterance: str
    turn_signal: dict


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
    turn_llm=Depends(get_llm_client),
    session_llm=Depends(get_session_llm_client),
) -> TurnResponse:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    learner = await learners_store.get(session.learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    program_state = learner.program_states.get(session.program_id, {})

    # Run session role if trigger policy fires (session start, mastery, or struggle)
    if should_run_session_role(session.transcript, program_state):
        reg = registry()
        program = reg.program(session.program_id)
        if program is None:
            raise HTTPException(status_code=422, detail=f"Program '{session.program_id}' not found")
        coach_profile = reg.coach_profile(program.coach_profile_id) if program.coach_profile_id else None
        intent = await run_session(
            program=program,
            coach_profile=coach_profile,
            learner_portrait=learner.portrait_md,
            program_state=program_state,
            transcript_window=session.transcript,
            llm_client=session_llm,
        )
        await sessions_store.append_event(session_id, intent)
        session = await sessions_store.get(session_id)

    # Derive current intent from most recent CoachIntentEvent
    current_intent: CoachIntentEvent | None = None
    for event in reversed(session.transcript):
        if isinstance(event, CoachIntentEvent):
            current_intent = event
            break

    if current_intent is None or current_intent.skill_id is None:
        raise HTTPException(status_code=422, detail="No skill available for this session")

    skill = registry().skill(current_intent.skill_id)
    if skill is None:
        raise HTTPException(status_code=422, detail=f"Skill '{current_intent.skill_id}' not found in registry")

    # Record learner input and reload
    await sessions_store.append_event(session_id, LearnerTextEvent(text=body.text))
    session = await sessions_store.get(session_id)

    # Run turn role
    utterance_event, signal_event = await run_turn(
        intent=current_intent,
        skill=skill,
        transcript_window=session.transcript,
        learner_text=body.text,
        llm_client=turn_llm,
    )

    await sessions_store.append_event(session_id, utterance_event)
    await sessions_store.append_event(session_id, signal_event)

    # Deterministic state update — fold signal into learner's program state
    updated_state = apply_turn_signal(program_state, current_intent.skill_id, signal_event)
    await learners_store.update_program_state(
        learner_id=session.learner_id,
        program_id=session.program_id,
        skill_id=current_intent.skill_id,
        skill_state=updated_state[current_intent.skill_id],
    )

    return TurnResponse(
        utterance=utterance_event.text,
        turn_signal=signal_event.model_dump(mode="json"),
    )
