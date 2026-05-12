from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.roles.session_role import get_session_llm_client
from app.roles.turn_role import get_llm_client


def _make_fake_turn_llm(utterance: str = "What is 47 + 36?", on_target: bool = True):
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        input={
                            "utterance": utterance,
                            "on_target": on_target,
                            "matched_markers": [],
                            "affect": {},
                            "notes": "",
                        },
                    )
                ]
            )

    class _FakeLLM:
        messages = _FakeMessages()

    return _FakeLLM()


def _make_fake_session_llm(goal: str = "warm_up", skill_id: str = "add-1digit"):
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        input={
                            "goal": goal,
                            "skill_id": skill_id,
                            "difficulty_hint": "same",
                            "rationale": "Starting warm up.",
                        },
                    )
                ]
            )

    class _FakeLLM:
        messages = _FakeMessages()

    return _FakeLLM()


@pytest.fixture
def fake_llm():
    return _make_fake_turn_llm()


@pytest.fixture
def client_with_fake_llm(client: AsyncClient, fake_llm):
    from app.main import app
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    app.dependency_overrides[get_session_llm_client] = lambda: _make_fake_session_llm()
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def session_id(client_with_fake_llm: AsyncClient) -> str:
    learner = (await client_with_fake_llm.post("/learners", json={"name": "Tester"})).json()
    session = (await client_with_fake_llm.post("/sessions", json={
        "learner_id": learner["id"],
        "program_id": "elementary-math",
    })).json()
    return session["id"]


@pytest.mark.asyncio
async def test_turn_returns_utterance(client_with_fake_llm: AsyncClient, session_id: str) -> None:
    resp = await client_with_fake_llm.post(
        f"/sessions/{session_id}/turn",
        json={"text": "hello"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["utterance"] == "What is 47 + 36?"
    assert "turn_signal" in body
    assert body["turn_signal"]["on_target"] is True


@pytest.mark.asyncio
async def test_turn_appends_events_to_transcript(client_with_fake_llm: AsyncClient, session_id: str) -> None:
    await client_with_fake_llm.post(f"/sessions/{session_id}/turn", json={"text": "5"})
    session = (await client_with_fake_llm.get(f"/sessions/{session_id}")).json()
    kinds = [e["kind"] for e in session["transcript"]]
    assert "learner_text" in kinds
    assert "utterance" in kinds
    assert "turn_signal" in kinds


@pytest.mark.asyncio
async def test_turn_missing_session_returns_404(client_with_fake_llm: AsyncClient) -> None:
    resp = await client_with_fake_llm.post("/sessions/no-such/turn", json={"text": "hi"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_turn_uses_existing_intent_from_transcript(client_with_fake_llm: AsyncClient, session_id: str) -> None:
    # Seed a CoachIntentEvent so trigger policy won't fire session role
    await client_with_fake_llm.post(
        f"/sessions/{session_id}/events",
        json={"event": {
            "kind": "coach_intent",
            "goal": "drill",
            "skill_id": "add-2digit-carry",
            "difficulty_hint": "harder",
        }},
    )
    resp = await client_with_fake_llm.post(f"/sessions/{session_id}/turn", json={"text": "ready"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_turn_empty_text_still_responds(client_with_fake_llm: AsyncClient, session_id: str) -> None:
    resp = await client_with_fake_llm.post(f"/sessions/{session_id}/turn", json={"text": ""})
    assert resp.status_code == 200
