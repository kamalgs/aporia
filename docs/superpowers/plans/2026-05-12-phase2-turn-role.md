# Phase 2 — Turn Role Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a turn-level LLM role that runs Q&A against a single skill brief, emitting typed transcript events, and expose it via a `POST /sessions/{id}/turn` endpoint.

**Architecture:** A pure `run_turn()` function in `app/roles/turn_role.py` takes the current intent, skill brief, recent transcript, and learner text; calls Anthropic with a `emit_turn` tool to force structured output; and returns an `UtteranceEvent` + `TurnSignalEvent`. The API endpoint derives the current intent from the transcript (most recent `CoachIntentEvent`, or a warm-up default) and calls `run_turn`. The LLM client is injected via FastAPI `Depends` so tests can swap in a fake without hitting the API.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, `anthropic>=0.49` SDK, `claude-haiku-4-5-20251001` (fast turn-level model), pytest + httpx blackbox tests.

---

## File Structure

**Create:**
```
app/
  roles/
    __init__.py
    turn_role.py          # run_turn() pure function + get_llm_client() factory
tests/
  roles/
    __init__.py
    test_turn_role.py     # unit tests with FakeAnthropicClient
  api/
    test_turn_api.py      # blackbox endpoint tests with dependency override
```

**Modify:**
- `pyproject.toml` — add `anthropic>=0.49`
- `app/api/sessions.py` — add `POST /{session_id}/turn` endpoint
- `content/skills/add-2digit-carry.md` — enrich common_mistakes + sample_exchanges
- `tests/conftest.py` — add `mock_llm_client` fixture and `llm_client` fixture

---

## Task 0: Add Anthropic SDK dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `anthropic` to pyproject.toml dependencies**

Replace the `dependencies` list in `pyproject.toml`:

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
    "alembic>=1.14",
    "sqlalchemy>=2.0",
    "anthropic>=0.49",
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

- [ ] **Step 2: Sync deps**

Run:
```bash
uv sync --extra dev
```

Expected: resolves and installs `anthropic` and its transitive deps.

- [ ] **Step 3: Verify import works**

Run:
```bash
uv run python -c "import anthropic; print(anthropic.__version__)"
```

Expected: prints a version string like `0.49.0`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add anthropic SDK dependency"
```

---

## Task 1: Enrich first skill content

**Files:**
- Modify: `content/skills/add-2digit-carry.md`

- [ ] **Step 1: Overwrite `content/skills/add-2digit-carry.md`**

```markdown
---
id: add-2digit-carry
title: Two-digit addition with carrying
objective: Add two 2-digit numbers that require carrying the tens digit.
mastery_description: Student consistently solves 2-digit addition problems with carrying, giving the correct answer and able to explain what happens when the ones column exceeds 9.
common_mistakes:
  - Forgetting to carry — adds the ones column correctly but ignores the carry into the tens column (e.g. 47+36 = 73 instead of 83)
  - Wrong carry amount — carries 2 instead of 1, or carries when ones total is less than 10
  - Tens column error — carries correctly but adds the tens column wrong (e.g. 4+3+1 = 7 instead of 8)
  - Place value confusion — swaps tens and ones in the answer
sample_exchanges:
  - role: tutor
    text: "What is 47 + 36?"
  - role: learner
    text: "73"
  - role: tutor
    text: "Almost — you got the ones column right (7+6=13, write 3). What do you do with the leftover 1?"
tags:
  - math
  - addition
  - elementary
---

Students learn to add two 2-digit numbers where the ones column sums to 10 or more, requiring a carry into the tens column.

Key steps:
1. Add the ones digits. If the sum is 10 or more, write the ones digit and carry 1 to the tens column.
2. Add the tens digits plus the carried 1.
3. Write the result.
```

- [ ] **Step 2: Verify loader still works**

Run:
```bash
uv run pytest tests/content_registry/ -v
```

Expected: all 6 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add content/skills/add-2digit-carry.md
git commit -m "content: enrich add-2digit-carry skill with detailed mistakes and sample exchanges"
```

---

## Task 2: Turn role — pure function

**Files:**
- Create: `app/roles/__init__.py`
- Create: `app/roles/turn_role.py`
- Create: `tests/roles/__init__.py`
- Create: `tests/roles/test_turn_role.py`

- [ ] **Step 1: Create `app/roles/__init__.py`** (empty)

