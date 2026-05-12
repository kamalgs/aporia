import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_skills(client: AsyncClient) -> None:
    resp = await client.get("/content/skills")
    assert resp.status_code == 200
    skills = resp.json()
    assert any(s["id"] == "add-2digit-carry" for s in skills)


@pytest.mark.asyncio
async def test_get_skill(client: AsyncClient) -> None:
    resp = await client.get("/content/skills/add-2digit-carry")
    assert resp.status_code == 200
    assert resp.json()["id"] == "add-2digit-carry"
    assert resp.json()["tags"] == ["math", "addition", "elementary"]


@pytest.mark.asyncio
async def test_get_missing_skill_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/content/skills/no-such-skill")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_programs(client: AsyncClient) -> None:
    resp = await client.get("/content/programs")
    assert resp.status_code == 200
    assert any(p["id"] == "elementary-math" for p in resp.json())


@pytest.mark.asyncio
async def test_get_coach_profile(client: AsyncClient) -> None:
    resp = await client.get("/content/coach_profiles/patient-encourager")
    assert resp.status_code == 200
    assert resp.json()["id"] == "patient-encourager"


@pytest.mark.asyncio
async def test_get_guardian_profile(client: AsyncClient) -> None:
    resp = await client.get("/content/guardian_profiles/child-7-9")
    assert resp.status_code == 200
    assert resp.json()["id"] == "child-7-9"
