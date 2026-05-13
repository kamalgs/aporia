import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.domain.content import GuardianProfile, Program
from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TurnSignalEvent,
    UtteranceEvent,
)
from app.roles.identity_role import _identity_agent, run_identity


def _make_identity_model(portrait: str = "Alice is a confident learner who grasps carrying quickly.") -> FunctionModel:
    def _fn(messages: list, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "portrait_md": portrait,
        })])
    return FunctionModel(_fn)


_PROGRAM = Program(
    id="elementary-math",
    title="Elementary Math",
    skill_ids=["add-1digit", "add-2digit-carry"],
    mandatory_skill_ids=["add-1digit", "add-2digit-carry"],
    assessment_criteria="Student solves both skill types reliably.",
)

_GUARDIAN = GuardianProfile(
    id="child-7-9",
    title="Child aged 7–9",
    cohort_description="Early-primary children.",
    cohort_tags=["child"],
    raw_md="Short attention spans. Use praise frequently.",
)

_TRANSCRIPT = [
    CoachIntentEvent(goal="warm_up", skill_id="add-1digit"),
    UtteranceEvent(text="What is 3+4?", skill_id="add-1digit"),
    LearnerTextEvent(text="7"),
    TurnSignalEvent(on_target=True),
    UtteranceEvent(text="What is 47+36?", skill_id="add-2digit-carry"),
    LearnerTextEvent(text="83"),
    TurnSignalEvent(on_target=True),
]


@pytest.mark.asyncio
async def test_run_identity_returns_portrait_string() -> None:
    with _identity_agent.override(model=_make_identity_model()):
        portrait = await run_identity(
            program=_PROGRAM,
            guardian_profile=_GUARDIAN,
            prior_portrait="",
            program_state={},
            transcript=_TRANSCRIPT,
        )
    assert isinstance(portrait, str)
    assert "Alice" in portrait


@pytest.mark.asyncio
async def test_run_identity_with_prior_portrait() -> None:
    with _identity_agent.override(model=_make_identity_model("Alice is becoming more confident session by session.")):
        portrait = await run_identity(
            program=_PROGRAM,
            guardian_profile=_GUARDIAN,
            prior_portrait="Alice joined today. Very shy at first.",
            program_state={"add-2digit-carry": {"consecutive_correct": 2}},
            transcript=_TRANSCRIPT,
        )
    assert "confident" in portrait


@pytest.mark.asyncio
async def test_run_identity_without_guardian_profile() -> None:
    with _identity_agent.override(model=_make_identity_model("Learner shows solid grasp of addition.")):
        portrait = await run_identity(
            program=_PROGRAM,
            guardian_profile=None,
            prior_portrait="",
            program_state={},
            transcript=_TRANSCRIPT,
        )
    assert portrait
