from app.domain.events import CoachIntentEvent, TurnSignalEvent, TutorInputEvent, UtteranceEvent
from app.roles.trigger_policy import MASTERY_THRESHOLD, should_run_session_role


def _intent() -> CoachIntentEvent:
    return CoachIntentEvent(goal="warm_up", skill_id="s1")


def _signal(on_target: bool) -> TurnSignalEvent:
    return TurnSignalEvent(on_target=on_target)


def test_empty_transcript_triggers() -> None:
    assert should_run_session_role([], {}) is True


def test_transcript_with_only_non_intent_events_triggers() -> None:
    assert should_run_session_role([_signal(True)], {}) is True


def test_intent_present_and_few_signals_does_not_trigger() -> None:
    transcript = [_intent(), _signal(True), _signal(False)]
    assert should_run_session_role(transcript, {}) is False


def test_three_consecutive_correct_triggers() -> None:
    signals = [_signal(True)] * MASTERY_THRESHOLD
    transcript = [_intent()] + signals
    assert should_run_session_role(transcript, {}) is True


def test_three_consecutive_incorrect_triggers() -> None:
    signals = [_signal(False)] * MASTERY_THRESHOLD
    transcript = [_intent()] + signals
    assert should_run_session_role(transcript, {}) is True


def test_mixed_signals_no_trigger() -> None:
    transcript = [_intent(), _signal(True), _signal(False), _signal(True)]
    assert should_run_session_role(transcript, {}) is False


def test_non_signal_events_between_signals_ignored() -> None:
    transcript = [
        _intent(),
        UtteranceEvent(text="q1"),
        _signal(True),
        UtteranceEvent(text="q2"),
        _signal(True),
        UtteranceEvent(text="q3"),
        _signal(True),
    ]
    assert should_run_session_role(transcript, {}) is True


def test_pending_whisper_after_intent_triggers() -> None:
    transcript = [
        CoachIntentEvent(goal="warm_up", skill_id="add-1digit"),
        TutorInputEvent(mode="whisper", tutor_id="t1", content="go easier"),
    ]
    assert should_run_session_role(transcript, {}) is True


def test_whisper_before_intent_does_not_double_trigger() -> None:
    """Whisper consumed by the existing intent — no re-trigger on threshold alone."""
    transcript = [
        TutorInputEvent(mode="whisper", tutor_id="t1", content="go easier"),
        CoachIntentEvent(goal="teach", skill_id="add-1digit"),
    ]
    assert should_run_session_role(transcript, {}) is False