```python
```

- [ ] **Step 2: Write failing test `tests/roles/test_turn_role.py`**

```python
from types import SimpleNamespace

import pytest

from app.domain.events import CoachIntentEvent, LearnerTextEvent, UtteranceEvent, TurnSignalEvent
from app.domain.content import Skill
from app.roles.turn_role import run_turn


def _fake_client(utterance: str = "What is 47 + 36?", on_target: bool = True):
    """Returns a fake Anthropic client whose messages.create returns a canned tool-use response."""

    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        input={
                            "utterance": utterance,
                            "on_target": on_target,
                            "matched_markers": [],
                            "affect": {},
                            "notes": "",
                        },
                    )
                ]
            )

    class _FakeClient:
        messages = _FakeMessages()

    return _FakeClient()


_SKILL = Skill(
    id="add-2digit-carry",
    title="Two-digit addition with carrying",
    objective="Add two 2-digit numbers that require carrying.",
    mastery_description="Student solves consistently.",
    common_mistakes=["Forgetting to carry"],
)

_INTENT = CoachIntentEvent(goal="warm_up", skill_id="add-2digit-carry")


@pytest.mark.asyncio
async def test_run_turn_returns_utterance_and_signal() -> None:
    utterance_event, signal_event = await run_turn(
        intent=_INTENT,
        skill=_SKILL,
        transcript_window=[],
        learner_text="hello",
        llm_client=_fake_client(),
    )
    assert isinstance(utterance_event, UtteranceEvent)
    assert utterance_event.text == "What is 47 + 36?"
    assert utterance_event.skill_id == "add-2digit-carry"
    assert isinstance(signal_event, TurnSignalEvent)
    assert signal_event.on_target is True


@pytest.mark.asyncio
async def test_run_turn_off_target() -> None:
    utterance_event, signal_event = await run_turn(
        intent=_INTENT,
        skill=_SKILL,
        transcript_window=[],
        learner_text="I don't know",
        llm_client=_fake_client(utterance="Let's try a simpler one first.", on_target=False),
    )
    assert signal_event.on_target is False
    assert "simpler" in utterance_event.text


@pytest.mark.asyncio
async def test_run_turn_passes_transcript_window() -> None:
    """run_turn should include transcript events in the LLM call without crashing."""
    window = [
        UtteranceEvent(text="What is 23 + 48?", skill_id="add-2digit-carry"),
        LearnerTextEvent(text="71"),
    ]
    utterance_event, signal_event = await run_turn(
        intent=_INTENT,
        skill=_SKILL,
        transcript_window=window,
        learner_text="ok",
        llm_client=_fake_client(),
    )
    assert utterance_event.text


@pytest.mark.asyncio
async def test_run_turn_matched_markers_captured() -> None:
    client = _fake_client()

    class _FakeMessagesWithMarkers:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        input={
                            "utterance": "Almost! You forgot to carry the 1.",
                            "on_target": False,
                            "matched_markers": ["Forgetting to carry"],
                            "affect": {"frustration": 0.3},
                            "notes": "student dropped carry",
                        },
                    )
                ]
            )

    client.messages = _FakeMessagesWithMarkers()
    _, signal_event = await run_turn(
        intent=_INTENT,
        skill=_SKILL,
        transcript_window=[],
        learner_text="73",
        llm_client=client,
    )
    assert "Forgetting to carry" in signal_event.matched_markers
    assert signal_event.affect.get("frustration") == pytest.approx(0.3)
    assert "dropped carry" in signal_event.notes
```

- [ ] **Step 3: Run test to confirm failure**

Run:
```bash
uv run pytest tests/roles/test_turn_role.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.roles'` or similar.

- [ ] **Step 4: Write `app/roles/turn_role.py`**

