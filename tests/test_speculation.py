import pytest

from app.speculation import SpeculationCache


def test_get_returns_none_on_empty():
    cache = SpeculationCache()
    assert cache.get("sess-1", "add-carry", "drill", "same", 0) is None


def test_put_and_get_round_trip():
    cache = SpeculationCache()
    cache.put("sess-1", "add-carry", "drill", "same", 0, "Nice try — you forgot the carry.")
    result = cache.get("sess-1", "add-carry", "drill", "same", 0)
    assert result == "Nice try — you forgot the carry."


def test_different_sessions_are_isolated():
    cache = SpeculationCache()
    cache.put("sess-A", "add-carry", "drill", "same", 0, "Response A")
    assert cache.get("sess-B", "add-carry", "drill", "same", 0) is None


def test_invalidate_clears_session_entries():
    cache = SpeculationCache()
    cache.put("sess-1", "add-carry", "drill", "same", 0, "Response")
    cache.put("sess-1", "add-carry", "drill", "same", 1, "Response 2")
    cache.invalidate("sess-1")
    assert cache.get("sess-1", "add-carry", "drill", "same", 0) is None
    assert cache.get("sess-1", "add-carry", "drill", "same", 1) is None


def test_invalidate_does_not_affect_other_sessions():
    cache = SpeculationCache()
    cache.put("sess-1", "add-carry", "drill", "same", 0, "Response 1")
    cache.put("sess-2", "add-carry", "drill", "same", 0, "Response 2")
    cache.invalidate("sess-1")
    assert cache.get("sess-2", "add-carry", "drill", "same", 0) == "Response 2"


def test_match_mistake_returns_index_on_hit():
    cache = SpeculationCache()
    mistakes = [
        "Forgetting to carry — adds ones correctly but ignores carry (e.g. 47+36 = 73 instead of 83)",
        "Wrong carry amount — carries 2 instead of 1",
    ]
    assert cache.match_mistake("73", mistakes) == 0
    assert cache.match_mistake("2", mistakes) == 1  # "2" appears in mistake[1]
    assert cache.match_mistake("99", mistakes) is None  # "99" not in any mistake


def test_match_mistake_returns_none_on_miss():
    cache = SpeculationCache()
    mistakes = ["Forgetting to carry (e.g. 47+36 = 73)"]
    assert cache.match_mistake("83", mistakes) is None
    assert cache.match_mistake("", mistakes) is None
