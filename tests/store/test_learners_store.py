import pytest

from app.domain.learner import LearnerCreate
from app.store import learners


@pytest.mark.asyncio
async def test_insert_and_get_learner(db_pool: None) -> None:
    created = await learners.insert(LearnerCreate(name="Alice", cohort_tags=["adult"]))
    assert created.id
    assert created.name == "Alice"
    assert created.cohort_tags == ["adult"]

    fetched = await learners.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "Alice"
    assert fetched.cohort_tags == ["adult"]


@pytest.mark.asyncio
async def test_get_nonexistent_learner_returns_none(db_pool: None) -> None:
    result = await learners.get("does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_insert_default_fields(db_pool: None) -> None:
    created = await learners.insert(LearnerCreate(name="Bob"))
    assert created.cohort_tags == []
    assert created.portrait_md == ""
    assert created.traits == {}
    assert created.program_states == {}
