from app.domain.events import CoachIntentEvent, TranscriptEvent, TurnSignalEvent, TutorInputEvent

MASTERY_THRESHOLD = 3


def _last_intent_idx(transcript: list[TranscriptEvent]) -> int:
    for i in range(len(transcript) - 1, -1, -1):
        if isinstance(transcript[i], CoachIntentEvent):
            return i
    return -1


def should_run_session_role(transcript: list[TranscriptEvent], program_state: dict) -> bool:
    """Return True if the session role should run before the next turn."""
    if not any(isinstance(e, CoachIntentEvent) for e in transcript):
        return True

    last_idx = _last_intent_idx(transcript)
    events_after = transcript[last_idx + 1:]
    if any(isinstance(e, TutorInputEvent) and e.mode == "whisper" for e in events_after):
        return True

    recent_signals = [e for e in transcript if isinstance(e, TurnSignalEvent)][-MASTERY_THRESHOLD:]
    if len(recent_signals) >= MASTERY_THRESHOLD:
        if all(s.on_target for s in recent_signals):
            return True
        if all(not s.on_target for s in recent_signals):
            return True

    return False
