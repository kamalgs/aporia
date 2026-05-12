import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import event_stream
from app.content_registry.registry import registry
from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TranscriptEvent,
    TutorInputEvent,
    UtteranceEvent,
)
from app.domain.session import Session, SessionCreate
from app.roles.identity_role import get_identity_llm_client, run_identity
from app.roles.session_role import get_session_llm_client, run_session
from app.roles.state_updater import apply_turn_signal
from app.roles.trigger_policy import should_run_session_role
from app.roles.turn_role import get_llm_client, run_turn
from app.store import learners as learners_store
from app.store import sessions as sessions_store
from app.store import tutors as tutors_store

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


class WhisperRequest(BaseModel):
    tutor_id: str
    content: str


class SteerRequest(BaseModel):
    tutor_id: str
    goal: str
    skill_id: str
    difficulty_hint: str = "same"
    rationale: str = ""


class TakeoverRequest(BaseModel):
    tutor_id: str


class TutorTurnRequest(BaseModel):
    tutor_id: str
    text: str


class AnnotateRequest(BaseModel):
    tutor_id: str
    text: str


def _extract_pending_guidance(transcript: list[TranscriptEvent]) -> str:
    last_intent_idx = -1
    for i, e in enumerate(transcript):
        if isinstance(e, CoachIntentEvent):
            last_intent_idx = i
    whispers = [
        e for e in transcript[last_intent_idx + 1:]
        if isinstance(e, TutorInputEvent) and e.mode == "whisper"
    ]
    return "\n".join(w.content for w in whispers)


def _is_taken_over(transcript: list[TranscriptEvent]) -> bool:
    """Scan from the end; return True if the last tutor mode event is takeover."""
    for event in reversed(transcript):
        if isinstance(event, TutorInputEvent):
            if event.mode == "takeover":
                return True
            if event.mode == "handback":
                return False
    return False


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
    await event_stream.publish(session_id, body.event.model_dump(mode="json"))


@router.get("/{session_id}/stream")
async def stream_session(session_id: str) -> StreamingResponse:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    replay = [e.model_dump(mode="json") for e in session.transcript]

    async def generator():
        async for evt in event_stream.subscribe(session_id, replay):
            yield f"data: {json.dumps(evt)}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")


