from app.domain.events import TurnSignalEvent
from app.roles.state_updater import apply_turn_signal


def _signal(on_target: bool, markers: list[str] | None = None) -> TurnSignalEvent:
    return TurnSignalEvent(on_target=on_target, matched_markers=markers or [])


def test_first_correct_turn_initialises_state() -> None:
    result = apply_turn_signal({}, "skill-a", _signal(on_target=True))
    assert result["skill-a"]["attempt_count"] == 1
    assert result["skill-a"]["correct_count"] == 1
    assert result["skill-a"]["consecutive_correct"] == 1
    assert result["skill-a"]["consecutive_incorrect"] == 0


def test_consecutive_correct_increments() -> None:
    state = {}
    state = apply_turn_signal(state, "skill-a", _signal(True))
    state = apply_turn_signal(state, "skill-a", _signal(True))
    assert state["skill-a"]["consecutive_correct"] == 2


def test_incorrect_resets_consecutive_correct() -> None:
    state = apply_turn_signal({}, "skill-a", _signal(True))
    state = apply_turn_signal(state, "skill-a", _signal(True))
    state = apply_turn_signal(state, "skill-a", _signal(False))
    assert state["skill-a"]["consecutive_correct"] == 0
    assert state["skill-a"]["consecutive_incorrect"] == 1


def test_correct_resets_consecutive_incorrect() -> None:
    state = apply_turn_signal({}, "skill-a", _signal(False))
    state = apply_turn_signal(state, "skill-a", _signal(False))
    state = apply_turn_signal(state, "skill-a", _signal(True))
    assert state["skill-a"]["consecutive_incorrect"] == 0
    assert state["skill-a"]["consecutive_correct"] == 1


def test_matched_markers_accumulate() -> None:
    state = apply_turn_signal({}, "skill-a", _signal(False, ["Forgetting to carry"]))
    state = apply_turn_signal(state, "skill-a", _signal(False, ["Forgetting to carry"]))
    assert state["skill-a"]["matched_markers"]["Forgetting to carry"] == 2


def test_does_not_mutate_input() -> None:
    original = {}
    result = apply_turn_signal(original, "skill-a", _signal(True))
    assert original == {}
    assert result != original


def test_multiple_skills_are_independent() -> None:
    state = apply_turn_signal({}, "skill-a", _signal(True))
    state = apply_turn_signal(state, "skill-b", _signal(False))
    assert state["skill-a"]["correct_count"] == 1
    assert state["skill-b"]["consecutive_incorrect"] == 1
