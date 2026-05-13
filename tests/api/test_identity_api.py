from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.roles.identity_role import get_identity_llm_client
from app.roles.session_role import get_session_llm_client
from app.roles.turn_role import get_turn_model


def _fake_turn_llm():
    def _fn(messages: list, info: AgentInfo) -> ModelResponse:
        tool_name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name, {
            "utterance": "Good work!",
            "on_target": True,
            "matched_markers": [],
            "affect": {},
            "notes": "",
        })])
    return FunctionModel(_fn)


def _fake_session_llm():
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(
                type="tool_use",
                input={"goal": "warm_up", "skill_id": "add-1digit",
                       "difficulty_hint": "same", "rationale": "start"},
            )])
    class _FakeLLM:
        messages = _FakeMessages()
    return _FakeLLM()


def _fake_identity_llm(portrait: str = "Alice is a promising young mathematician."):
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(
                type="tool_use",
                input={"portrait_md": portrait},
            )])
    class _FakeLLM:
        messages = _FakeMessages()
    return _FakeLLM()


@pytest.fixture
def client_with_all_fakes(client: AsyncClient):
    from app.main import app
    app.dependency_overrides[get_turn_model] = _fake_turn_llm
    app.dependency_overrides[get_session_llm_client] = _fake_session_llm
    app.dependency_overrides[get_identity_llm_client] = _fake_identity_llm
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def learner_and_session(client_with_all_fakes: AsyncClient):
    learner = (await client_with_all_fakes.post("/learners", json={"name": "Alice", "cohort_tags": ["child"]})).json()
    session = (await client_with_all_fakes.post("/sessions", json={
        "learner_id": learner["id"],
        "program_id": "elementary-math",
    })).json()
    return client_with_all_fakes, learner["id"], session["id"]


@pytest.mark.asyncio
async def test_end_session_updates_learner_portrait(learner_and_session) -> None:
    client, learner_id, session_id = learner_and_session
    await client.post(f"/sessions/{session_id}/turn", json={"text": "7"})
    resp = await client.post(f"/sessions/{session_id}/end", json={"summary_md": "Good first session."})
    assert resp.status_code == 200
    learner = (await client.get(f"/learners/{learner_id}")).json()
    assert learner["portrait_md"] == "Alice is a promising young mathematician."


@pytest.mark.asyncio
async def test_end_session_with_no_turns_still_updates_portrait(learner_and_session) -> None:
    client, learner_id, session_id = learner_and_session
    resp = await client.post(f"/sessions/{session_id}/end", json={})
    assert resp.status_code == 200
    learner = (await client.get(f"/learners/{learner_id}")).json()
    assert learner["portrait_md"]


@pytest.mark.asyncio
async def test_end_session_status_becomes_ended(learner_and_session) -> None:
    client, learner_id, session_id = learner_and_session
    resp = await client.post(f"/sessions/{session_id}/end", json={})
    assert resp.json()["status"] == "ended"


@pytest.mark.asyncio
async def test_end_session_uses_prior_portrait(learner_and_session) -> None:
    """When a learner already has a portrait, the identity role receives it as prior_portrait."""
    from app.main import app
    received_prior = {}

    def _capturing_identity_llm():
        class _FakeMessages:
            def create(self, **kwargs):
                received_prior["system"] = kwargs.get("system", "")
                return SimpleNamespace(content=[SimpleNamespace(
                    type="tool_use", input={"portrait_md": "Updated portrait."},
                )])
        class _FakeLLM:
            messages = _FakeMessages()
        return _FakeLLM()

    app.dependency_overrides[get_identity_llm_client] = _capturing_identity_llm

    client, learner_id, session_id = learner_and_session
    await client.post(f"/sessions/{session_id}/end", json={})

    session2 = (await client.post("/sessions", json={
        "learner_id": learner_id, "program_id": "elementary-math",
    })).json()
    await client.post(f"/sessions/{session2['id']}/end", json={})

    assert "PRIOR PORTRAIT" in received_prior.get("system", "")
