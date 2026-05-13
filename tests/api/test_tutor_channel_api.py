import pytest
from httpx import AsyncClient
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.roles.identity_role import get_identity_model
from app.roles.session_role import get_session_model
from app.roles.turn_role import get_turn_model
from tests.api.helpers import make_fake_identity_model, make_fake_session_model, make_fake_turn_model


@pytest.fixture
def client_all_fakes(client: AsyncClient):
    from app.main import app
    app.dependency_overrides[get_turn_model] = lambda: make_fake_turn_model()
    app.dependency_overrides[get_session_model] = lambda: make_fake_session_model()
    app.dependency_overrides[get_identity_model] = lambda: make_fake_identity_model()
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def channel_setup(client_all_fakes: AsyncClient):
    tutor = (await client_all_fakes.post("/tutors", json={"name": "Ms. Chen"})).json()
    learner = (await client_all_fakes.post("/learners", json={"name": "Sam"})).json()
    session = (await client_all_fakes.post("/sessions", json={
        "learner_id": learner["id"], "program_id": "elementary-math",
    })).json()
    return client_all_fakes, tutor["id"], learner["id"], session["id"]


# ── Whisper tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_whisper_appended_to_transcript(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    await client.post(f"/sessions/{session_id}/whisper",
                      json={"tutor_id": tutor_id, "content": "slow down a bit"})
    session = (await client.get(f"/sessions/{session_id}")).json()
    whispers = [e for e in session["transcript"]
                if e["kind"] == "tutor_input" and e["mode"] == "whisper"]
    assert len(whispers) == 1
    assert whispers[0]["content"] == "slow down a bit"


@pytest.mark.asyncio
async def test_whisper_requires_valid_tutor(channel_setup) -> None:
    client, _, _, session_id = channel_setup
    resp = await client.post(f"/sessions/{session_id}/whisper",
                             json={"tutor_id": "no-such-tutor", "content": "hello"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_whisper_triggers_session_role_on_next_turn(channel_setup) -> None:
    from app.main import app
    call_count = {"n": 0}

    def _counting_session_model():
        call_count["n"] += 1
        return make_fake_session_model()

    app.dependency_overrides[get_session_model] = _counting_session_model

    client, tutor_id, _, session_id = channel_setup
    await client.post(f"/sessions/{session_id}/turn", json={"text": "hi"})
    count_after_first = call_count["n"]
    await client.post(f"/sessions/{session_id}/whisper",
                      json={"tutor_id": tutor_id, "content": "go easier"})
    await client.post(f"/sessions/{session_id}/turn", json={"text": "ok"})
    assert call_count["n"] > count_after_first


@pytest.mark.asyncio
async def test_whisper_content_reaches_session_role_prompt(channel_setup) -> None:
    from app.main import app
    captured = {}

    def _capturing_session_fn(messages: list, info: AgentInfo) -> ModelResponse:
        captured["instructions"] = messages[0].instructions if messages else ""
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "goal": "teach", "skill_id": "add-1digit",
            "difficulty_hint": "easier", "rationale": "tutor said so", "tone_note": None,
        })])

    def _capturing_session_model():
        return FunctionModel(_capturing_session_fn)

    app.dependency_overrides[get_session_model] = _capturing_session_model

    client, tutor_id, _, session_id = channel_setup
    await client.post(f"/sessions/{session_id}/whisper",
                      json={"tutor_id": tutor_id, "content": "UNIQUE_WHISPER_MARKER"})
    await client.post(f"/sessions/{session_id}/turn", json={"text": "hi"})
    assert "UNIQUE_WHISPER_MARKER" in captured.get("instructions", "")


# ── Steer tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_steer_injects_coach_intent(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    resp = await client.post(f"/sessions/{session_id}/steer", json={
        "tutor_id": tutor_id,
        "goal": "teach",
        "skill_id": "add-2digit-carry",
        "difficulty_hint": "easier",
        "rationale": "learner is struggling",
    })
    assert resp.status_code == 204
    session = (await client.get(f"/sessions/{session_id}")).json()
    intents = [e for e in session["transcript"] if e["kind"] == "coach_intent"]
    assert len(intents) >= 1
    last_intent = intents[-1]
    assert last_intent["goal"] == "teach"
    assert last_intent["skill_id"] == "add-2digit-carry"


