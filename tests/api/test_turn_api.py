import json

import pytest
from httpx import AsyncClient
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.roles.session_role import get_session_model
from app.roles.turn_role import get_turn_model


def _make_fake_turn_model(utterance: str = "What is 47 + 36?", on_target: bool = True) -> FunctionModel:
    def _fn(messages: list, info: AgentInfo) -> ModelResponse:
        tool_name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name, {
            "utterance": utterance,
            "on_target": on_target,
            "matched_markers": [],
            "affect": {},
            "notes": "",
        })])
    return FunctionModel(_fn)


def _make_fake_session_model(goal: str = "warm_up", skill_id: str = "add-1digit") -> FunctionModel:
    def _fn(messages: list, info: AgentInfo) -> ModelResponse:
        tool_name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name, {
            "goal": goal,
            "skill_id": skill_id,
            "difficulty_hint": "same",
            "rationale": "Starting warm up.",
            "tone_note": None,
        })])
    return FunctionModel(_fn)


@pytest.fixture
def fake_turn_model():
    return _make_fake_turn_model()


@pytest.fixture
def client_with_fake_llm(client: AsyncClient, fake_turn_model):
    from app.main import app
    app.dependency_overrides[get_turn_model] = lambda: fake_turn_model
    app.dependency_overrides[get_session_model] = lambda: _make_fake_session_model()
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


# ── Speculation cache tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_speculation_cache_hit_skips_turn_llm(client_with_fake_llm: AsyncClient, session_id: str) -> None:
    """Seeding the speculation cache causes the cached utterance to be returned."""
    from app.speculation import cache as get_cache

    # Seed add-2digit-carry intent directly — "73" appears in its mistake[0] description
    await client_with_fake_llm.post(
        f"/sessions/{session_id}/events",
        json={"event": {
            "kind": "coach_intent",
            "goal": "drill",
            "skill_id": "add-2digit-carry",
            "difficulty_hint": "same",
        }},
    )
    get_cache().put(session_id, "add-2digit-carry", "drill", "same", 0, "CACHED_UTTERANCE")

    resp = await client_with_fake_llm.post(f"/sessions/{session_id}/turn", json={"text": "73"})
    assert resp.status_code == 200
    assert resp.json()["utterance"] == "CACHED_UTTERANCE"


@pytest.mark.asyncio
async def test_speculation_cache_miss_falls_through_to_live(client_with_fake_llm: AsyncClient, session_id: str) -> None:
    """On cache miss the normal fake LLM response is returned."""
    resp = await client_with_fake_llm.post(f"/sessions/{session_id}/turn", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json()["utterance"] == "What is 47 + 36?"


# ── Streaming endpoint tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_turn_stream_returns_sse(client_with_fake_llm: AsyncClient, session_id: str) -> None:
    resp = await client_with_fake_llm.post(
        f"/sessions/{session_id}/turn/stream",
        json={"text": "hello"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    lines = [ln for ln in resp.text.split("\n") if ln.startswith("data:")]
    assert len(lines) >= 2

    events = [json.loads(ln[5:].strip()) for ln in lines]
    token_events = [e for e in events if e.get("type") == "token"]
    signal_events = [e for e in events if e.get("type") == "signal"]

    assert len(token_events) >= 1
    assert "".join(e["text"] for e in token_events).strip() == "What is 47 + 36?"
    assert len(signal_events) == 1
    assert signal_events[0]["on_target"] is True


@pytest.mark.asyncio
async def test_turn_stream_appends_events_to_transcript(client_with_fake_llm: AsyncClient, session_id: str) -> None:
    await client_with_fake_llm.post(f"/sessions/{session_id}/turn/stream", json={"text": "5"})
    session = (await client_with_fake_llm.get(f"/sessions/{session_id}")).json()
    kinds = [e["kind"] for e in session["transcript"]]
    assert "learner_text" in kinds
    assert "utterance" in kinds
    assert "turn_signal" in kinds


@pytest.mark.asyncio
async def test_turn_stream_from_cache(client_with_fake_llm: AsyncClient, session_id: str) -> None:
    from app.speculation import cache as get_cache

    # Seed add-2digit-carry intent directly — "73" appears in its mistake[0] description
    await client_with_fake_llm.post(
        f"/sessions/{session_id}/events",
        json={"event": {
            "kind": "coach_intent",
            "goal": "drill",
            "skill_id": "add-2digit-carry",
            "difficulty_hint": "same",
        }},
    )
    get_cache().put(session_id, "add-2digit-carry", "drill", "same", 0, "STREAMED_CACHE")

    resp = await client_with_fake_llm.post(
        f"/sessions/{session_id}/turn/stream", json={"text": "73"}
    )
    assert resp.status_code == 200
    lines = [ln for ln in resp.text.split("\n") if ln.startswith("data:")]
    events = [json.loads(ln[5:].strip()) for ln in lines]
    full_text = "".join(e["text"] for e in events if e.get("type") == "token").strip()
    assert full_text == "STREAMED_CACHE"
