import pytest

from app.store import db


@pytest.mark.asyncio
async def test_pool_provides_working_connection(db_pool: None) -> None:
    async with db.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1")
            row = await cur.fetchone()
    assert row == (1,)


@pytest.mark.asyncio
async def test_schema_creates_learners_and_sessions(db_pool: None) -> None:
    async with db.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name;"
            )
            rows = await cur.fetchall()
    table_names = [r[0] for r in rows]
    assert "learners" in table_names
    assert "sessions" in table_names
