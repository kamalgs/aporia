from types import SimpleNamespace

import pytest

from app.domain.content import CoachProfile, Program
from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TurnSignalEvent,
    UtteranceEvent,
)
from app.roles.session_role import run_session


def _fake_session_client(goal: str = "drill", skill_id: str = "add-2digit-carry"):
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        input={
                            "goal": goal,
                            "skill_id": skill_id,
                            "difficulty_hint": "same",
                            "rationale": "Learner seems ready to drill.",
                            "tone_note": None,
                        },
                    )
                ]
            )

    class _FakeClient:
        messages = _FakeMessages()

    return _FakeClient()


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
    intent = await run_session(
        program=_PROGRAM,
        coach_profile=_COACH_PROFILE,
        learner_portrait="",
        program_state={},
        transcript_window=[],
        llm_client=_fake_session_client(),
    )
    assert isinstance(intent, CoachIntentEvent)
    assert intent.goal == "drill"
    assert intent.skill_id == "add-2digit-carry"


@pytest.mark.asyncio
async def test_run_session_uses_rationale() -> None:
    intent = await run_session(
        program=_PROGRAM,
        coach_profile=_COACH_PROFILE,
        learner_portrait="Quick learner, confident.",
        program_state={},
        transcript_window=[],
        llm_client=_fake_session_client(goal="consolidate"),
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
        UtteranceEvent(text="Excellent!"),
        LearnerTextEvent(text="thanks"),
        TurnSignalEvent(on_target=True),
    ]
    intent = await run_session(
        program=_PROGRAM,
        coach_profile=_COACH_PROFILE,
        learner_portrait="",
        program_state={"add-2digit-carry": {"consecutive_correct": 3}},
        transcript_window=transcript,
        llm_client=_fake_session_client(goal="wrap"),
    )
    assert intent.goal == "wrap"
