from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from testcontainers.postgres import PostgresContainer

from app.store import db


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    raw = postgres_container.get_connection_url()
    return raw.replace("postgresql+psycopg2://", "postgresql://")


@pytest_asyncio.fixture
async def db_pool(database_url: str) -> AsyncIterator[None]:
    db.run_migrations(database_url)
    await db.init_pool(database_url)
    yield
    async with db.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("TRUNCATE TABLE sessions, learners CASCADE;")
        await conn.commit()
    await db.close_pool()


@pytest_asyncio.fixture
async def client(db_pool: None) -> AsyncIterator[AsyncClient]:
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
