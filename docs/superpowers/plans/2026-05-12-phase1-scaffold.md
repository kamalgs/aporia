# Phase 1 Scaffold — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a fresh backend skeleton for the AI tutor platform with a two-table Postgres schema, typed-event transcript shape, content registry, and HTTP API for learners and sessions — all driven by blackbox functional tests.

**Architecture:** Single FastAPI service. Persistence is two Postgres tables (`learners`, `sessions`) accessed via thin SQL helpers (psycopg3, async, no ORM). Specialist-authored content (programs, skills, subject teaching guides, learner-cohort guides) is loaded from markdown files in `content/` into an in-process registry at startup. No agent reasoning yet; the API exposes the data shapes future phases will use.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, psycopg3 (async), Postgres 16 (via testcontainers for tests, local Docker for dev), pytest + pytest-asyncio + httpx for blackbox API tests, python-frontmatter for content parsing, uv for dependencies.

**Backend-first, test-driven, blackbox.** No frontend changes in this phase. Tests drive the API as an external client (`httpx.AsyncClient` against `app`), not against internal helpers.

---

## File Structure

**Delete (greenfield rebuild):**
- `app/__init__.py`, `app/agent.py`, `app/main.py`, `app/models.py`, `app/session_store.py`, `app/__pycache__/`
- `frontend/src/App.tsx` (will be rewritten in a later phase — leave file in place for now but it can be ignored)
- `test/test_api.py`, `test/test_e2e_api.py`, `test/test_eval.py` (will be rewritten against new shape)

**Create:**

```
app/
  __init__.py
  main.py                       # FastAPI app, lifespan, route wiring
  config.py                     # env-loaded settings
  api/
    __init__.py
    learners.py                 # POST/GET learners
    sessions.py                 # POST sessions, POST events, GET session
  domain/
    __init__.py
    events.py                   # typed transcript event union
    content.py                  # Program, Skill, CoachProfile, GuardianProfile models
    learner.py                  # Learner read/write models
    session.py                  # Session read/write models
  store/
    __init__.py
    db.py                       # connection pool, schema init, query helper
    learners.py                 # learner row CRUD
    sessions.py                 # session row CRUD
  content_registry/
    __init__.py
    loader.py                   # walk content/, parse frontmatter, build registry
    registry.py                 # in-process content registry singleton
content/
  programs/
    .gitkeep
  skills/
    .gitkeep
  coach_profiles/
    .gitkeep
  guardian_profiles/
    .gitkeep
schema.sql                       # DDL for learners + sessions
tests/
  conftest.py                    # postgres testcontainer, FastAPI client fixtures
  api/
    __init__.py
    test_learners_api.py
    test_sessions_api.py
  content_registry/
    __init__.py
    test_loader.py
  store/
    __init__.py
    test_learners_store.py
    test_sessions_store.py
```

**Modify:**
- `pyproject.toml` — fresh dependencies, drop unused (`gradio`, `pydantic-ai`); add psycopg, testcontainers, python-frontmatter.
- `.gitignore` — ensure `__pycache__/` and `*.pyc` ignored.

---

## Task 0: Repo cleanup and dependency reset

**Files:**
- Delete: `app/agent.py`, `app/main.py`, `app/models.py`, `app/session_store.py`, `app/__pycache__/`
- Delete: `test/test_api.py`, `test/test_e2e_api.py`, `test/test_eval.py`
- Modify: `.gitignore`
- Modify: `pyproject.toml`

- [ ] **Step 1: Delete prototype source files**

```bash
cd /home/agent/projects/tutor
git rm -r app/__pycache__/ app/agent.py app/main.py app/models.py app/session_store.py
git rm test/test_api.py test/test_e2e_api.py test/test_eval.py
rmdir test 2>/dev/null || true
```

- [ ] **Step 2: Update `.gitignore`**

Append to `.gitignore` if not already present:

```
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.coverage
```

- [ ] **Step 3: Replace `pyproject.toml` with fresh dependency set**

Overwrite `pyproject.toml`:

```toml
[project]
name = "tutor"
version = "0.2.0"
description = "AI tutor platform"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "pydantic>=2.12",
    "pydantic-settings>=2.6",
    "psycopg[binary,pool]>=3.2",
    "python-frontmatter>=1.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.28",
    "testcontainers[postgres]>=4.8",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --strict-markers"
```

- [ ] **Step 4: Refresh lockfile and install**

Run:
```bash
uv sync --extra dev
```

