import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_learner(client: AsyncClient) -> None:
    resp = await client.post("/learners", json={"name": "Alice", "cohort_tags": ["adult"]})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Alice"
    assert body["cohort_tags"] == ["adult"]
    assert "id" in body


@pytest.mark.asyncio
async def test_get_learner(client: AsyncClient) -> None:
    created = (await client.post("/learners", json={"name": "Bob"})).json()
    resp = await client.get(f"/learners/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Bob"


@pytest.mark.asyncio
async def test_get_missing_learner_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/learners/no-such-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_learner_minimal(client: AsyncClient) -> None:
    resp = await client.post("/learners", json={"name": "Carol"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["cohort_tags"] == []
    assert body["portrait_md"] == ""
    assert body["traits"] == {}
