from app.domain.events import TurnSignalEvent


def apply_turn_signal(program_state: dict, skill_id: str, signal: TurnSignalEvent) -> dict:
    """Fold a TurnSignalEvent into program_state for the given skill. Returns a new dict."""
    existing = program_state.get(skill_id, {})
    skill_state = {
        "attempt_count": existing.get("attempt_count", 0) + 1,
        "correct_count": existing.get("correct_count", 0),
        "consecutive_correct": existing.get("consecutive_correct", 0),
        "consecutive_incorrect": existing.get("consecutive_incorrect", 0),
        "matched_markers": dict(existing.get("matched_markers", {})),
    }
    if signal.on_target:
        skill_state["correct_count"] += 1
        skill_state["consecutive_correct"] += 1
        skill_state["consecutive_incorrect"] = 0
    else:
        skill_state["consecutive_correct"] = 0
        skill_state["consecutive_incorrect"] += 1
        for marker in signal.matched_markers:
            skill_state["matched_markers"][marker] = (
                skill_state["matched_markers"].get(marker, 0) + 1
            )
    return {**program_state, skill_id: skill_state}
