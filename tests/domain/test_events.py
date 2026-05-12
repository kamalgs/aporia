from pydantic import TypeAdapter

from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TranscriptEvent,
    TurnSignalEvent,
    TutorInputEvent,
    UtteranceEvent,
)


_adapter = TypeAdapter(TranscriptEvent)


def test_learner_text_roundtrip() -> None:
    event = LearnerTextEvent(text="hello")
    rebuilt = _adapter.validate_python(event.model_dump())
    assert isinstance(rebuilt, LearnerTextEvent)
    assert rebuilt.text == "hello"


def test_utterance_roundtrip() -> None:
    event = UtteranceEvent(text="What is 25 + 36?", skill_id="add-2digit-carry")
    rebuilt = _adapter.validate_python(event.model_dump())
    assert isinstance(rebuilt, UtteranceEvent)
    assert rebuilt.skill_id == "add-2digit-carry"


def test_coach_intent_roundtrip() -> None:
    event = CoachIntentEvent(goal="warm_up", skill_id="add-2digit-carry", difficulty_hint="easier")
    rebuilt = _adapter.validate_python(event.model_dump())
    assert isinstance(rebuilt, CoachIntentEvent)
    assert rebuilt.goal == "warm_up"


def test_turn_signal_roundtrip() -> None:
    event = TurnSignalEvent(on_target=True, matched_markers=["correct"], affect={"confidence": 0.8})
    rebuilt = _adapter.validate_python(event.model_dump())
    assert isinstance(rebuilt, TurnSignalEvent)
    assert rebuilt.on_target is True
    assert rebuilt.matched_markers == ["correct"]


def test_tutor_input_roundtrip() -> None:
    event = TutorInputEvent(mode="whisper", tutor_id="t1", content="slow down")
    rebuilt = _adapter.validate_python(event.model_dump())
    assert isinstance(rebuilt, TutorInputEvent)
    assert rebuilt.mode == "whisper"


def test_unknown_kind_rejected() -> None:
    import pytest
    with pytest.raises(Exception):
        _adapter.validate_python({"kind": "unknown", "text": "x"})
