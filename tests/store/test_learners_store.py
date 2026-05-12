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


@pytest.mark.asyncio
async def test_update_program_state(db_pool: None) -> None:
    learner = await learners.insert(LearnerCreate(name="Alice"))
    updated = await learners.update_program_state(
        learner.id,
        program_id="prog-1",
        skill_id="skill-a",
        skill_state={"attempt_count": 1, "correct_count": 1},
    )
    assert updated.program_states["prog-1"]["skill-a"]["attempt_count"] == 1


@pytest.mark.asyncio
async def test_update_program_state_merges_skills(db_pool: None) -> None:
    learner = await learners.insert(LearnerCreate(name="Bob"))
    await learners.update_program_state(
        learner.id, "prog-1", skill_id="skill-a", skill_state={"attempt_count": 1}
    )
    updated = await learners.update_program_state(
        learner.id, "prog-1", skill_id="skill-b", skill_state={"attempt_count": 2}
    )
    assert "skill-a" in updated.program_states["prog-1"]
    assert "skill-b" in updated.program_states["prog-1"]


@pytest.mark.asyncio
async def test_update_portrait(db_pool: None) -> None:
    learner = await learners.insert(LearnerCreate(name="Alice"))
    updated = await learners.update_portrait(learner.id, "Alice is a quick learner.")
    assert updated.portrait_md == "Alice is a quick learner."


@pytest.mark.asyncio
async def test_update_portrait_overwrites_previous(db_pool: None) -> None:
    learner = await learners.insert(LearnerCreate(name="Bob"))
    await learners.update_portrait(learner.id, "First portrait.")
    updated = await learners.update_portrait(learner.id, "Updated portrait.")
    assert updated.portrait_md == "Updated portrait."