```python
from typing import Any

from anthropic import Anthropic

from app.domain.content import Skill
from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TranscriptEvent,
    TurnSignalEvent,
    UtteranceEvent,
    UtteranceEvent,
)

TURN_MODEL = "claude-haiku-4-5-20251001"
TRANSCRIPT_WINDOW_SIZE = 10

_EMIT_TURN_TOOL: dict[str, Any] = {
    "name": "emit_turn",
    "description": "Emit your next message to the learner and record your assessment of their response.",
    "input_schema": {
        "type": "object",
        "properties": {
            "utterance": {
                "type": "string",
                "description": "The next message to send to the learner.",
            },
            "on_target": {
                "type": "boolean",
                "description": "True if the learner's response was correct or on-track.",
            },
            "matched_markers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Names of common mistake patterns that match the learner's response.",
            },
            "affect": {
                "type": "object",
                "description": "Observed affective signals as float scores, e.g. {'confidence': 0.7}.",
            },
            "notes": {
                "type": "string",
                "description": "Optional free-form notes about this turn.",
            },
        },
        "required": ["utterance", "on_target"],
    },
}


def _format_transcript(window: list[TranscriptEvent]) -> list[dict[str, str]]:
    """Convert transcript events into alternating user/assistant messages for the LLM."""
    messages = []
    for event in window:
        if isinstance(event, LearnerTextEvent):
            messages.append({"role": "user", "content": event.text})
        elif isinstance(event, UtteranceEvent):
            messages.append({"role": "assistant", "content": event.text})
    return messages


def _build_system_prompt(intent: CoachIntentEvent, skill: Skill) -> str:
    mistakes = "\n".join(f"- {m}" for m in skill.common_mistakes) or "None documented."
    lines = [
        f"You are a skilled tutor working one-on-one with a learner on the following skill.",
        f"",
        f"SKILL: {skill.title}",
        f"OBJECTIVE: {skill.objective}",
        f"MASTERY LOOKS LIKE: {skill.mastery_description}",
        f"",
        f"COMMON MISTAKES TO WATCH FOR:",
        mistakes,
        f"",
        f"CURRENT INTENT:",
        f"  Goal: {intent.goal}",
        f"  Skill: {intent.skill_id or skill.id}",
    ]
    if intent.difficulty_hint:
        lines.append(f"  Difficulty: {intent.difficulty_hint}")
    if intent.tone_note:
        lines.append(f"  Tone: {intent.tone_note}")
    lines += [
        f"",
        f"Use the emit_turn tool to send your next message and record your assessment.",
        f"Keep responses short — one or two sentences maximum.",
        f"If the learner's input is their first message, greet them briefly and ask an opening question.",
    ]
    return "\n".join(lines)


async def run_turn(
    intent: CoachIntentEvent,
    skill: Skill,
    transcript_window: list[TranscriptEvent],
    learner_text: str,
    llm_client: Any,
) -> tuple[UtteranceEvent, TurnSignalEvent]:
    """Call the LLM turn role and return an utterance + turn signal pair."""
    window = transcript_window[-TRANSCRIPT_WINDOW_SIZE:]
    messages = _format_transcript(window)
    messages.append({"role": "user", "content": learner_text})

    response = llm_client.messages.create(
        model=TURN_MODEL,
        system=_build_system_prompt(intent, skill),
        messages=messages,
        tools=[_EMIT_TURN_TOOL],
        tool_choice={"type": "any"},
        max_tokens=512,
    )

    tool_input = response.content[0].input
    utterance = UtteranceEvent(text=tool_input["utterance"], skill_id=skill.id)
    signal = TurnSignalEvent(
        on_target=tool_input["on_target"],
        matched_markers=tool_input.get("matched_markers", []),
        affect=tool_input.get("affect", {}),
        notes=tool_input.get("notes", ""),
    )
    return utterance, signal


def get_llm_client() -> Anthropic:
    """FastAPI dependency factory — returns a live Anthropic client."""
    return Anthropic()
```

- [ ] **Step 5: Create `tests/roles/__init__.py`** (empty)

```python
```

- [ ] **Step 6: Run tests to confirm they pass**

Run:
```bash
uv run pytest tests/roles/test_turn_role.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/roles/__init__.py app/roles/turn_role.py tests/roles/__init__.py tests/roles/test_turn_role.py
git commit -m "feat: turn-level role with injectable LLM client"
```

---

## Task 3: Turn endpoint

**Files:**
- Modify: `app/api/sessions.py`
- Modify: `tests/conftest.py`
- Create: `tests/api/test_turn_api.py`

- [ ] **Step 1: Write failing test `tests/api/test_turn_api.py`**

