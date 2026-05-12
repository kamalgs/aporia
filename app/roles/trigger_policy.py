from app.domain.events import CoachIntentEvent, TranscriptEvent, TurnSignalEvent

MASTERY_THRESHOLD = 3


def should_run_session_role(transcript: list[TranscriptEvent], program_state: dict) -> bool:
    """Return True if the session role should run before the next turn."""
    if not any(isinstance(e, CoachIntentEvent) for e in transcript):
        return True

    recent_signals = [e for e in transcript if isinstance(e, TurnSignalEvent)][-MASTERY_THRESHOLD:]
    if len(recent_signals) >= MASTERY_THRESHOLD:
        if all(s.on_target for s in recent_signals):
            return True
        if all(not s.on_target for s in recent_signals):
            return True

    return False
