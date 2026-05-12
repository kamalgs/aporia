import pytest

from app.domain.events import LearnerTextEvent, UtteranceEvent
from app.domain.learner import LearnerCreate
from app.domain.session import SessionCreate
from app.store import learners, sessions


@pytest.fixture
async def learner(db_pool: None):
    return await learners.insert(LearnerCreate(name="Tester"))


@pytest.mark.asyncio
async def test_insert_and_get_session(learner) -> None:
    created = await sessions.insert(SessionCreate(learner_id=learner.id, program_id="prog-1"))
    assert created.id
    assert created.status == "active"
    assert created.transcript == []

    fetched = await sessions.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.program_id == "prog-1"


@pytest.mark.asyncio
async def test_get_nonexistent_session_returns_none(db_pool: None) -> None:
    result = await sessions.get("no-such-session")
    assert result is None


@pytest.mark.asyncio
async def test_append_event_and_retrieve(learner) -> None:
    session = await sessions.insert(SessionCreate(learner_id=learner.id, program_id="prog-1"))

    await sessions.append_event(session.id, UtteranceEvent(text="What is 2 + 3?"))
    await sessions.append_event(session.id, LearnerTextEvent(text="5"))

    fetched = await sessions.get(session.id)
    assert len(fetched.transcript) == 2
    assert isinstance(fetched.transcript[0], UtteranceEvent)
    assert isinstance(fetched.transcript[1], LearnerTextEvent)


@pytest.mark.asyncio
async def test_end_session(learner) -> None:
    session = await sessions.insert(SessionCreate(learner_id=learner.id, program_id="prog-1"))
    ended = await sessions.end(session.id, summary_md="Good session.")

    assert ended.status == "ended"
    assert ended.ended_at is not None
    assert ended.summary_md == "Good session."