@pytest.mark.asyncio
async def test_steer_skill_used_on_next_turn(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    await client.post(f"/sessions/{session_id}/steer", json={
        "tutor_id": tutor_id, "goal": "drill", "skill_id": "add-2digit-carry",
    })
    resp = await client.post(f"/sessions/{session_id}/turn", json={"text": "ready"})
    assert resp.status_code == 200
    session = (await client.get(f"/sessions/{session_id}")).json()
    intents = [e for e in session["transcript"] if e["kind"] == "coach_intent"]
    steered = [i for i in intents if "TUTOR STEER" in (i.get("rationale") or "")]
    assert len(steered) >= 1
    assert steered[0]["skill_id"] == "add-2digit-carry"


@pytest.mark.asyncio
async def test_steer_requires_valid_tutor(channel_setup) -> None:
    client, _, _, session_id = channel_setup
    resp = await client.post(f"/sessions/{session_id}/steer", json={
        "tutor_id": "no-such", "goal": "drill", "skill_id": "add-1digit",
    })
    assert resp.status_code == 404


# ── Takeover / handback / tutor-turn tests ───────────────────────────────────

@pytest.mark.asyncio
async def test_turn_rejected_during_takeover(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    await client.post(f"/sessions/{session_id}/takeover", json={"tutor_id": tutor_id})
    resp = await client.post(f"/sessions/{session_id}/turn", json={"text": "hi"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_tutor_turn_during_takeover(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    await client.post(f"/sessions/{session_id}/takeover", json={"tutor_id": tutor_id})
    resp = await client.post(f"/sessions/{session_id}/tutor-turn",
                             json={"tutor_id": tutor_id, "text": "Let me show you."})
    assert resp.status_code == 200
    assert resp.json()["utterance"] == "Let me show you."
    session = (await client.get(f"/sessions/{session_id}")).json()
    utterances = [e for e in session["transcript"] if e["kind"] == "utterance"]
    assert any(u["text"] == "Let me show you." for u in utterances)


@pytest.mark.asyncio
async def test_tutor_turn_outside_takeover_returns_409(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    resp = await client.post(f"/sessions/{session_id}/tutor-turn",
                             json={"tutor_id": tutor_id, "text": "hello"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_handback_restores_ai_turn(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    await client.post(f"/sessions/{session_id}/takeover", json={"tutor_id": tutor_id})
    await client.post(f"/sessions/{session_id}/handback", json={"tutor_id": tutor_id})
    resp = await client.post(f"/sessions/{session_id}/turn", json={"text": "back to AI"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_takeover_requires_valid_tutor(channel_setup) -> None:
    client, _, _, session_id = channel_setup
    resp = await client.post(f"/sessions/{session_id}/takeover", json={"tutor_id": "ghost"})
    assert resp.status_code == 404


# ── Annotation tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_annotation_appended_to_transcript(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    await client.post(f"/sessions/{session_id}/turn", json={"text": "5"})
    session = (await client.get(f"/sessions/{session_id}")).json()
    turn_idx = 0

    resp = await client.post(
        f"/sessions/{session_id}/turns/{turn_idx}/annotate",
        json={"tutor_id": tutor_id, "text": "Learner hesitated here"},
    )
    assert resp.status_code == 204

    session = (await client.get(f"/sessions/{session_id}")).json()
    annotations = [
        e for e in session["transcript"]
        if e["kind"] == "tutor_input" and e["mode"] == "annotation"
    ]
    assert len(annotations) == 1
    assert annotations[0]["content"] == "Learner hesitated here"
    assert annotations[0]["target_turn_idx"] == turn_idx


@pytest.mark.asyncio
async def test_annotation_out_of_range_returns_422(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    resp = await client.post(
        f"/sessions/{session_id}/turns/9999/annotate",
        json={"tutor_id": tutor_id, "text": "out of range"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_annotation_requires_valid_tutor(channel_setup) -> None:
    client, _, _, session_id = channel_setup
    resp = await client.post(
        f"/sessions/{session_id}/turns/0/annotate",
        json={"tutor_id": "ghost", "text": "who am I"},
    )
    assert resp.status_code == 404
