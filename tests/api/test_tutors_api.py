import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_get_tutor(client: AsyncClient) -> None:
    resp = await client.post("/tutors", json={"name": "Ms. Chen"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Ms. Chen"
    assert "id" in body

    fetched = (await client.get(f"/tutors/{body['id']}")).json()
    assert fetched["name"] == "Ms. Chen"
    assert fetched["id"] == body["id"]


@pytest.mark.asyncio
async def test_get_nonexistent_tutor_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/tutors/no-such-id")
    assert resp.status_code == 404
