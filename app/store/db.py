from contextlib import asynccontextmanager
from typing import AsyncIterator

from alembic import command
from alembic.config import Config
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool


_pool: AsyncConnectionPool | None = None


async def init_pool(database_url: str) -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(database_url, open=False, min_size=1, max_size=8)
        await _pool.open()
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised; call init_pool() first")
    return _pool


@asynccontextmanager
async def connection() -> AsyncIterator[AsyncConnection]:
    async with pool().connection() as conn:
        yield conn


def run_migrations(database_url: str) -> None:
    """Apply all pending Alembic migrations synchronously."""
    # psycopg3 sync dialect: postgresql+psycopg://
    sync_url = database_url.replace("postgresql://", "postgresql+psycopg://")
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(cfg, "head")