@router.post("/{session_id}/end", response_model=Session)
async def end_session(
    session_id: str,
    body: EndSessionRequest,
    identity_llm=Depends(get_identity_llm_client),
) -> Session:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    session = await sessions_store.end(session_id, body.summary_md)

    learner = await learners_store.get(session.learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    reg = registry()
    program = reg.program(session.program_id)
    if program is not None:
        guardian_profile = reg.find_guardian_profile(learner.cohort_tags)
        program_state = learner.program_states.get(session.program_id, {})
        new_portrait = await run_identity(
            program=program,
            guardian_profile=guardian_profile,
            prior_portrait=learner.portrait_md,
            program_state=program_state,
            transcript=session.transcript,
            llm_client=identity_llm,
        )
        await learners_store.update_portrait(learner.id, new_portrait)

    return session


@router.post("/{session_id}/whisper", status_code=204)
async def post_whisper(session_id: str, body: WhisperRequest) -> None:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    tutor = await tutors_store.get(body.tutor_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    evt = TutorInputEvent(mode="whisper", tutor_id=body.tutor_id, content=body.content)
    await sessions_store.append_event(session_id, evt)
    await event_stream.publish(session_id, evt.model_dump(mode="json"))


@router.post("/{session_id}/steer", status_code=204)
async def post_steer(session_id: str, body: SteerRequest) -> None:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    tutor = await tutors_store.get(body.tutor_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    steer_log = TutorInputEvent(
        mode="steer",
        tutor_id=body.tutor_id,
        content=json.dumps({
            "goal": body.goal,
            "skill_id": body.skill_id,
            "difficulty_hint": body.difficulty_hint,
        }),
    )
    await sessions_store.append_event(session_id, steer_log)
    await event_stream.publish(session_id, steer_log.model_dump(mode="json"))
    intent = CoachIntentEvent(
        goal=body.goal,
        skill_id=body.skill_id,
        difficulty_hint=body.difficulty_hint,
        rationale=f"[TUTOR STEER] {body.rationale}",
    )
    await sessions_store.append_event(session_id, intent)
    await event_stream.publish(session_id, intent.model_dump(mode="json"))


@router.post("/{session_id}/takeover", status_code=204)
async def takeover_session(session_id: str, body: TakeoverRequest) -> None:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    tutor = await tutors_store.get(body.tutor_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    evt = TutorInputEvent(mode="takeover", tutor_id=body.tutor_id, content="")
    await sessions_store.append_event(session_id, evt)
    await event_stream.publish(session_id, evt.model_dump(mode="json"))


@router.post("/{session_id}/handback", status_code=204)
async def handback_session(session_id: str, body: TakeoverRequest) -> None:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    tutor = await tutors_store.get(body.tutor_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    evt = TutorInputEvent(mode="handback", tutor_id=body.tutor_id, content="")
    await sessions_store.append_event(session_id, evt)
    await event_stream.publish(session_id, evt.model_dump(mode="json"))


@router.post("/{session_id}/tutor-turn", response_model=TurnResponse)
async def tutor_turn(session_id: str, body: TutorTurnRequest) -> TurnResponse:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    tutor = await tutors_store.get(body.tutor_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    if not _is_taken_over(session.transcript):
        raise HTTPException(status_code=409, detail="Session is not in takeover mode")
    utterance = UtteranceEvent(text=body.text)
    await sessions_store.append_event(session_id, utterance)
    await event_stream.publish(session_id, utterance.model_dump(mode="json"))
    return TurnResponse(
        utterance=body.text,
        turn_signal={"kind": "turn_signal", "on_target": True,
                     "matched_markers": [], "affect": {}, "notes": ""},
    )


@router.post("/{session_id}/turns/{turn_idx}/annotate", status_code=204)
async def annotate_turn(session_id: str, turn_idx: int, body: AnnotateRequest) -> None:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    tutor = await tutors_store.get(body.tutor_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    if turn_idx < 0 or turn_idx >= len(session.transcript):
        raise HTTPException(status_code=422, detail="turn_idx out of range")
    evt = TutorInputEvent(
        mode="annotation",
        tutor_id=body.tutor_id,
        content=body.text,
        target_turn_idx=turn_idx,
    )
    await sessions_store.append_event(session_id, evt)
    await event_stream.publish(session_id, evt.model_dump(mode="json"))


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

    if _is_taken_over(session.transcript):
        raise HTTPException(
            status_code=409,
            detail="Session is taken over by tutor; use /tutor-turn instead",
        )

    learner = await learners_store.get(session.learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    program_state = learner.program_states.get(session.program_id, {})

    if should_run_session_role(session.transcript, program_state):
        reg = registry()
        program = reg.program(session.program_id)
        if program is None:
            raise HTTPException(status_code=422, detail=f"Program '{session.program_id}' not found")
        coach_profile = reg.coach_profile(program.coach_profile_id) if program.coach_profile_id else None
        pending_guidance = _extract_pending_guidance(session.transcript)
        intent = await run_session(
            program=program,
            coach_profile=coach_profile,
            learner_portrait=learner.portrait_md,
            program_state=program_state,
            transcript_window=session.transcript,
            llm_client=session_llm,
            pending_guidance=pending_guidance,
        )
        await sessions_store.append_event(session_id, intent)
        await event_stream.publish(session_id, intent.model_dump(mode="json"))
        session = await sessions_store.get(session_id)

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

    learner_evt = LearnerTextEvent(text=body.text)
    await sessions_store.append_event(session_id, learner_evt)
    await event_stream.publish(session_id, learner_evt.model_dump(mode="json"))
    session = await sessions_store.get(session_id)

    utterance_event, signal_event = await run_turn(
        intent=current_intent,
        skill=skill,
        transcript_window=session.transcript,
        learner_text=body.text,
        llm_client=turn_llm,
    )

    await sessions_store.append_event(session_id, utterance_event)
    await event_stream.publish(session_id, utterance_event.model_dump(mode="json"))
    await sessions_store.append_event(session_id, signal_event)
    await event_stream.publish(session_id, signal_event.model_dump(mode="json"))

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
