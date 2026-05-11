from __future__ import annotations
import uuid
from typing import Dict, List

from app.models import TurnData


class SessionStore:
    def __init__(self):
        self._sessions: Dict[str, List[TurnData]] = {}

    def create(self) -> str:
        session_id = str(uuid.uuid4())[:8]
        self._sessions[session_id] = []
        return session_id

    def get(self, session_id: str) -> List[TurnData] | None:
        return self._sessions.get(session_id)

    def append(self, session_id: str, turn: TurnData) -> None:
        history = self._sessions.get(session_id)
        if history is None:
            raise KeyError(f"Session {session_id} not found")
        history.append(turn)

    def all_turns(self, session_id: str) -> List[TurnData]:
        return list(self._sessions.get(session_id, []))


_store = SessionStore()


def get_store() -> SessionStore:
    return _store
