from __future__ import annotations


class SpeculationCache:
    """In-process cache for pre-generated turn-role responses.

    Key: (session_id, skill_id, goal, difficulty_hint, mistake_idx)
    Value: pre-generated utterance string
    """

    def __init__(self) -> None:
        self._store: dict[tuple, str] = {}

    def _key(
        self,
        session_id: str,
        skill_id: str,
        goal: str,
        difficulty_hint: str,
        mistake_idx: int,
    ) -> tuple:
        return (session_id, skill_id, goal, difficulty_hint, mistake_idx)

    def get(
        self,
        session_id: str,
        skill_id: str,
        goal: str,
        difficulty_hint: str,
        mistake_idx: int,
    ) -> str | None:
        return self._store.get(self._key(session_id, skill_id, goal, difficulty_hint, mistake_idx))

    def put(
        self,
        session_id: str,
        skill_id: str,
        goal: str,
        difficulty_hint: str,
        mistake_idx: int,
        utterance: str,
    ) -> None:
        self._store[self._key(session_id, skill_id, goal, difficulty_hint, mistake_idx)] = utterance

    def invalidate(self, session_id: str) -> None:
        self._store = {k: v for k, v in self._store.items() if k[0] != session_id}

    def match_mistake(self, learner_text: str, mistakes: list[str]) -> int | None:
        """Return the index of the first mistake whose description contains the learner text.

        Works well for short numeric answers (e.g. '73' in 'e.g. 47+36 = 73 instead of 83').
        Returns None on no match.
        """
        text = learner_text.strip()
        if not text:
            return None
        for i, mistake in enumerate(mistakes):
            if text in mistake:
                return i
        return None


_cache = SpeculationCache()


def cache() -> SpeculationCache:
    return _cache
