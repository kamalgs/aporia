import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.domain.content import Skill
from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TurnSignalEvent,
    UtteranceEvent,
)
from app.roles.turn_role import _turn_agent, run_turn, run_turn_for_speculation


def _make_turn_model(utterance: str = "What is 47 + 36?", on_target: bool = True) -> FunctionModel:
    def _fn(messages: list, info: AgentInfo) -> ModelResponse:
        tool_name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name, {
            "utterance": utterance,
            "on_target": on_target,
            "matched_markers": [],
            "affect": {},
            "notes": "",
        })])
    return FunctionModel(_fn)


_SKILL = Skill(
    id="add-2digit-carry",
    title="Two-digit addition with carrying",
    objective="Add two 2-digit numbers that require carrying.",
    mastery_description="Student solves consistently.",
    common_mistakes=["Forgetting to carry"],
)

_INTENT = CoachIntentEvent(goal="warm_up", skill_id="add-2digit-carry")


@pytest.mark.asyncio
async def test_run_turn_returns_utterance_and_signal() -> None:
    with _turn_agent.override(model=_make_turn_model()):
        utterance_event, signal_event = await run_turn(
            intent=_INTENT,
            skill=_SKILL,
            transcript_window=[],
            learner_text="hello",
        )
    assert utterance_event.text == "What is 47 + 36?"
    assert utterance_event.skill_id == "add-2digit-carry"
    assert signal_event.on_target is True


@pytest.mark.asyncio
async def test_run_turn_off_target() -> None:
    with _turn_agent.override(model=_make_turn_model("Let's try a simpler one first.", False)):
        utterance_event, signal_event = await run_turn(
            intent=_INTENT,
            skill=_SKILL,
            transcript_window=[],
            learner_text="I don't know",
        )
    assert signal_event.on_target is False
    assert "simpler" in utterance_event.text


@pytest.mark.asyncio
async def test_run_turn_passes_transcript_window() -> None:
    window = [
        UtteranceEvent(text="What is 23 + 48?", skill_id="add-2digit-carry"),
        LearnerTextEvent(text="71"),
    ]
    with _turn_agent.override(model=_make_turn_model()):
        utterance_event, _ = await run_turn(
            intent=_INTENT,
            skill=_SKILL,
            transcript_window=window,
            learner_text="ok",
        )
    assert utterance_event.text


@pytest.mark.asyncio
async def test_run_turn_matched_markers_captured() -> None:
    def _fn(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "utterance": "Almost! You forgot to carry the 1.",
            "on_target": False,
            "matched_markers": ["Forgetting to carry"],
            "affect": {"frustration": 0.3},
            "notes": "student dropped carry",
        })])

    with _turn_agent.override(model=FunctionModel(_fn)):
        _, signal_event = await run_turn(
            intent=_INTENT,
            skill=_SKILL,
            transcript_window=[],
            learner_text="73",
        )
    assert "Forgetting to carry" in signal_event.matched_markers
    assert signal_event.affect.get("frustration") == pytest.approx(0.3)
    assert "dropped carry" in signal_event.notes


@pytest.mark.asyncio
async def test_run_turn_for_speculation_returns_utterance_string() -> None:
    def _fn(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "utterance": "You forgot to carry.",
            "on_target": False,
            "matched_markers": [],
            "affect": {},
            "notes": "",
        })])

    with _turn_agent.override(model=FunctionModel(_fn)):
        utterance = await run_turn_for_speculation(
            intent=CoachIntentEvent(goal="drill", skill_id="add-2digit-carry"),
            skill=_SKILL,
            mistake_text="Forgetting to carry",
        )
    assert isinstance(utterance, str)
    assert len(utterance) > 0
