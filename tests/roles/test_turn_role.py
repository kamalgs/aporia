from types import SimpleNamespace

import pytest

from app.domain.content import Skill
from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TurnSignalEvent,
    UtteranceEvent,
)
from app.roles.turn_role import run_turn


def _fake_client(utterance: str = "What is 47 + 36?", on_target: bool = True):
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        input={
                            "utterance": utterance,
                            "on_target": on_target,
                            "matched_markers": [],
                            "affect": {},
                            "notes": "",
                        },
                    )
                ]
            )

    class _FakeClient:
        messages = _FakeMessages()

    return _FakeClient()


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
    utterance_event, signal_event = await run_turn(
        intent=_INTENT,
        skill=_SKILL,
        transcript_window=[],
        learner_text="hello",
        llm_client=_fake_client(),
    )
    assert isinstance(utterance_event, UtteranceEvent)
    assert utterance_event.text == "What is 47 + 36?"
    assert utterance_event.skill_id == "add-2digit-carry"
    assert isinstance(signal_event, TurnSignalEvent)
    assert signal_event.on_target is True


@pytest.mark.asyncio
async def test_run_turn_off_target() -> None:
    utterance_event, signal_event = await run_turn(
        intent=_INTENT,
        skill=_SKILL,
        transcript_window=[],
        learner_text="I don't know",
        llm_client=_fake_client(utterance="Let's try a simpler one first.", on_target=False),
    )
    assert signal_event.on_target is False
    assert "simpler" in utterance_event.text


@pytest.mark.asyncio
async def test_run_turn_passes_transcript_window() -> None:
    window = [
        UtteranceEvent(text="What is 23 + 48?", skill_id="add-2digit-carry"),
        LearnerTextEvent(text="71"),
    ]
    utterance_event, signal_event = await run_turn(
        intent=_INTENT,
        skill=_SKILL,
        transcript_window=window,
        learner_text="ok",
        llm_client=_fake_client(),
    )
    assert utterance_event.text


@pytest.mark.asyncio
async def test_run_turn_matched_markers_captured() -> None:
    client = _fake_client()

    class _FakeMessagesWithMarkers:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        input={
                            "utterance": "Almost! You forgot to carry the 1.",
                            "on_target": False,
                            "matched_markers": ["Forgetting to carry"],
                            "affect": {"frustration": 0.3},
                            "notes": "student dropped carry",
                        },
                    )
                ]
            )

    client.messages = _FakeMessagesWithMarkers()
    _, signal_event = await run_turn(
        intent=_INTENT,
        skill=_SKILL,
        transcript_window=[],
        learner_text="73",
        llm_client=client,
    )
    assert "Forgetting to carry" in signal_event.matched_markers
    assert signal_event.affect.get("frustration") == pytest.approx(0.3)
    assert "dropped carry" in signal_event.notes
