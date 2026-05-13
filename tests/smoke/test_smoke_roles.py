import os

import pytest
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.domain.content import CoachProfile, GuardianProfile, Program, Skill
from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TurnSignalEvent,
    UtteranceEvent,
)
from app.roles.identity_role import run_identity
from app.roles.session_role import run_session
from app.roles.turn_role import run_turn

FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
DEEPSEEK_MODEL = "accounts/fireworks/models/deepseek-v4-pro"

pytestmark = pytest.mark.smoke


def _fireworks_model() -> OpenAIChatModel:
    api_key = os.environ.get("FIREWORKS_API_KEY", "")
    if not api_key:
        pytest.skip("FIREWORKS_API_KEY not set")
    return OpenAIChatModel(
        DEEPSEEK_MODEL,
        provider=OpenAIProvider(base_url=FIREWORKS_BASE_URL, api_key=api_key),
    )


_SKILL = Skill(
    id="add-2digit-carry",
    title="Two-digit addition with carrying",
    objective="Add two 2-digit numbers that require carrying.",
    mastery_description="Student solves 5 in a row correctly.",
    common_mistakes=[
        "Forgetting to carry — adds ones correctly but ignores carry (e.g. 47+36 = 73 instead of 83)",
        "Wrong carry amount — carries 2 instead of 1",
    ],
)

_INTENT = CoachIntentEvent(goal="warm_up", skill_id="add-2digit-carry")

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

_GUARDIAN = GuardianProfile(
    id="child-7-9",
    title="Child aged 7–9",
    cohort_description="Early-primary children aged 7–9.",
    cohort_tags=["child"],
    raw_md="Short attention spans. Use praise frequently.",
)


@pytest.mark.asyncio
async def test_turn_role_smoke() -> None:
    model = _fireworks_model()
    utterance_event, signal_event = await run_turn(
        intent=_INTENT,
        skill=_SKILL,
        transcript_window=[],
        learner_text="Hi, I'm ready to practice!",
        model=model,
    )
    assert isinstance(utterance_event.text, str)
    assert len(utterance_event.text) > 5
    assert isinstance(signal_event.on_target, bool)
    print(f"\nTurn utterance: {utterance_event.text}")
    print(f"On target: {signal_event.on_target}")


@pytest.mark.asyncio
async def test_turn_role_smoke_wrong_answer() -> None:
    model = _fireworks_model()
    utterance_event, signal_event = await run_turn(
        intent=CoachIntentEvent(goal="drill", skill_id="add-2digit-carry"),
        skill=_SKILL,
        transcript_window=[
            UtteranceEvent(text="What is 47 + 36?", skill_id="add-2digit-carry"),
            LearnerTextEvent(text="73"),
        ],
        learner_text="73",
        model=model,
    )
    assert isinstance(utterance_event.text, str)
    assert signal_event.on_target is False
    print(f"\nCorrection utterance: {utterance_event.text}")


@pytest.mark.asyncio
async def test_session_role_smoke() -> None:
    model = _fireworks_model()
    transcript = [
        UtteranceEvent(text="What is 3 + 4?"),
        LearnerTextEvent(text="7"),
        TurnSignalEvent(on_target=True),
        UtteranceEvent(text="What is 5 + 8?"),
        LearnerTextEvent(text="13"),
        TurnSignalEvent(on_target=True),
    ]
    intent = await run_session(
        program=_PROGRAM,
        coach_profile=_COACH_PROFILE,
        learner_portrait="New learner, first session.",
        program_state={"add-1digit": {"consecutive_correct": 2}},
        transcript_window=transcript,
        model=model,
    )
    assert intent.goal in {"warm_up", "probe", "teach", "drill", "consolidate", "rest", "wrap"}
    assert intent.skill_id in _PROGRAM.skill_ids
    print(f"\nSession intent: goal={intent.goal}, skill={intent.skill_id}, hint={intent.difficulty_hint}")
    print(f"Rationale: {intent.rationale}")


@pytest.mark.asyncio
async def test_identity_role_smoke() -> None:
    model = _fireworks_model()
    transcript = [
        CoachIntentEvent(goal="warm_up", skill_id="add-1digit"),
        UtteranceEvent(text="What is 3 + 4?", skill_id="add-1digit"),
        LearnerTextEvent(text="7"),
        TurnSignalEvent(on_target=True),
        UtteranceEvent(text="What is 47 + 36?", skill_id="add-2digit-carry"),
        LearnerTextEvent(text="73"),
        TurnSignalEvent(on_target=False, matched_markers=["Forgetting to carry"]),
        UtteranceEvent(text="Close! Remember to carry the 1. Try again.", skill_id="add-2digit-carry"),
        LearnerTextEvent(text="83"),
        TurnSignalEvent(on_target=True),
    ]
    portrait = await run_identity(
        program=_PROGRAM,
        guardian_profile=_GUARDIAN,
        prior_portrait="",
        program_state={"add-2digit-carry": {"consecutive_correct": 1}},
        transcript=transcript,
        model=model,
    )
    assert isinstance(portrait, str)
    assert len(portrait) > 50
    print(f"\nPortrait:\n{portrait}")