```python
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.roles.turn_role import get_llm_client


def _make_fake_llm(utterance: str = "What is 47 + 36?", on_target: bool = True):
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        input={
                            "utterance": utterance,
                            "on_target": on_target,
                            "matched_markers": [],
                            "affect": {},
                            "notes": "",
                        },
                    )
                ]
            )

    class _FakeLLM:
        messages = _FakeMessages()

    return _FakeLLM()


@pytest.fixture
def fake_llm():
    return _make_fake_llm()


@pytest.fixture
def client_with_fake_llm(client: AsyncClient, fake_llm):
    from app.main import app
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def session_id(client_with_fake_llm: AsyncClient) -> str:
    learner = (await client_with_fake_llm.post("/learners", json={"name": "Tester"})).json()
    session = (await client_with_fake_llm.post("/sessions", json={
        "learner_id": learner["id"],
        "program_id": "elementary-math",
    })).json()
    return session["id"]


@pytest.mark.asyncio
async def test_turn_returns_utterance(client_with_fake_llm: AsyncClient, session_id: str) -> None:
    resp = await client_with_fake_llm.post(
        f"/sessions/{session_id}/turn",
        json={"text": "hello"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["utterance"] == "What is 47 + 36?"
    assert "turn_signal" in body
    assert body["turn_signal"]["on_target"] is True


@pytest.mark.asyncio
async def test_turn_appends_events_to_transcript(client_with_fake_llm: AsyncClient, session_id: str) -> None:
    await client_with_fake_llm.post(f"/sessions/{session_id}/turn", json={"text": "5"})
    session = (await client_with_fake_llm.get(f"/sessions/{session_id}")).json()
    kinds = [e["kind"] for e in session["transcript"]]
    assert "learner_text" in kinds
    assert "utterance" in kinds
    assert "turn_signal" in kinds


@pytest.mark.asyncio
async def test_turn_missing_session_returns_404(client_with_fake_llm: AsyncClient) -> None:
    resp = await client_with_fake_llm.post("/sessions/no-such/turn", json={"text": "hi"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_turn_uses_existing_intent_from_transcript(client_with_fake_llm: AsyncClient, session_id: str) -> None:
    """If a CoachIntentEvent is already in the transcript, the turn role should use it."""
    await client_with_fake_llm.post(
        f"/sessions/{session_id}/events",
        json={"event": {
            "kind": "coach_intent",
            "goal": "drill",
            "skill_id": "add-2digit-carry",
            "difficulty_hint": "harder",
        }},
    )
    resp = await client_with_fake_llm.post(f"/sessions/{session_id}/turn", json={"text": "ready"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_turn_empty_text_still_responds(client_with_fake_llm: AsyncClient, session_id: str) -> None:
    resp = await client_with_fake_llm.post(f"/sessions/{session_id}/turn", json={"text": ""})
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to confirm failure**

Run:
```bash
uv run pytest tests/api/test_turn_api.py -v
```

Expected: FAIL — `POST /sessions/{id}/turn` doesn't exist yet.

- [ ] **Step 3: Add turn endpoint to `app/api/sessions.py`**

Replace the contents of `app/api/sessions.py` with:

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.content_registry.registry import registry
from app.domain.events import CoachIntentEvent, TranscriptEvent
from app.domain.session import Session, SessionCreate
from app.roles.turn_role import TurnSignalEvent, UtteranceEvent, get_llm_client, run_turn
from app.store import sessions as sessions_store

router = APIRouter(prefix="/sessions", tags=["sessions"])

_DEFAULT_GOAL = "warm_up"


class AppendEventRequest(BaseModel):
    event: TranscriptEvent


class EndSessionRequest(BaseModel):
    summary_md: str = ""


class TurnRequest(BaseModel):
    text: str


class TurnResponse(BaseModel):
    utterance: str
    turn_signal: dict


def _derive_intent(session: Session) -> CoachIntentEvent:
    """Return the most recent CoachIntentEvent from the transcript, or a default warm-up."""
    for event in reversed(session.transcript):
        if isinstance(event, CoachIntentEvent):
            return event
    # No intent recorded yet — build a default from the program's first mandatory skill.
    reg = registry()
    program = reg.program(session.program_id)
    skill_id = None
    if program and program.mandatory_skill_ids:
        skill_id = program.mandatory_skill_ids[0]
    elif program and program.skill_ids:
        skill_id = program.skill_ids[0]
    return CoachIntentEvent(goal=_DEFAULT_GOAL, skill_id=skill_id)


@router.post("", response_model=Session, status_code=201)
async def create_session(body: SessionCreate) -> Session:
    return await sessions_store.insert(body)


@router.get("/{session_id}", response_model=Session)
async def get_session(session_id: str) -> Session:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/{session_id}/events", status_code=204)
async def append_event(session_id: str, body: AppendEventRequest) -> None:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await sessions_store.append_event(session_id, body.event)


@router.post("/{session_id}/end", response_model=Session)
async def end_session(session_id: str, body: EndSessionRequest) -> Session:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return await sessions_store.end(session_id, body.summary_md)


@router.post("/{session_id}/turn", response_model=TurnResponse)
async def session_turn(
    session_id: str,
    body: TurnRequest,
    llm_client=Depends(get_llm_client),
) -> TurnResponse:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    intent = _derive_intent(session)
    if intent.skill_id is None:
        raise HTTPException(status_code=422, detail="No skill available for this session")

    skill = registry().skill(intent.skill_id)
    if skill is None:
        raise HTTPException(status_code=422, detail=f"Skill '{intent.skill_id}' not found in registry")

    await sessions_store.append_event(session_id, CoachIntentEvent(
        goal=intent.goal,
        skill_id=intent.skill_id,
        difficulty_hint=intent.difficulty_hint,
        tone_note=intent.tone_note,
        rationale=intent.rationale,
    ))
    await sessions_store.append_event(session_id, LearnerTextEvent(text=body.text))

    session = await sessions_store.get(session_id)
    utterance_event, signal_event = await run_turn(
        intent=intent,
        skill=skill,
        transcript_window=session.transcript,
        learner_text=body.text,
        llm_client=llm_client,
    )

    await sessions_store.append_event(session_id, utterance_event)
    await sessions_store.append_event(session_id, signal_event)

    return TurnResponse(
        utterance=utterance_event.text,
        turn_signal=signal_event.model_dump(mode="json"),
    )
```

