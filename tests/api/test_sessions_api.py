import pytest
from httpx import AsyncClient


@pytest.fixture
async def learner_id(client: AsyncClient) -> str:
    resp = await client.post("/learners", json={"name": "Tester"})
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_session(client: AsyncClient, learner_id: str) -> None:
    resp = await client.post("/sessions", json={"learner_id": learner_id, "program_id": "prog-1"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "active"
    assert body["transcript"] == []


@pytest.mark.asyncio
async def test_get_session(client: AsyncClient, learner_id: str) -> None:
    created = (await client.post("/sessions", json={"learner_id": learner_id, "program_id": "prog-1"})).json()
    resp = await client.get(f"/sessions/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


@pytest.mark.asyncio
async def test_get_missing_session_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/sessions/no-such-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_append_event_and_retrieve(client: AsyncClient, learner_id: str) -> None:
    session = (await client.post("/sessions", json={"learner_id": learner_id, "program_id": "prog-1"})).json()
    sid = session["id"]

    r1 = await client.post(f"/sessions/{sid}/events", json={"event": {"kind": "utterance", "text": "What is 2+3?"}})
    assert r1.status_code == 204

    r2 = await client.post(f"/sessions/{sid}/events", json={"event": {"kind": "learner_text", "text": "5"}})
    assert r2.status_code == 204

    fetched = (await client.get(f"/sessions/{sid}")).json()
    assert len(fetched["transcript"]) == 2
    assert fetched["transcript"][0]["kind"] == "utterance"
    assert fetched["transcript"][1]["kind"] == "learner_text"


@pytest.mark.asyncio
async def test_end_session(client: AsyncClient, learner_id: str) -> None:
    session = (await client.post("/sessions", json={"learner_id": learner_id, "program_id": "prog-1"})).json()
    sid = session["id"]

    resp = await client.post(f"/sessions/{sid}/end", json={"summary_md": "Good work!"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ended"
    assert body["summary_md"] == "Good work!"
    assert body["ended_at"] is not None


@pytest.mark.asyncio
async def test_append_event_to_missing_session_returns_404(client: AsyncClient) -> None:
    resp = await client.post("/sessions/no-such/events", json={"event": {"kind": "learner_text", "text": "hi"}})
    assert resp.status_code == 404
