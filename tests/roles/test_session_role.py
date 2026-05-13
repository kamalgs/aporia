import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.domain.content import CoachProfile, Program
from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TurnSignalEvent,
    UtteranceEvent,
)
from app.roles.session_role import _session_agent, run_session


def _make_session_model(goal: str = "drill", skill_id: str = "add-2digit-carry") -> FunctionModel:
    def _fn(messages: list, info: AgentInfo) -> ModelResponse:
        tool_name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name, {
            "goal": goal,
            "skill_id": skill_id,
            "difficulty_hint": "same",
            "rationale": "Learner seems ready to drill.",
            "tone_note": None,
        })])
    return FunctionModel(_fn)


_PROGRAM = Program(
    id="elementary-math",
    title="Elementary Math",
    skill_ids=["add-1digit", "add-2digit-carry"],
    mandatory_skill_ids=["add-1digit", "add-2digit-carry"],
    assessment_criteria="Student solves both skill types reliably.",
    coach_profile_id="patient-encourager",
)

_COACH_PROFILE = CoachProfile(
    id="patient-encourager",
    title="Patient Encourager",
    tone="Warm and encouraging",
    pacing="Slow and steady",
)


@pytest.mark.asyncio
async def test_run_session_returns_coach_intent() -> None:
    with _session_agent.override(model=_make_session_model()):
        intent = await run_session(
            program=_PROGRAM,
            coach_profile=_COACH_PROFILE,
            learner_portrait="",
            program_state={},
            transcript_window=[],
        )
    assert isinstance(intent, CoachIntentEvent)
    assert intent.goal == "drill"
    assert intent.skill_id == "add-2digit-carry"


@pytest.mark.asyncio
async def test_run_session_uses_rationale() -> None:
    with _session_agent.override(model=_make_session_model(goal="consolidate")):
        intent = await run_session(
            program=_PROGRAM,
            coach_profile=_COACH_PROFILE,
            learner_portrait="Quick learner, confident.",
            program_state={},
            transcript_window=[],
        )
    assert intent.goal == "consolidate"
    assert intent.rationale


@pytest.mark.asyncio
async def test_run_session_with_transcript() -> None:
    transcript = [
        UtteranceEvent(text="What is 2+3?"),
        LearnerTextEvent(text="5"),
        TurnSignalEvent(on_target=True),
        UtteranceEvent(text="What is 47+36?"),
        LearnerTextEvent(text="83"),
        TurnSignalEvent(on_target=True),
    ]
    with _session_agent.override(model=_make_session_model(goal="wrap")):
        intent = await run_session(
            program=_PROGRAM,
            coach_profile=_COACH_PROFILE,
            learner_portrait="",
            program_state={"add-2digit-carry": {"consecutive_correct": 3}},
            transcript_window=transcript,
        )
    assert intent.goal == "wrap"