Expected: dependency resolution succeeds, virtual env populated.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: clear prototype source and reset dependencies for v1 scaffold"
```

---

## Task 1: Database schema and connection helper

**Files:**
- Create: `schema.sql`
- Create: `app/__init__.py`, `app/config.py`
- Create: `app/store/__init__.py`, `app/store/db.py`
- Create: `tests/__init__.py`, `tests/conftest.py`, `tests/store/__init__.py`, `tests/store/test_db.py`

- [ ] **Step 1: Write `schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS learners (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    cohort_tags     JSONB NOT NULL DEFAULT '[]'::jsonb,
    portrait_md     TEXT NOT NULL DEFAULT '',
    traits          JSONB NOT NULL DEFAULT '{}'::jsonb,
    program_states  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    learner_id      TEXT NOT NULL REFERENCES learners(id) ON DELETE CASCADE,
    program_id      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    transcript      JSONB NOT NULL DEFAULT '[]'::jsonb,
    summary_md      TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_sessions_learner ON sessions (learner_id, started_at DESC);
```

- [ ] **Step 2: Write `app/__init__.py`** (empty file)

```python
```

- [ ] **Step 3: Write `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://tutor:tutor@localhost:5432/tutor"
    content_dir: str = "content"


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Write `app/store/__init__.py`** (empty file)

```python
```

- [ ] **Step 5: Write `app/store/db.py`**

```python
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

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


async def apply_schema(schema_path: Path) -> None:
    sql = schema_path.read_text()
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql)
        await conn.commit()
```

- [ ] **Step 6: Write `tests/__init__.py`** (empty), `tests/store/__init__.py` (empty)

```python
```

- [ ] **Step 7: Write `tests/conftest.py`**

```python
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer

from app.store import db


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schema.sql"


@pytest.fixture(scope="session")
def postgres_container() -> PostgresContainer:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest_asyncio.fixture
async def database_url(postgres_container: PostgresContainer) -> str:
    raw = postgres_container.get_connection_url()
    # testcontainers returns SQLAlchemy-style URL; psycopg wants postgresql://
    return raw.replace("postgresql+psycopg2://", "postgresql://")


@pytest_asyncio.fixture
async def db_pool(database_url: str) -> AsyncIterator[None]:
    await db.init_pool(database_url)
    await db.apply_schema(SCHEMA_PATH)
    yield
    # truncate tables between tests for isolation
    async with db.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("TRUNCATE TABLE sessions, learners CASCADE;")
        await conn.commit()
    await db.close_pool()
```

- [ ] **Step 8: Write failing test `tests/store/test_db.py`**

```python
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
```

- [ ] **Step 9: Run tests, expect pass**

Run:
```bash
uv run pytest tests/store/test_db.py -v
```

Expected: both tests PASS. (Postgres testcontainer spins up; schema applies; queries succeed.)

If the first run fails because Docker isn't running, surface that explicitly — the engineer needs to start Docker before continuing.

- [ ] **Step 10: Commit**

```bash
git add schema.sql app/__init__.py app/config.py app/store/__init__.py app/store/db.py tests/__init__.py tests/conftest.py tests/store/__init__.py tests/store/test_db.py pyproject.toml
git commit -m "feat: postgres schema and async connection pool with testcontainers harness"
```

---

## Task 2: Typed transcript event union

**Files:**
- Create: `app/domain/__init__.py`, `app/domain/events.py`
- Create: `tests/domain/__init__.py`, `tests/domain/test_events.py`

- [ ] **Step 1: Create empty `app/domain/__init__.py`**

```python
```

- [ ] **Step 2: Write `app/domain/events.py`**

```python
from datetime import datetime, timezone
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _EventBase(BaseModel):
    """Common fields for every transcript event.

    Events are stored in the session transcript as a flat ordered list.
    The `kind` field discriminates the union; all other fields are open
    JSON so future event types do not require schema migration.
    """

    created_at: datetime = Field(default_factory=_now)


class LearnerTextEvent(_EventBase):
    kind: Literal["learner_text"] = "learner_text"
    text: str


class UtteranceEvent(_EventBase):
    """Something the system says to the learner."""
    kind: Literal["utterance"] = "utterance"
    text: str
    skill_id: str | None = None


class CoachIntentEvent(_EventBase):
    """Recorded planning decision from the session-level role."""
    kind: Literal["coach_intent"] = "coach_intent"
    goal: str
    skill_id: str | None = None
    difficulty_hint: str | None = None
    rationale: str = ""
    tone_note: str | None = None


class TurnSignalEvent(_EventBase):
    """Per-turn evaluation captured by the turn-level role."""
    kind: Literal["turn_signal"] = "turn_signal"
    on_target: bool
    matched_markers: list[str] = Field(default_factory=list)
    affect: dict[str, float] = Field(default_factory=dict)
    notes: str = ""


class TutorInputEvent(_EventBase):
    """A human tutor's intervention attached to the session."""
    kind: Literal["tutor_input"] = "tutor_input"
    mode: Literal["whisper", "steer", "takeover", "annotation"]
    tutor_id: str
    content: str
    target_turn_idx: int | None = None


TranscriptEvent = Annotated[
    Union[
        LearnerTextEvent,
        UtteranceEvent,
        CoachIntentEvent,
        TurnSignalEvent,
        TutorInputEvent,
    ],
    Field(discriminator="kind"),
]
```

- [ ] **Step 3: Create `tests/domain/__init__.py`** (empty)

```python
```

- [ ] **Step 4: Write failing test `tests/domain/test_events.py`**

```python
from pydantic import TypeAdapter

from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TranscriptEvent,
    TurnSignalEvent,
    TutorInputEvent,
    UtteranceEvent,
)


_adapter = TypeAdapter(TranscriptEvent)


def test_learner_text_event_roundtrip() -> None:
    event = LearnerTextEvent(text="hello")
    raw = event.model_dump()
    rebuilt = _adapter.validate_python(raw)
    assert isinstance(rebuilt, LearnerTextEvent)
    assert rebuilt.text == "hello"


def test_utterance_event_roundtrip() -> None:
    event = UtteranceEvent(text="What is 25 + 36?", skill_id="add-2digit-carry")
    rebuilt = _adapter.validate_python(event.model_dump())
    assert isinstance(rebuilt, UtteranceEvent)
    assert rebuilt.skill_id == "add-2digit-carry"


def test_coach_intent_event_roundtrip() -> None:
    event = CoachIntentEvent(
        goal="warm_up",
        skill_id="add-2digit-carry",
        difficulty_hint="easier",
        rationale="learner just got a wrong answer",
    )
    rebuilt = _adapter.validate_python(event.model_dump())
    assert isinstance(rebuilt, CoachIntentEvent)
    assert rebuilt.goal == "warm_up"


def test_turn_signal_event_roundtrip() -> None:
    event = TurnSignalEvent(
        on_target=False,
        matched_markers=["omit_carry"],
        affect={"frustration": 0.3},
        notes="repeated same mistake",
    )
    rebuilt = _adapter.validate_python(event.model_dump())
    assert isinstance(rebuilt, TurnSignalEvent)
    assert rebuilt.matched_markers == ["omit_carry"]


def test_tutor_input_event_roundtrip() -> None:
    event = TutorInputEvent(
        mode="whisper",
        tutor_id="tutor-1",
        content="she's faking confidence",
    )
    rebuilt = _adapter.validate_python(event.model_dump())
    assert isinstance(rebuilt, TutorInputEvent)
    assert rebuilt.mode == "whisper"


def test_discriminator_routes_unknown_kind_to_error() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _adapter.validate_python({"kind": "not_a_real_kind", "text": "x"})
```

- [ ] **Step 5: Run tests, expect pass**

Run:
```bash
uv run pytest tests/domain/test_events.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/domain/__init__.py app/domain/events.py tests/domain/__init__.py tests/domain/test_events.py
git commit -m "feat: typed discriminated-union transcript events"
```

---

## Task 3: Learner store

**Files:**
- Create: `app/domain/learner.py`
- Create: `app/store/learners.py`
- Create: `tests/store/test_learners_store.py`

- [ ] **Step 1: Write `app/domain/learner.py`**

```python
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Learner(BaseModel):
    id: str
    name: str
    cohort_tags: list[str] = Field(default_factory=list)
    portrait_md: str = ""
    traits: dict[str, Any] = Field(default_factory=dict)
    program_states: dict[str, dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class LearnerCreate(BaseModel):
    name: str
    cohort_tags: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Write `app/store/learners.py`**

```python
import json
import uuid

from app.domain.learner import Learner, LearnerCreate
from app.store import db


def _new_id() -> str:
    return f"lr_{uuid.uuid4().hex[:12]}"


async def insert(payload: LearnerCreate) -> Learner:
    learner_id = _new_id()
    async with db.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO learners (id, name, cohort_tags)
                VALUES (%s, %s, %s::jsonb)
                RETURNING id, name, cohort_tags, portrait_md, traits,
                          program_states, created_at, updated_at
                """,
                (learner_id, payload.name, json.dumps(payload.cohort_tags)),
            )
            row = await cur.fetchone()
        await conn.commit()
    return _row_to_learner(row)


async def get(learner_id: str) -> Learner | None:
    async with db.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, name, cohort_tags, portrait_md, traits,
                       program_states, created_at, updated_at
                FROM learners WHERE id = %s
                """,
                (learner_id,),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    return _row_to_learner(row)


def _row_to_learner(row: tuple) -> Learner:
    return Learner(
        id=row[0],
        name=row[1],
        cohort_tags=row[2],
        portrait_md=row[3],
        traits=row[4],
        program_states=row[5],
        created_at=row[6],
        updated_at=row[7],
    )
```

- [ ] **Step 3: Write failing test `tests/store/test_learners_store.py`**

```python
import pytest

from app.domain.learner import LearnerCreate
from app.store import learners


@pytest.mark.asyncio
async def test_insert_returns_learner_with_generated_id(db_pool: None) -> None:
    created = await learners.insert(LearnerCreate(name="Asha", cohort_tags=["child_7_9"]))
    assert created.id.startswith("lr_")
    assert created.name == "Asha"
    assert created.cohort_tags == ["child_7_9"]
    assert created.portrait_md == ""
    assert created.traits == {}
    assert created.program_states == {}


@pytest.mark.asyncio
async def test_get_after_insert_returns_same_learner(db_pool: None) -> None:
    created = await learners.insert(LearnerCreate(name="Asha"))
    fetched = await learners.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "Asha"


@pytest.mark.asyncio
async def test_get_unknown_id_returns_none(db_pool: None) -> None:
    fetched = await learners.get("lr_does_not_exist")
    assert fetched is None
```

- [ ] **Step 4: Run tests, expect pass**

Run:
```bash
uv run pytest tests/store/test_learners_store.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/domain/learner.py app/store/learners.py tests/store/test_learners_store.py
git commit -m "feat: learner store (insert, get) with blackbox tests"
```

---

## Task 4: Session store

**Files:**
- Create: `app/domain/session.py`
- Create: `app/store/sessions.py`
- Create: `tests/store/test_sessions_store.py`

- [ ] **Step 1: Write `app/domain/session.py`**

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.events import TranscriptEvent


SessionStatus = Literal["active", "ended"]


class Session(BaseModel):
    id: str
    learner_id: str
    program_id: str
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None
    transcript: list[TranscriptEvent] = Field(default_factory=list)
    summary_md: str = ""


class SessionCreate(BaseModel):
    learner_id: str
    program_id: str
```

- [ ] **Step 2: Write `app/store/sessions.py`**

```python
import json
import uuid
from datetime import datetime, timezone

from pydantic import TypeAdapter

from app.domain.events import TranscriptEvent
from app.domain.session import Session, SessionCreate
from app.store import db


_transcript_adapter = TypeAdapter(list[TranscriptEvent])


def _new_id() -> str:
    return f"se_{uuid.uuid4().hex[:12]}"


async def insert(payload: SessionCreate) -> Session:
    session_id = _new_id()
    async with db.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO sessions (id, learner_id, program_id)
                VALUES (%s, %s, %s)
                RETURNING id, learner_id, program_id, status, started_at,
                          ended_at, transcript, summary_md
                """,
                (session_id, payload.learner_id, payload.program_id),
            )
            row = await cur.fetchone()
        await conn.commit()
    return _row_to_session(row)


async def get(session_id: str) -> Session | None:
    async with db.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, learner_id, program_id, status, started_at,
                       ended_at, transcript, summary_md
                FROM sessions WHERE id = %s
                """,
                (session_id,),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    return _row_to_session(row)


async def append_event(session_id: str, event: TranscriptEvent) -> Session:
    """Append a transcript event atomically using JSONB concatenation."""
    event_json = json.dumps(event.model_dump(mode="json"))
    async with db.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE sessions
                SET transcript = transcript || %s::jsonb
                WHERE id = %s
                RETURNING id, learner_id, program_id, status, started_at,
                          ended_at, transcript, summary_md
                """,
                (event_json, session_id),
            )
            row = await cur.fetchone()
        await conn.commit()
    if row is None:
        raise KeyError(f"session {session_id} not found")
    return _row_to_session(row)


async def end(session_id: str, summary_md: str = "") -> Session:
    ended_at = datetime.now(timezone.utc)
    async with db.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE sessions
                SET status = 'ended', ended_at = %s, summary_md = %s
                WHERE id = %s
                RETURNING id, learner_id, program_id, status, started_at,
                          ended_at, transcript, summary_md
                """,
                (ended_at, summary_md, session_id),
            )
            row = await cur.fetchone()
        await conn.commit()
    if row is None:
        raise KeyError(f"session {session_id} not found")
    return _row_to_session(row)


def _row_to_session(row: tuple) -> Session:
    return Session(
        id=row[0],
        learner_id=row[1],
        program_id=row[2],
        status=row[3],
        started_at=row[4],
        ended_at=row[5],
        transcript=_transcript_adapter.validate_python(row[6]),
        summary_md=row[7],
    )
```

- [ ] **Step 3: Write failing test `tests/store/test_sessions_store.py`**

```python
import pytest

from app.domain.events import LearnerTextEvent, UtteranceEvent
from app.domain.learner import LearnerCreate
from app.domain.session import SessionCreate
from app.store import learners, sessions


@pytest.mark.asyncio
async def test_insert_session_starts_active_with_empty_transcript(db_pool: None) -> None:
    learner = await learners.insert(LearnerCreate(name="Asha"))
    created = await sessions.insert(
        SessionCreate(learner_id=learner.id, program_id="math-2digit")
    )
    assert created.id.startswith("se_")
    assert created.learner_id == learner.id
    assert created.program_id == "math-2digit"
    assert created.status == "active"
    assert created.ended_at is None
    assert created.transcript == []


@pytest.mark.asyncio
async def test_append_event_grows_transcript_in_order(db_pool: None) -> None:
    learner = await learners.insert(LearnerCreate(name="Asha"))
    session = await sessions.insert(
        SessionCreate(learner_id=learner.id, program_id="math-2digit")
    )
    after_first = await sessions.append_event(
        session.id, UtteranceEvent(text="What is 25 + 36?")
    )
    assert len(after_first.transcript) == 1
    after_second = await sessions.append_event(
        session.id, LearnerTextEvent(text="51")
    )
    assert len(after_second.transcript) == 2
    assert after_second.transcript[0].kind == "utterance"
    assert after_second.transcript[1].kind == "learner_text"


@pytest.mark.asyncio
async def test_end_marks_session_ended(db_pool: None) -> None:
    learner = await learners.insert(LearnerCreate(name="Asha"))
    session = await sessions.insert(
        SessionCreate(learner_id=learner.id, program_id="math-2digit")
    )
    ended = await sessions.end(session.id, summary_md="learner did great")
    assert ended.status == "ended"
    assert ended.ended_at is not None
    assert ended.summary_md == "learner did great"


@pytest.mark.asyncio
async def test_get_unknown_session_returns_none(db_pool: None) -> None:
    fetched = await sessions.get("se_does_not_exist")
    assert fetched is None


@pytest.mark.asyncio
async def test_append_to_unknown_session_raises(db_pool: None) -> None:
    with pytest.raises(KeyError):
        await sessions.append_event("se_nope", LearnerTextEvent(text="x"))
```

- [ ] **Step 4: Run tests, expect pass**

Run:
```bash
uv run pytest tests/store/test_sessions_store.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/domain/session.py app/store/sessions.py tests/store/test_sessions_store.py
git commit -m "feat: session store with append_event and end"
```

---

## Task 5: FastAPI application skeleton

**Files:**
- Create: `app/main.py`
- Create: `app/api/__init__.py`

- [ ] **Step 1: Create empty `app/api/__init__.py`**

```python
```

- [ ] **Step 2: Write `app/main.py`**

```python
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.config import get_settings
from app.store import db


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schema.sql"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await db.init_pool(settings.database_url)
    await db.apply_schema(SCHEMA_PATH)
    try:
        yield
    finally:
        await db.close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="AI Tutor Platform", version="0.2.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    from app.api import learners as learners_routes
    from app.api import sessions as sessions_routes

    app.include_router(learners_routes.router)
    app.include_router(sessions_routes.router)

    return app


app = create_app()
```

(Routers don't exist yet — the next two tasks add them. This step doesn't run on its own; we will defer testing the app until after Task 7.)

- [ ] **Step 3: No commit yet** — the app won't import until routers exist. Move to Task 6.

---

## Task 6: Learners API

**Files:**
- Create: `app/api/learners.py`
- Create: `tests/api/__init__.py`, `tests/api/test_learners_api.py`

- [ ] **Step 1: Write `app/api/learners.py`**

```python
from fastapi import APIRouter, HTTPException, status

from app.domain.learner import Learner, LearnerCreate
from app.store import learners as learners_store


router = APIRouter(prefix="/learners", tags=["learners"])


@router.post("", response_model=Learner, status_code=status.HTTP_201_CREATED)
async def create_learner(payload: LearnerCreate) -> Learner:
    return await learners_store.insert(payload)


@router.get("/{learner_id}", response_model=Learner)
async def get_learner(learner_id: str) -> Learner:
    learner = await learners_store.get(learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail=f"learner {learner_id} not found")
    return learner
```

- [ ] **Step 2: Create `tests/api/__init__.py`** (empty)

```python
```

- [ ] **Step 3: Extend `tests/conftest.py` with an HTTP client fixture**

Add at the bottom of `tests/conftest.py`:

```python
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest_asyncio.fixture
async def client(db_pool: None) -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

Note: the existing `db_pool` fixture initialises the pool and applies schema; the client fixture reuses it so the app's lifespan does not double-init. The app's `lifespan` will still try to init — but `init_pool` is idempotent (returns the existing pool). Verify this; if it isn't, adjust `init_pool` to be idempotent.

Update `app/store/db.py:init_pool` if not already idempotent (it is, per the `if _pool is None` guard).

- [ ] **Step 4: Write failing test `tests/api/test_learners_api.py`**

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_learner_returns_201_with_generated_id(client: AsyncClient) -> None:
    response = await client.post("/learners", json={"name": "Asha", "cohort_tags": ["child_7_9"]})
    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("lr_")
    assert body["name"] == "Asha"
    assert body["cohort_tags"] == ["child_7_9"]
    assert body["portrait_md"] == ""


@pytest.mark.asyncio
async def test_create_learner_minimal_payload(client: AsyncClient) -> None:
    response = await client.post("/learners", json={"name": "Sam"})
    assert response.status_code == 201
    body = response.json()
    assert body["cohort_tags"] == []


@pytest.mark.asyncio
async def test_get_learner_returns_404_when_missing(client: AsyncClient) -> None:
    response = await client.get("/learners/lr_nope")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_learner_after_create(client: AsyncClient) -> None:
    created = (await client.post("/learners", json={"name": "Asha"})).json()
    fetched = await client.get(f"/learners/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]
    assert fetched.json()["name"] == "Asha"
```

- [ ] **Step 5: Run tests, expect pass**

Run:
```bash
uv run pytest tests/api/test_learners_api.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/api/__init__.py app/api/learners.py tests/api/__init__.py tests/api/test_learners_api.py tests/conftest.py
git commit -m "feat: learners API (POST, GET) with blackbox HTTP tests"
```

---

## Task 7: Sessions API

**Files:**
- Create: `app/api/sessions.py`
- Create: `tests/api/test_sessions_api.py`

- [ ] **Step 1: Write `app/api/sessions.py`**

```python
from fastapi import APIRouter, Body, HTTPException, status
from pydantic import TypeAdapter

from app.domain.events import TranscriptEvent
from app.domain.session import Session, SessionCreate
from app.store import learners as learners_store
from app.store import sessions as sessions_store


router = APIRouter(prefix="/sessions", tags=["sessions"])


_event_adapter = TypeAdapter(TranscriptEvent)


@router.post("", response_model=Session, status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreate) -> Session:
    learner = await learners_store.get(payload.learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail=f"learner {payload.learner_id} not found")
    return await sessions_store.insert(payload)


@router.get("/{session_id}", response_model=Session)
async def get_session(session_id: str) -> Session:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    return session


@router.post("/{session_id}/events", response_model=Session)
async def append_event(session_id: str, event_payload: dict = Body(...)) -> Session:
    try:
        event = _event_adapter.validate_python(event_payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    try:
        return await sessions_store.append_event(session_id, event)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")


@router.post("/{session_id}/end", response_model=Session)
async def end_session(session_id: str, summary_md: str = Body("", embed=True)) -> Session:
    try:
        return await sessions_store.end(session_id, summary_md=summary_md)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
```

- [ ] **Step 2: Write failing test `tests/api/test_sessions_api.py`**

```python
import pytest
from httpx import AsyncClient


async def _make_learner(client: AsyncClient, name: str = "Asha") -> str:
    return (await client.post("/learners", json={"name": name})).json()["id"]


@pytest.mark.asyncio
async def test_create_session_for_existing_learner(client: AsyncClient) -> None:
    learner_id = await _make_learner(client)
    response = await client.post(
        "/sessions", json={"learner_id": learner_id, "program_id": "math-2digit"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("se_")
    assert body["status"] == "active"
    assert body["transcript"] == []


@pytest.mark.asyncio
async def test_create_session_for_unknown_learner_404(client: AsyncClient) -> None:
    response = await client.post(
        "/sessions", json={"learner_id": "lr_nope", "program_id": "math-2digit"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_append_events_and_read_back(client: AsyncClient) -> None:
    learner_id = await _make_learner(client)
    session = (await client.post(
        "/sessions", json={"learner_id": learner_id, "program_id": "math-2digit"}
    )).json()
    sid = session["id"]

    r1 = await client.post(
        f"/sessions/{sid}/events",
        json={"kind": "utterance", "text": "What is 25 + 36?"},
    )
    assert r1.status_code == 200
    assert len(r1.json()["transcript"]) == 1

    r2 = await client.post(
        f"/sessions/{sid}/events",
        json={"kind": "learner_text", "text": "51"},
    )
    assert r2.status_code == 200
    transcript = r2.json()["transcript"]
    assert len(transcript) == 2
    assert transcript[0]["kind"] == "utterance"
    assert transcript[1]["kind"] == "learner_text"


@pytest.mark.asyncio
async def test_append_event_rejects_unknown_kind(client: AsyncClient) -> None:
    learner_id = await _make_learner(client)
    sid = (await client.post(
        "/sessions", json={"learner_id": learner_id, "program_id": "math-2digit"}
    )).json()["id"]
    response = await client.post(
        f"/sessions/{sid}/events", json={"kind": "garbage", "text": "x"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_end_session_marks_status(client: AsyncClient) -> None:
    learner_id = await _make_learner(client)
    sid = (await client.post(
        "/sessions", json={"learner_id": learner_id, "program_id": "math-2digit"}
    )).json()["id"]
    response = await client.post(
        f"/sessions/{sid}/end", json={"summary_md": "great session"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ended"
    assert body["summary_md"] == "great session"


@pytest.mark.asyncio
async def test_get_session_returns_404_when_missing(client: AsyncClient) -> None:
    response = await client.get("/sessions/se_nope")
    assert response.status_code == 404
```

- [ ] **Step 3: Run tests, expect pass**

Run:
```bash
uv run pytest tests/api/test_sessions_api.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add app/api/sessions.py tests/api/test_sessions_api.py
git commit -m "feat: sessions API (create, append events, end, get) with blackbox HTTP tests"
```

---

## Task 8: Content domain types

**Files:**
- Create: `app/domain/content.py`
- Create: `tests/domain/test_content.py`

- [ ] **Step 1: Write `app/domain/content.py`**

```python
from typing import Literal

from pydantic import BaseModel, Field


ContentKind = Literal["program", "skill", "coach_profile", "guardian_profile"]


class ContentArtifact(BaseModel):
    """Base for everything specialists author.

    `body_md` is the full prose of the document. `frontmatter` carries the
    light structured fields (id, name, tags, references). Specific kinds
    expose their own typed views over the same data, but every artifact
    keeps the raw body so an LLM or human reader can consume it directly.
    """

    id: str
    kind: ContentKind
    name: str
    tags: list[str] = Field(default_factory=list)
    body_md: str
    source_path: str  # relative path under content/


class Program(ContentArtifact):
    kind: Literal["program"] = "program"
    skill_ids: list[str] = Field(default_factory=list)
    mandatory_skill_ids: list[str] = Field(default_factory=list)
    coach_profile_id: str | None = None


class Skill(ContentArtifact):
    kind: Literal["skill"] = "skill"
    topic_tags: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=lambda: ["socratic"])


class CoachProfile(ContentArtifact):
    kind: Literal["coach_profile"] = "coach_profile"
    subject: str | None = None


class GuardianProfile(ContentArtifact):
    kind: Literal["guardian_profile"] = "guardian_profile"
    cohort: str | None = None
```

- [ ] **Step 2: Write test `tests/domain/test_content.py`**

```python
from app.domain.content import CoachProfile, GuardianProfile, Program, Skill


def test_program_has_skill_membership_fields() -> None:
    p = Program(
        id="math-2digit",
        name="Two-Digit Addition with Carrying",
        body_md="program prose...",
        source_path="programs/math-2digit.md",
        skill_ids=["s1", "s2", "s3"],
        mandatory_skill_ids=["s1", "s2"],
        coach_profile_id="math_elementary",
    )
    assert p.kind == "program"
    assert p.mandatory_skill_ids == ["s1", "s2"]
    assert "s3" in p.skill_ids


def test_skill_default_format_is_socratic() -> None:
    s = Skill(id="s1", name="Add two ones with sum >= 10", body_md="...", source_path="skills/s1.md")
    assert s.formats == ["socratic"]


def test_coach_and_guardian_profile_carry_subject_and_cohort() -> None:
    c = CoachProfile(
        id="math_elementary",
        name="Elementary Math Teaching Guide",
        body_md="...",
        source_path="coach_profiles/math_elementary.md",
        subject="math",
    )
    g = GuardianProfile(
        id="child_7_9",
        name="Working with 7-9 year olds",
        body_md="...",
        source_path="guardian_profiles/child_7_9.md",
        cohort="child_7_9",
    )
    assert c.subject == "math"
    assert g.cohort == "child_7_9"
```

- [ ] **Step 3: Run tests, expect pass**

Run:
```bash
uv run pytest tests/domain/test_content.py -v
```

Expected: 3 PASS.

- [ ] **Step 4: Commit**

```bash
git add app/domain/content.py tests/domain/test_content.py
git commit -m "feat: content domain types (Program, Skill, CoachProfile, GuardianProfile)"
```

---

## Task 9: Content registry — loader and in-process registry

**Files:**
- Create: `app/content_registry/__init__.py`, `app/content_registry/loader.py`, `app/content_registry/registry.py`
- Create: `tests/content_registry/__init__.py`, `tests/content_registry/test_loader.py`

- [ ] **Step 1: Create empty `app/content_registry/__init__.py`**

```python
```

- [ ] **Step 2: Write `app/content_registry/loader.py`**

```python
from pathlib import Path

import frontmatter

from app.domain.content import (
    CoachProfile,
    ContentArtifact,
    GuardianProfile,
    Program,
    Skill,
)


_KIND_DIR = {
    "program": "programs",
    "skill": "skills",
    "coach_profile": "coach_profiles",
    "guardian_profile": "guardian_profiles",
}

_KIND_TO_CLASS: dict[str, type[ContentArtifact]] = {
    "program": Program,
    "skill": Skill,
    "coach_profile": CoachProfile,
    "guardian_profile": GuardianProfile,
}


def load_all(content_dir: Path) -> list[ContentArtifact]:
    artifacts: list[ContentArtifact] = []
    for kind, subdir in _KIND_DIR.items():
        dir_path = content_dir / subdir
        if not dir_path.exists():
            continue
        for path in sorted(dir_path.glob("*.md")):
            artifacts.append(_load_one(kind, path, content_dir))
    return artifacts


def _load_one(kind: str, path: Path, content_dir: Path) -> ContentArtifact:
    post = frontmatter.load(path)
    meta = dict(post.metadata)
    if "id" not in meta:
        raise ValueError(f"{path}: frontmatter missing required field 'id'")
    if "name" not in meta:
        raise ValueError(f"{path}: frontmatter missing required field 'name'")
    payload = {
        **meta,
        "kind": kind,
        "body_md": post.content,
        "source_path": str(path.relative_to(content_dir)),
    }
    cls = _KIND_TO_CLASS[kind]
    return cls.model_validate(payload)
```

- [ ] **Step 3: Write `app/content_registry/registry.py`**

```python
from pathlib import Path

from app.content_registry.loader import load_all
from app.domain.content import (
    CoachProfile,
    ContentArtifact,
    GuardianProfile,
    Program,
    Skill,
)


class ContentRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, ContentArtifact] = {}

    def load(self, content_dir: Path) -> None:
        self._by_id.clear()
        for artifact in load_all(content_dir):
            key = f"{artifact.kind}:{artifact.id}"
            if key in self._by_id:
                raise ValueError(f"duplicate content id: {key}")
            self._by_id[key] = artifact

    def get(self, kind: str, artifact_id: str) -> ContentArtifact | None:
        return self._by_id.get(f"{kind}:{artifact_id}")

    def program(self, program_id: str) -> Program | None:
        artifact = self.get("program", program_id)
        return artifact if isinstance(artifact, Program) else None

    def skill(self, skill_id: str) -> Skill | None:
        artifact = self.get("skill", skill_id)
        return artifact if isinstance(artifact, Skill) else None

    def coach_profile(self, profile_id: str) -> CoachProfile | None:
        artifact = self.get("coach_profile", profile_id)
        return artifact if isinstance(artifact, CoachProfile) else None

    def guardian_profile(self, profile_id: str) -> GuardianProfile | None:
        artifact = self.get("guardian_profile", profile_id)
        return artifact if isinstance(artifact, GuardianProfile) else None

    def all_of_kind(self, kind: str) -> list[ContentArtifact]:
        return [a for k, a in self._by_id.items() if k.startswith(f"{kind}:")]


_registry = ContentRegistry()


def registry() -> ContentRegistry:
    return _registry
```

- [ ] **Step 4: Create test directory plus a tiny fixture content tree**

Create empty `tests/content_registry/__init__.py`:

```python
```

- [ ] **Step 5: Write failing test `tests/content_registry/test_loader.py`**

```python
from pathlib import Path

import pytest

from app.content_registry.loader import load_all
from app.content_registry.registry import ContentRegistry
from app.domain.content import Program, Skill


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_loads_program_and_skill_from_markdown(tmp_path: Path) -> None:
    _write(
        tmp_path / "programs" / "math-2digit.md",
        """---
id: math-2digit
name: Two-Digit Addition with Carrying
skill_ids: [add-ones, add-2digit-carry]
mandatory_skill_ids: [add-2digit-carry]
coach_profile_id: math_elementary
tags: [math, arithmetic]
---
Program prose goes here.
""",
    )
    _write(
        tmp_path / "skills" / "add-2digit-carry.md",
        """---
id: add-2digit-carry
name: Adding two 2-digit numbers with a carry
topic_tags: [math, addition]
formats: [socratic, drill]
---
Skill brief goes here.
""",
    )

    artifacts = load_all(tmp_path)
    by_id = {(a.kind, a.id): a for a in artifacts}

    program = by_id[("program", "math-2digit")]
    assert isinstance(program, Program)
    assert program.skill_ids == ["add-ones", "add-2digit-carry"]
    assert program.mandatory_skill_ids == ["add-2digit-carry"]
    assert "Program prose" in program.body_md

    skill = by_id[("skill", "add-2digit-carry")]
    assert isinstance(skill, Skill)
    assert skill.formats == ["socratic", "drill"]


def test_loader_raises_on_missing_required_frontmatter(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "broken.md",
        "---\nname: missing-id\n---\nbody\n",
    )
    with pytest.raises(ValueError, match="missing required field 'id'"):
        load_all(tmp_path)


def test_registry_round_trips_via_load(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "s.md",
        "---\nid: s\nname: A Skill\n---\nbody\n",
    )
    _write(
        tmp_path / "coach_profiles" / "cp.md",
        "---\nid: cp\nname: A Coach Profile\nsubject: math\n---\nbody\n",
    )
    reg = ContentRegistry()
    reg.load(tmp_path)
    assert reg.skill("s") is not None
    assert reg.coach_profile("cp") is not None
    assert reg.skill("does-not-exist") is None


def test_registry_rejects_duplicate_ids(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "a.md",
        "---\nid: dup\nname: A\n---\n",
    )
    _write(
        tmp_path / "skills" / "b.md",
        "---\nid: dup\nname: B\n---\n",
    )
    reg = ContentRegistry()
    with pytest.raises(ValueError, match="duplicate content id"):
        reg.load(tmp_path)
```

- [ ] **Step 6: Run tests, expect pass**

Run:
```bash
uv run pytest tests/content_registry/test_loader.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/content_registry/ tests/content_registry/
git commit -m "feat: content registry that loads markdown artifacts with frontmatter"
```

---

## Task 10: Wire the content registry into app startup, expose a read endpoint

**Files:**
- Create: `content/programs/.gitkeep`, `content/skills/.gitkeep`, `content/coach_profiles/.gitkeep`, `content/guardian_profiles/.gitkeep`
- Modify: `app/main.py`
- Create: `app/api/content.py`
- Create: `tests/api/test_content_api.py`

- [ ] **Step 1: Create empty content directories**

```bash
mkdir -p content/programs content/skills content/coach_profiles content/guardian_profiles
touch content/programs/.gitkeep content/skills/.gitkeep content/coach_profiles/.gitkeep content/guardian_profiles/.gitkeep
```

- [ ] **Step 2: Modify `app/main.py` — load registry in lifespan, register content router**

Replace `app/main.py` with:

```python
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.config import get_settings
from app.content_registry.registry import registry
from app.store import db


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schema.sql"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await db.init_pool(settings.database_url)
    await db.apply_schema(SCHEMA_PATH)
    registry().load(Path(settings.content_dir))
    try:
        yield
    finally:
        await db.close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="AI Tutor Platform", version="0.2.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    from app.api import content as content_routes
    from app.api import learners as learners_routes
    from app.api import sessions as sessions_routes

    app.include_router(learners_routes.router)
    app.include_router(sessions_routes.router)
    app.include_router(content_routes.router)

    return app


app = create_app()
```

- [ ] **Step 3: Write `app/api/content.py`**

```python
from fastapi import APIRouter, HTTPException

from app.content_registry.registry import registry
from app.domain.content import ContentArtifact


router = APIRouter(prefix="/content", tags=["content"])


@router.get("/{kind}")
async def list_kind(kind: str) -> list[ContentArtifact]:
    if kind not in {"program", "skill", "coach_profile", "guardian_profile"}:
        raise HTTPException(status_code=404, detail=f"unknown kind: {kind}")
    return registry().all_of_kind(kind)


@router.get("/{kind}/{artifact_id}")
async def get_one(kind: str, artifact_id: str) -> ContentArtifact:
    artifact = registry().get(kind, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"{kind}:{artifact_id} not found")
    return artifact
```

- [ ] **Step 4: Reload registry from a test-controlled directory in tests**

Update `tests/conftest.py` — replace the `client` fixture so the registry loads a per-test temp content tree:

```python
@pytest_asyncio.fixture
async def client(db_pool: None, tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[AsyncClient]:
    from app.content_registry.registry import registry
    from app.config import Settings
    import app.config as config_module

    content_dir = tmp_path_factory.mktemp("content")
    for sub in ("programs", "skills", "coach_profiles", "guardian_profiles"):
        (content_dir / sub).mkdir()

    def _override_settings() -> Settings:
        return Settings(database_url=Settings().database_url, content_dir=str(content_dir))

    original = config_module.get_settings
    config_module.get_settings = _override_settings
    registry().load(content_dir)

    app = create_app()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        config_module.get_settings = original
```

Note: this overrides `get_settings` so the app's lifespan uses the temp content dir but still uses the testcontainer DB URL.

- [ ] **Step 5: Write failing test `tests/api/test_content_api.py`**

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_content_empty(client: AsyncClient) -> None:
    response = await client.get("/content/program")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_content_unknown_kind_404(client: AsyncClient) -> None:
    response = await client.get("/content/not_a_real_kind")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_unknown_artifact_404(client: AsyncClient) -> None:
    response = await client.get("/content/program/missing")
    assert response.status_code == 404
```

- [ ] **Step 6: Run tests, expect pass**

Run:
```bash
uv run pytest tests/api/test_content_api.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add content/ app/main.py app/api/content.py tests/api/test_content_api.py tests/conftest.py
git commit -m "feat: content registry loaded at startup with /content read API"
```

---

## Task 11: End-to-end smoke test and final scaffold cleanup

**Files:**
- Create: `tests/test_end_to_end_smoke.py`
- Modify: `README.md`

- [ ] **Step 1: Write `tests/test_end_to_end_smoke.py`**

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_full_phase1_round_trip(client: AsyncClient) -> None:
    """End-to-end: create learner -> create session -> append events -> end session -> read back."""
    learner = (await client.post("/learners", json={"name": "Asha", "cohort_tags": ["child_7_9"]})).json()
    session = (await client.post(
        "/sessions", json={"learner_id": learner["id"], "program_id": "math-2digit"}
    )).json()
    sid = session["id"]

    await client.post(
        f"/sessions/{sid}/events",
        json={"kind": "coach_intent", "goal": "warm_up", "rationale": "starting cold"},
    )
    await client.post(
        f"/sessions/{sid}/events",
        json={"kind": "utterance", "text": "What is 25 + 36?", "skill_id": "add-2digit-carry"},
    )
    await client.post(
        f"/sessions/{sid}/events",
        json={"kind": "learner_text", "text": "51"},
    )
    await client.post(
        f"/sessions/{sid}/events",
        json={
            "kind": "turn_signal",
            "on_target": False,
            "matched_markers": ["omit_carry"],
            "affect": {"frustration": 0.2},
        },
    )
    ended = (await client.post(f"/sessions/{sid}/end", json={"summary_md": "first sitting"})).json()
    assert ended["status"] == "ended"
    assert len(ended["transcript"]) == 4

    fetched = (await client.get(f"/sessions/{sid}")).json()
    kinds = [event["kind"] for event in fetched["transcript"]]
    assert kinds == ["coach_intent", "utterance", "learner_text", "turn_signal"]
    assert fetched["summary_md"] == "first sitting"
```

- [ ] **Step 2: Run full test suite**

Run:
```bash
uv run pytest -v
```

Expected: every test passes. Total count: well into the thirties. Run time is dominated by the testcontainer Postgres spin-up; tests themselves are fast.

- [ ] **Step 3: Replace README.md content**

Overwrite `README.md`:

```markdown
# AI Tutor Platform

A subject-agnostic AI tutor framework. Specialists author content (programs, skills, teaching guides) as markdown; the framework runs the coaching relationship.

**Status:** v1 in progress. See `docs/superpowers/specs/2026-05-12-tutoring-platform-design.md` for the design and `docs/superpowers/plans/` for phased implementation plans.

## Local development

Requires Python 3.12, Docker (for Postgres), and [uv](https://github.com/astral-sh/uv).

Install dependencies:

    uv sync --extra dev

Start Postgres for development:

    docker run -d --name tutor-pg \
      -e POSTGRES_USER=tutor -e POSTGRES_PASSWORD=tutor -e POSTGRES_DB=tutor \
      -p 5432:5432 postgres:16-alpine

Run the API:

    uv run uvicorn app.main:app --reload

Run tests (spawns a throwaway Postgres testcontainer):

    uv run pytest

## Layout

- `app/` — backend service (FastAPI)
- `content/` — specialist-authored programs, skills, coach profiles, guardian profiles
- `docs/superpowers/` — design spec and implementation plans
- `tests/` — blackbox functional tests

## Phases

This repo follows phased implementation. Each phase lands as commits on a single working branch and is merged when complete.

- Phase 1 — scaffold (schema, event-typed transcript, content registry, API) ← *current*
- Phase 2 — turn-level role + first skill
- Phase 3 — session-level role + program + subject teaching guide
- Phase 4 — identity role + learner portrait + cohort guide
- Phase 5 — human tutor channel
- Phase 6 — responsiveness (small/fast model + speculative branches + streaming)
- Phase 7 — frontend rewrite
- Phase 8 — second subject as smoke test
```

- [ ] **Step 4: Final commit**

```bash
git add tests/test_end_to_end_smoke.py README.md
git commit -m "feat: phase 1 end-to-end smoke test and updated README"
```

- [ ] **Step 5: Push the branch**

```bash
git push
```

---

## Phase 1 done — definition of done

- All tests in `tests/` pass against a real Postgres (via testcontainers).
- API supports: create/get learner, create/get session, append events, end session, list/read content artifacts.
- Typed event union enforced at the transcript boundary: unknown event kinds are rejected with 422.
- Content registry loads markdown artifacts at startup, exposes typed lookups, rejects duplicate ids.
- No agent reasoning, no LLM calls, no frontend changes.
- README documents local development and the phased roadmap.

## What this phase deliberately omits

These are not gaps; they are scoped to later phases.

- Turn-level role and Tactician prompts (Phase 2).
- Coach planning and Intent contract (Phase 3).
- Guardian and durable learner portrait (Phase 4).
- Human tutor channel and event stream (Phase 5).
- Speculation, streaming, fast-model routing (Phase 6).
- Frontend (Phase 7).
- Real specialist content (added per phase as needed).