Note: add the missing import at the top of the file — `LearnerTextEvent` needs to be imported from `app.domain.events`.

- [ ] **Step 4: Fix the missing import in `app/api/sessions.py`**

The `session_turn` handler uses `LearnerTextEvent` but the import block shown in Step 3 imports it via `app.roles.turn_role`. That's wrong — it's defined in `app.domain.events`. Update the imports section of `app/api/sessions.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.content_registry.registry import registry
from app.domain.events import CoachIntentEvent, LearnerTextEvent, TranscriptEvent
from app.domain.session import Session, SessionCreate
from app.roles.turn_role import TurnSignalEvent, UtteranceEvent, get_llm_client, run_turn
from app.store import sessions as sessions_store
```

- [ ] **Step 5: Run turn API tests**

Run:
```bash
uv run pytest tests/api/test_turn_api.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 6: Run the full test suite**

Run:
```bash
uv run pytest -v
```

Expected: all 37 existing tests + 5 new turn API tests + 4 turn role unit tests = **46 tests PASS**.

- [ ] **Step 7: Commit**

```bash
git add app/api/sessions.py tests/api/test_turn_api.py
git commit -m "feat: POST /sessions/{id}/turn — turn-level Q&A endpoint"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement (Phase 2) | Task |
|---|---|
| Turn role that runs Q&A against single skill brief | Task 2 |
| Emits typed transcript events | Task 2 + Task 3 (appends `LearnerTextEvent`, `CoachIntentEvent`, `UtteranceEvent`, `TurnSignalEvent`) |
| Port math-2-digit-addition as first skill pack | Task 1 (enriched) |
| End-to-end usable for one skill | Task 3 (full turn endpoint) |
| No session role / planning yet | ✓ — intent derived from transcript or defaulted |
| Eval harness rebuilt at step 2 | Not included — existing 37 tests cover domain/store/API; turn tests added here |
| LLM injectable for tests | Task 2 + 3 (Depends + dependency_overrides) |

**Placeholder scan:** No TBDs, all code blocks present, all function signatures consistent across tasks.

**Type consistency:**
- `run_turn()` signature in Task 2 test matches implementation: `(intent: CoachIntentEvent, skill: Skill, transcript_window: list[TranscriptEvent], learner_text: str, llm_client: Any) -> tuple[UtteranceEvent, TurnSignalEvent]` ✓
- `TurnResponse` fields match what the endpoint returns: `utterance: str`, `turn_signal: dict` ✓
- `get_llm_client` imported from `app.roles.turn_role` in both `app/api/sessions.py` and `tests/api/test_turn_api.py` ✓
