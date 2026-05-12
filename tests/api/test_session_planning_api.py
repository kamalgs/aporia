from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.roles.session_role import get_session_llm_client
from app.roles.turn_role import get_llm_client


def _fake_turn_llm(on_target: bool = True):
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(
                    type="tool_use",
                    input={"utterance": "Good, next question.", "on_target": on_target,
                           "matched_markers": [], "affect": {}, "notes": ""},
                )]
            )

    class _FakeLLM:
        messages = _FakeMessages()

    return _FakeLLM()


def _fake_session_llm(goal: str = "warm_up", skill_id: str = "add-1digit"):
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(
                    type="tool_use",
                    input={"goal": goal, "skill_id": skill_id,
                           "difficulty_hint": "same", "rationale": "test"},
                )]
            )

    class _FakeLLM:
        messages = _FakeMessages()

    return _FakeLLM()


@pytest.fixture
def client_planning(client: AsyncClient):
    from app.main import app
    app.dependency_overrides[get_llm_client] = lambda: _fake_turn_llm()
    app.dependency_overrides[get_session_llm_client] = lambda: _fake_session_llm()
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def session_setup(client_planning: AsyncClient):
    learner = (await client_planning.post("/learners", json={"name": "Planner"})).json()
    session = (await client_planning.post("/sessions", json={
        "learner_id": learner["id"],
        "program_id": "elementary-math",
    })).json()
    return client_planning, learner["id"], session["id"]


@pytest.mark.asyncio
async def test_first_turn_appends_session_role_intent(session_setup) -> None:
    client, learner_id, session_id = session_setup
    await client.post(f"/sessions/{session_id}/turn", json={"text": "hi"})
    session = (await client.get(f"/sessions/{session_id}")).json()
    intent_events = [e for e in session["transcript"] if e["kind"] == "coach_intent"]
    assert len(intent_events) >= 1
    assert intent_events[0]["goal"] == "warm_up"


@pytest.mark.asyncio
async def test_program_state_updated_after_turn(session_setup) -> None:
    client, learner_id, session_id = session_setup
    await client.post(f"/sessions/{session_id}/turn", json={"text": "5"})
    learner = (await client.get(f"/learners/{learner_id}")).json()
    prog_state = learner["program_states"].get("elementary-math", {})
    assert len(prog_state) > 0


@pytest.mark.asyncio
async def test_session_role_fires_after_mastery_threshold(session_setup) -> None:
    from app.main import app
    call_count = {"n": 0}

    def _counting_session_llm():
        call_count["n"] += 1
        return _fake_session_llm(goal="drill", skill_id="add-2digit-carry")

    app.dependency_overrides[get_session_llm_client] = _counting_session_llm

    client, learner_id, session_id = session_setup
    # First turn: session role fires at start (call 1)
    await client.post(f"/sessions/{session_id}/turn", json={"text": "hi"})
    # Inject 3 consecutive correct signals to trip the mastery threshold
    for _ in range(3):
        await client.post(
            f"/sessions/{session_id}/events",
            json={"event": {"kind": "turn_signal", "on_target": True}},
        )
    # Next turn: trigger policy fires session role again (call 2)
    await client.post(f"/sessions/{session_id}/turn", json={"text": "83"})
    assert call_count["n"] >= 2


@pytest.mark.asyncio
async def test_session_role_fires_after_struggle_threshold(session_setup) -> None:
    from app.main import app
    recorded_intents = []

    def _recording_session_llm():
        class _FakeMessages:
            def create(self, **kwargs):
                recorded_intents.append(True)
                return SimpleNamespace(
                    content=[SimpleNamespace(
                        type="tool_use",
                        input={"goal": "teach", "skill_id": "add-1digit",
                               "difficulty_hint": "easier", "rationale": "too hard"},
                    )]
                )

        class _FakeLLM:
            messages = _FakeMessages()

        return _FakeLLM()

    app.dependency_overrides[get_session_llm_client] = _recording_session_llm

    client, learner_id, session_id = session_setup
    await client.post(f"/sessions/{session_id}/turn", json={"text": "start"})
    for _ in range(3):
        await client.post(
            f"/sessions/{session_id}/events",
            json={"event": {"kind": "turn_signal", "on_target": False}},
        )
    await client.post(f"/sessions/{session_id}/turn", json={"text": "idk"})

    session = (await client.get(f"/sessions/{session_id}")).json()
    intents = [e for e in session["transcript"] if e["kind"] == "coach_intent"]
    assert len(intents) >= 2
    last = intents[-1]
    assert last["skill_id"] == "add-1digit"
