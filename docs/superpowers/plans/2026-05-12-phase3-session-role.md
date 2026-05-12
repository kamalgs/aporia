# Phase 3 — Session Role Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the session-level planning role that produces `CoachIntent` at session start and on threshold triggers (mastery / repeated failure), with a deterministic state updater that tracks per-skill progress in the learner record.

**Architecture:** Three new pure modules: `state_updater.py` (deterministic signal→state fold, no LLM), `trigger_policy.py` (stateless check of transcript + program state), `session_role.py` (LLM call with `set_intent` tool, injectable client). The `/turn` endpoint gains a pre-turn check: if the trigger policy fires it runs the session role first, appends a `CoachIntentEvent`, then proceeds with the turn role as before. After each turn, it folds the signal into the learner's `program_states` in Postgres via a new `update_program_state()` store function.

**Tech Stack:** Same as Phase 2. Session role uses `claude-sonnet-4-6` (more capable, runs rarely). All new logic covered by blackbox functional tests with fake LLM clients.

---

## File Structure

**Create:**
```
app/roles/
  state_updater.py          # deterministic TurnSignalEvent → program_state fold
  trigger_policy.py         # should_run_session_role(transcript, program_state) → bool
  session_role.py           # run_session() LLM call + get_session_llm_client() factory
content/
  skills/
    add-1digit.md           # second skill for skill-switching tests
tests/roles/
  test_state_updater.py
  test_trigger_policy.py
  test_session_role.py
tests/api/
  test_session_planning_api.py   # integration tests: session role fires, skill switches
```

**Modify:**
```
app/store/learners.py        # add update_program_state()
app/api/sessions.py          # wire state updater + trigger policy + session role into /turn
content/programs/elementary-math.md  # add add-1digit skill
tests/store/test_learners_store.py   # add test for update_program_state
tests/conftest.py            # add fake_session_llm fixture, update client_with_fake_llm
```

---

## Task 0: Second skill + update program

**Files:**
- Create: `content/skills/add-1digit.md`
- Modify: `content/programs/elementary-math.md`

- [ ] **Step 1: Write `content/skills/add-1digit.md`**

```markdown
---
id: add-1digit
title: Single-digit addition
objective: Add two single-digit numbers (1–9) to get a result up to 18.
mastery_description: Student answers single-digit addition problems quickly and accurately without counting on fingers.
common_mistakes:
  - Off-by-one — miscounts and gives an answer 1 too high or too low
  - Reversal — swaps addends mentally and arrives at the right answer but shows shaky understanding
tags:
  - math
  - addition
  - elementary
---

Foundation for all addition: knowing single-digit sums from memory.
```

- [ ] **Step 2: Update `content/programs/elementary-math.md`**

```markdown
---
id: elementary-math
title: Elementary Math
description: Foundational arithmetic skills for young learners.
skill_ids:
  - add-1digit
  - add-2digit-carry
mandatory_skill_ids:
  - add-1digit
  - add-2digit-carry
assessment_criteria: Student can solve both single-digit and two-digit addition problems reliably. For two-digit problems with carrying, can explain the carry step.
coach_profile_id: patient-encourager
---

A gentle introduction to arithmetic operations with a focus on building number sense.
```

- [ ] **Step 3: Verify content tests pass**

Run:
```bash
uv run pytest tests/content_registry/ -v
```

Expected: 6 PASS (the loader tests use a tmp_path fixture with a fresh skill — not the actual content directory — so no changes needed there).

- [ ] **Step 4: Commit**

```bash
git add content/
git commit -m "content: add single-digit addition skill and expand elementary-math program"
```

---

## Task 1: Deterministic state updater

**Files:**
- Create: `app/roles/state_updater.py`
- Create: `tests/roles/test_state_updater.py`

- [ ] **Step 1: Write failing test `tests/roles/test_state_updater.py`**

```python
from app.domain.events import TurnSignalEvent
from app.roles.state_updater import apply_turn_signal


def _signal(on_target: bool, markers: list[str] | None = None) -> TurnSignalEvent:
    return TurnSignalEvent(on_target=on_target, matched_markers=markers or [])


def test_first_correct_turn_initialises_state() -> None:
    result = apply_turn_signal({}, "skill-a", _signal(on_target=True))
    assert result["skill-a"]["attempt_count"] == 1
    assert result["skill-a"]["correct_count"] == 1
    assert result["skill-a"]["consecutive_correct"] == 1
    assert result["skill-a"]["consecutive_incorrect"] == 0


def test_consecutive_correct_increments() -> None:
    state = {}
    state = apply_turn_signal(state, "skill-a", _signal(True))
    state = apply_turn_signal(state, "skill-a", _signal(True))
    assert state["skill-a"]["consecutive_correct"] == 2


def test_incorrect_resets_consecutive_correct() -> None:
    state = apply_turn_signal({}, "skill-a", _signal(True))
    state = apply_turn_signal(state, "skill-a", _signal(True))
    state = apply_turn_signal(state, "skill-a", _signal(False))
    assert state["skill-a"]["consecutive_correct"] == 0
    assert state["skill-a"]["consecutive_incorrect"] == 1


def test_correct_resets_consecutive_incorrect() -> None:
    state = apply_turn_signal({}, "skill-a", _signal(False))
    state = apply_turn_signal(state, "skill-a", _signal(False))
    state = apply_turn_signal(state, "skill-a", _signal(True))
    assert state["skill-a"]["consecutive_incorrect"] == 0
    assert state["skill-a"]["consecutive_correct"] == 1


def test_matched_markers_accumulate() -> None:
    state = apply_turn_signal({}, "skill-a", _signal(False, ["Forgetting to carry"]))
    state = apply_turn_signal(state, "skill-a", _signal(False, ["Forgetting to carry"]))
    assert state["skill-a"]["matched_markers"]["Forgetting to carry"] == 2


def test_does_not_mutate_input() -> None:
    original = {}
    result = apply_turn_signal(original, "skill-a", _signal(True))
    assert original == {}
    assert result != original


def test_multiple_skills_are_independent() -> None:
    state = apply_turn_signal({}, "skill-a", _signal(True))
    state = apply_turn_signal(state, "skill-b", _signal(False))
    assert state["skill-a"]["correct_count"] == 1
    assert state["skill-b"]["consecutive_incorrect"] == 1
    assert "skill-a" not in state.get("skill-b", {})
```

- [ ] **Step 2: Run to confirm failure**

Run:
```bash
uv run pytest tests/roles/test_state_updater.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.roles.state_updater'`.

- [ ] **Step 3: Write `app/roles/state_updater.py`**

```python
from app.domain.events import TurnSignalEvent


def apply_turn_signal(program_state: dict, skill_id: str, signal: TurnSignalEvent) -> dict:
    """Fold a TurnSignalEvent into program_state for the given skill. Returns a new dict."""
    existing = program_state.get(skill_id, {})
    skill_state = {
        "attempt_count": existing.get("attempt_count", 0) + 1,
        "correct_count": existing.get("correct_count", 0),
        "consecutive_correct": existing.get("consecutive_correct", 0),
        "consecutive_incorrect": existing.get("consecutive_incorrect", 0),
        "matched_markers": dict(existing.get("matched_markers", {})),
    }
    if signal.on_target:
        skill_state["correct_count"] += 1
        skill_state["consecutive_correct"] += 1
        skill_state["consecutive_incorrect"] = 0
    else:
        skill_state["consecutive_correct"] = 0
        skill_state["consecutive_incorrect"] += 1
        for marker in signal.matched_markers:
            skill_state["matched_markers"][marker] = (
                skill_state["matched_markers"].get(marker, 0) + 1
            )
    return {**program_state, skill_id: skill_state}
```

- [ ] **Step 4: Run tests**

Run:
```bash
uv run pytest tests/roles/test_state_updater.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/roles/state_updater.py tests/roles/test_state_updater.py
git commit -m "feat: deterministic turn-signal state updater"
```

---

## Task 2: Trigger policy

**Files:**
- Create: `app/roles/trigger_policy.py`
- Create: `tests/roles/test_trigger_policy.py`

- [ ] **Step 1: Write failing test `tests/roles/test_trigger_policy.py`**

```python
from app.domain.events import CoachIntentEvent, TurnSignalEvent, UtteranceEvent
from app.roles.trigger_policy import MASTERY_THRESHOLD, should_run_session_role


def _intent() -> CoachIntentEvent:
    return CoachIntentEvent(goal="warm_up", skill_id="s1")


def _signal(on_target: bool) -> TurnSignalEvent:
    return TurnSignalEvent(on_target=on_target)


def test_empty_transcript_triggers() -> None:
    assert should_run_session_role([], {}) is True


def test_transcript_with_only_non_intent_events_triggers() -> None:
    assert should_run_session_role([_signal(True)], {}) is True


def test_intent_present_and_few_signals_does_not_trigger() -> None:
    transcript = [_intent(), _signal(True), _signal(False)]
    assert should_run_session_role(transcript, {}) is False


def test_three_consecutive_correct_triggers() -> None:
    signals = [_signal(True)] * MASTERY_THRESHOLD
    transcript = [_intent()] + signals
    assert should_run_session_role(transcript, {}) is True


def test_three_consecutive_incorrect_triggers() -> None:
    signals = [_signal(False)] * MASTERY_THRESHOLD
    transcript = [_intent()] + signals
    assert should_run_session_role(transcript, {}) is True


def test_mixed_signals_no_trigger() -> None:
    transcript = [_intent(), _signal(True), _signal(False), _signal(True)]
    assert should_run_session_role(transcript, {}) is False


def test_non_signal_events_between_signals_ignored() -> None:
    # UtteranceEvents interleaved — only TurnSignalEvents count
    transcript = [
        _intent(),
        UtteranceEvent(text="q1"),
        _signal(True),
        UtteranceEvent(text="q2"),
        _signal(True),
        UtteranceEvent(text="q3"),
        _signal(True),
    ]
    assert should_run_session_role(transcript, {}) is True
```

- [ ] **Step 2: Run to confirm failure**

Run:
```bash
uv run pytest tests/roles/test_trigger_policy.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write `app/roles/trigger_policy.py`**

```python
from app.domain.events import CoachIntentEvent, TranscriptEvent, TurnSignalEvent

MASTERY_THRESHOLD = 3


def should_run_session_role(transcript: list[TranscriptEvent], program_state: dict) -> bool:
    """Return True if the session role should run before the next turn."""
    if not any(isinstance(e, CoachIntentEvent) for e in transcript):
        return True

    recent_signals = [e for e in transcript if isinstance(e, TurnSignalEvent)][-MASTERY_THRESHOLD:]
    if len(recent_signals) >= MASTERY_THRESHOLD:
        if all(s.on_target for s in recent_signals):
            return True
        if all(not s.on_target for s in recent_signals):
            return True

    return False
```

- [ ] **Step 4: Run tests**

Run:
```bash
uv run pytest tests/roles/test_trigger_policy.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/roles/trigger_policy.py tests/roles/test_trigger_policy.py
git commit -m "feat: session-role trigger policy (session start + consecutive-result threshold)"
```

---

## Task 3: Learner store — update_program_state

**Files:**
- Modify: `app/store/learners.py`
- Modify: `tests/store/test_learners_store.py`

- [ ] **Step 1: Write failing test — add to `tests/store/test_learners_store.py`**

Add these tests at the end of the existing file:

```python
@pytest.mark.asyncio
async def test_update_program_state(db_pool: None) -> None:
    learner = await learners.insert(LearnerCreate(name="Alice"))
    updated = await learners.update_program_state(
        learner.id,
        program_id="prog-1",
        skill_state={"attempt_count": 1, "correct_count": 1},
        skill_id="skill-a",
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
```

- [ ] **Step 2: Run to confirm failure**

Run:
```bash
uv run pytest tests/store/test_learners_store.py -v
```

Expected: 2 new tests FAIL with `AttributeError: module 'app.store.learners' has no attribute 'update_program_state'`.

- [ ] **Step 3: Add `update_program_state` to `app/store/learners.py`**

Add this function at the end of the file. The full updated file:

```python
import json
import uuid
from datetime import datetime, timezone

from app.domain.learner import Learner, LearnerCreate
from app.store.db import connection


async def insert(data: LearnerCreate) -> Learner:
    now = datetime.now(timezone.utc)
    learner_id = str(uuid.uuid4())
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO learners (id, name, cohort_tags, created_at, updated_at)
                VALUES (%s, %s, %s::jsonb, %s, %s)
                """,
                (learner_id, data.name, json.dumps(data.cohort_tags), now, now),
            )
        await conn.commit()
    return Learner(
        id=learner_id,
        name=data.name,
        cohort_tags=data.cohort_tags,
        portrait_md="",
        traits={},
        program_states={},
        created_at=now,
        updated_at=now,
    )


async def get(learner_id: str) -> Learner | None:
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, cohort_tags, portrait_md, traits, program_states, "
                "created_at, updated_at FROM learners WHERE id = %s",
                (learner_id,),
            )
            row = await cur.fetchone()
    if row is None:
        return None
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


async def update_program_state(
    learner_id: str,
    program_id: str,
    skill_id: str,
    skill_state: dict,
) -> Learner:
    """Patch program_states[program_id][skill_id] for the given learner."""
    now = datetime.now(timezone.utc)
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE learners
                SET program_states = jsonb_set(
                    jsonb_set(
                        program_states,
                        %s::text[],
                        COALESCE(program_states->%s, '{}'::jsonb),
                        true
                    ),
                    %s::text[],
                    %s::jsonb,
                    true
                ),
                updated_at = %s
                WHERE id = %s
                """,
                (
                    [program_id],
                    program_id,
                    [program_id, skill_id],
                    json.dumps(skill_state),
                    now,
                    learner_id,
                ),
            )
        await conn.commit()
    learner = await get(learner_id)
    assert learner is not None
    return learner
```

- [ ] **Step 4: Run tests**

Run:
```bash
uv run pytest tests/store/test_learners_store.py -v
```

Expected: all 5 tests PASS (3 existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add app/store/learners.py tests/store/test_learners_store.py
git commit -m "feat: learner store — update_program_state patches per-skill JSON in Postgres"
```

---

## Task 4: Session role LLM function

**Files:**
- Create: `app/roles/session_role.py`
- Create: `tests/roles/test_session_role.py`

- [ ] **Step 1: Write failing test `tests/roles/test_session_role.py`**

```python
from types import SimpleNamespace

import pytest

from app.domain.content import CoachProfile, Program, Skill
from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TurnSignalEvent,
    UtteranceEvent,
)
from app.roles.session_role import run_session


def _fake_session_client(goal: str = "drill", skill_id: str = "add-2digit-carry"):
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        input={
                            "goal": goal,
                            "skill_id": skill_id,
                            "difficulty_hint": "same",
                            "rationale": "Learner seems ready to drill.",
                            "tone_note": None,
                        },
                    )
                ]
            )

    class _FakeClient:
        messages = _FakeMessages()

    return _FakeClient()


_PROGRAM = Program(
    id="elementary-math",
    title="Elementary Math",
    skill_ids=["add-1digit", "add-2digit-carry"],
    mandatory_skill_ids=["add-1digit", "add-2digit-carry"],
    assessment_criteria="Student solves both skill types reliably.",
    coach_profile_id="patient-encourager",
)

_COACH_PROFILE = CoachProfile(
    id="patient-encourager",
    title="Patient Encourager",
    tone="Warm and encouraging",
    pacing="Slow and steady",
)


@pytest.mark.asyncio
async def test_run_session_returns_coach_intent() -> None:
    intent = await run_session(
        program=_PROGRAM,
        coach_profile=_COACH_PROFILE,
        learner_portrait="",
        program_state={},
        transcript_window=[],
        llm_client=_fake_session_client(),
    )
    assert isinstance(intent, CoachIntentEvent)
    assert intent.goal == "drill"
    assert intent.skill_id == "add-2digit-carry"


@pytest.mark.asyncio
async def test_run_session_uses_rationale() -> None:
    intent = await run_session(
        program=_PROGRAM,
        coach_profile=_COACH_PROFILE,
        learner_portrait="Quick learner, confident.",
        program_state={},
        transcript_window=[],
        llm_client=_fake_session_client(goal="consolidate"),
    )
    assert intent.goal == "consolidate"
    assert intent.rationale


@pytest.mark.asyncio
async def test_run_session_with_transcript() -> None:
    transcript = [
        UtteranceEvent(text="What is 2+3?"),
        LearnerTextEvent(text="5"),
        TurnSignalEvent(on_target=True),
        UtteranceEvent(text="What is 47+36?"),
        LearnerTextEvent(text="83"),
        TurnSignalEvent(on_target=True),
        UtteranceEvent(text="Excellent!"),
        LearnerTextEvent(text="thanks"),
        TurnSignalEvent(on_target=True),
    ]
    intent = await run_session(
        program=_PROGRAM,
        coach_profile=_COACH_PROFILE,
        learner_portrait="",
        program_state={"add-2digit-carry": {"consecutive_correct": 3}},
        transcript_window=transcript,
        llm_client=_fake_session_client(goal="wrap"),
    )
    assert intent.goal == "wrap"
```

- [ ] **Step 2: Run to confirm failure**

Run:
```bash
uv run pytest tests/roles/test_session_role.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write `app/roles/session_role.py`**

```python
from typing import Any

from anthropic import Anthropic

from app.domain.content import CoachProfile, Program
from app.domain.events import CoachIntentEvent, LearnerTextEvent, TranscriptEvent, TurnSignalEvent, UtteranceEvent

SESSION_MODEL = "claude-sonnet-4-6"
TRANSCRIPT_WINDOW_SIZE = 20

_SET_INTENT_TOOL: dict[str, Any] = {
    "name": "set_intent",
    "description": "Set the coaching intent for the next phase of the session.",
    "input_schema": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "enum": ["warm_up", "probe", "teach", "drill", "consolidate", "rest", "wrap"],
                "description": "The coaching goal for the next phase.",
            },
            "skill_id": {
                "type": "string",
                "description": "Which skill to focus on. Must be one of the program's skill_ids.",
            },
            "difficulty_hint": {
                "type": "string",
                "enum": ["easier", "same", "harder"],
                "description": "Relative difficulty adjustment for the next questions.",
            },
            "rationale": {
                "type": "string",
                "description": "Brief explanation of why this intent was chosen (for logs and human tutor view).",
            },
            "tone_note": {
                "type": "string",
                "description": "Optional tone adjustment for this phase (e.g. 'extra encouraging').",
            },
        },
        "required": ["goal", "skill_id"],
    },
}


def _build_session_prompt(
    program: Program,
    coach_profile: CoachProfile | None,
    learner_portrait: str,
    program_state: dict,
) -> str:
    skills_list = ", ".join(program.skill_ids)
    mandatory_list = ", ".join(program.mandatory_skill_ids)
    lines = [
        "You are the session planner for a one-on-one tutoring session.",
        "",
        f"PROGRAM: {program.title}",
        f"SKILLS AVAILABLE: {skills_list}",
        f"MANDATORY SKILLS: {mandatory_list}",
        f"COMPLETION CRITERIA: {program.assessment_criteria}",
        "",
    ]
    if coach_profile:
        lines += [
            f"COACHING STYLE ({coach_profile.title}):",
            f"  Tone: {coach_profile.tone}",
            f"  Pacing: {coach_profile.pacing}",
            "",
        ]
    if learner_portrait:
        lines += [f"LEARNER PORTRAIT:", learner_portrait, ""]
    if program_state:
        import json
        lines += [f"PROGRAM STATE (per-skill progress):", json.dumps(program_state, indent=2), ""]
    lines += [
        "Review the recent transcript and progress data above.",
        "Decide what to do next: which skill to focus on, what goal (warm_up, probe, teach, drill, consolidate, rest, wrap), and how hard.",
        "Use set_intent to record your decision.",
    ]
    return "\n".join(lines)


def _format_transcript_for_session(window: list[TranscriptEvent]) -> list[dict]:
    messages = []
    for event in window[-TRANSCRIPT_WINDOW_SIZE:]:
        if isinstance(event, LearnerTextEvent):
            messages.append({"role": "user", "content": event.text})
        elif isinstance(event, UtteranceEvent):
            messages.append({"role": "assistant", "content": event.text})
        elif isinstance(event, TurnSignalEvent):
            label = "✓ on-target" if event.on_target else "✗ off-target"
            markers = ", ".join(event.matched_markers) if event.matched_markers else "none"
            messages.append({
                "role": "assistant",
                "content": f"[Turn signal: {label}; markers: {markers}]",
            })
    return messages


async def run_session(
    program: Program,
    coach_profile: CoachProfile | None,
    learner_portrait: str,
    program_state: dict,
    transcript_window: list[TranscriptEvent],
    llm_client: Any,
) -> CoachIntentEvent:
    """Call the session-level LLM role and return a CoachIntentEvent."""
    messages = _format_transcript_for_session(transcript_window)
    if not messages:
        messages = [{"role": "user", "content": "(session start — no turns yet)"}]

    response = llm_client.messages.create(
        model=SESSION_MODEL,
        system=_build_session_prompt(program, coach_profile, learner_portrait, program_state),
        messages=messages,
        tools=[_SET_INTENT_TOOL],
        tool_choice={"type": "any"},
        max_tokens=512,
    )

    tool_input = response.content[0].input
    return CoachIntentEvent(
        goal=tool_input["goal"],
        skill_id=tool_input["skill_id"],
        difficulty_hint=tool_input.get("difficulty_hint"),
        rationale=tool_input.get("rationale", ""),
        tone_note=tool_input.get("tone_note"),
    )


def get_session_llm_client() -> Anthropic:
    return Anthropic()
```

- [ ] **Step 4: Run tests**

Run:
```bash
uv run pytest tests/roles/test_session_role.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/roles/session_role.py tests/roles/test_session_role.py
git commit -m "feat: session-level planning role with set_intent tool"
```

---

## Task 5: Wire into /turn endpoint + integration tests

**Files:**
- Modify: `app/api/sessions.py`
- Modify: `tests/conftest.py`
- Create: `tests/api/test_session_planning_api.py`
- Modify: `tests/api/test_turn_api.py` (update fixture to also override session LLM)

- [ ] **Step 1: Update `tests/conftest.py`**

Replace the `client` and `client_with_fake_llm` section. The full updated conftest:

```python
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
async def client(db_pool: None, database_url: str) -> AsyncIterator[AsyncClient]:
    from pathlib import Path

    from app.content_registry.registry import init_registry
    from app.main import app

    init_registry(Path("content"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
```

Note: `client_with_fake_llm` is now defined locally in each test module that needs LLM overrides. This keeps the conftest minimal and avoids sharing mutable state across test files.

- [ ] **Step 2: Update `tests/api/test_turn_api.py` to override both LLM deps**

The existing `client_with_fake_llm` fixture only overrides `get_llm_client`. Now that `/turn` also calls `get_session_llm_client`, tests will fail unless that's overridden too. Update the fixture at the top of `tests/api/test_turn_api.py`:

```python
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.roles.session_role import get_session_llm_client
from app.roles.turn_role import get_llm_client


def _make_fake_turn_llm(utterance: str = "What is 47 + 36?", on_target: bool = True):
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


def _make_fake_session_llm(goal: str = "warm_up", skill_id: str = "add-1digit"):
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        input={
                            "goal": goal,
                            "skill_id": skill_id,
                            "difficulty_hint": "same",
                            "rationale": "Starting warm up.",
                        },
                    )
                ]
            )

    class _FakeLLM:
        messages = _FakeMessages()

    return _FakeLLM()


@pytest.fixture
def fake_llm():
    return _make_fake_turn_llm()


@pytest.fixture
def client_with_fake_llm(client: AsyncClient, fake_llm):
    from app.main import app
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    app.dependency_overrides[get_session_llm_client] = lambda: _make_fake_session_llm()
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

- [ ] **Step 3: Write failing test `tests/api/test_session_planning_api.py`**

```python
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.roles.session_role import get_session_llm_client
from app.roles.turn_role import get_llm_client


def _fake_turn_llm(on_target: bool = True):
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(
                    type="tool_use",
                    input={"utterance": "Good, next question.", "on_target": on_target,
                           "matched_markers": [], "affect": {}, "notes": ""},
                )]
            )
    class _FakeLLM:
        messages = _FakeMessages()
    return _FakeLLM()


def _fake_session_llm(goal: str = "warm_up", skill_id: str = "add-1digit"):
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(
                    type="tool_use",
                    input={"goal": goal, "skill_id": skill_id,
                           "difficulty_hint": "same", "rationale": "test"},
                )]
            )
    class _FakeLLM:
        messages = _FakeMessages()
    return _FakeLLM()


@pytest.fixture
def client_planning(client: AsyncClient):
    from app.main import app
    app.dependency_overrides[get_llm_client] = lambda: _fake_turn_llm()
    app.dependency_overrides[get_session_llm_client] = lambda: _fake_session_llm()
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def session_setup(client_planning: AsyncClient):
    learner = (await client_planning.post("/learners", json={"name": "Planner"})).json()
    session = (await client_planning.post("/sessions", json={
        "learner_id": learner["id"],
        "program_id": "elementary-math",
    })).json()
    return client_planning, learner["id"], session["id"]


@pytest.mark.asyncio
async def test_first_turn_appends_session_role_intent(session_setup) -> None:
    client, learner_id, session_id = session_setup
    await client.post(f"/sessions/{session_id}/turn", json={"text": "hi"})
    session = (await client.get(f"/sessions/{session_id}")).json()
    intent_events = [e for e in session["transcript"] if e["kind"] == "coach_intent"]
    # Session role fires at start → one CoachIntentEvent from session role
    assert len(intent_events) >= 1
    assert intent_events[0]["goal"] == "warm_up"


@pytest.mark.asyncio
async def test_program_state_updated_after_turn(session_setup) -> None:
    client, learner_id, session_id = session_setup
    await client.post(f"/sessions/{session_id}/turn", json={"text": "5"})
    learner = (await client.get(f"/learners/{learner_id}")).json()
    prog_state = learner["program_states"].get("elementary-math", {})
    # The state updater should have written something for the skill used
    assert len(prog_state) > 0


@pytest.mark.asyncio
async def test_session_role_fires_after_mastery_threshold(session_setup) -> None:
    """After 3 consecutive correct answers, the session role fires again and a new intent appears."""
    from app.main import app
    call_count = {"n": 0}

    def _counting_session_llm():
        call_count["n"] += 1
        return _fake_session_llm(goal="drill", skill_id="add-2digit-carry")

    app.dependency_overrides[get_session_llm_client] = _counting_session_llm

    client, learner_id, session_id = session_setup
    # First turn: session role fires at start (call 1)
    await client.post(f"/sessions/{session_id}/turn", json={"text": "hi"})
    # Force 3 consecutive correct signals directly into transcript
    for _ in range(3):
        await client.post(
            f"/sessions/{session_id}/events",
            json={"event": {"kind": "turn_signal", "on_target": True}},
        )
    # Next turn: trigger policy should fire session role again (call 2)
    await client.post(f"/sessions/{session_id}/turn", json={"text": "83"})
    assert call_count["n"] >= 2


@pytest.mark.asyncio
async def test_session_role_fires_after_struggle_threshold(session_setup) -> None:
    """After 3 consecutive wrong answers, the session role fires and may switch skill or ease difficulty."""
    from app.main import app
    new_intents = []

    def _recording_session_llm():
        class _FakeMessages:
            def create(self, **kwargs):
                new_intents.append(True)
                return SimpleNamespace(
                    content=[SimpleNamespace(
                        type="tool_use",
                        input={"goal": "teach", "skill_id": "add-1digit",
                               "difficulty_hint": "easier", "rationale": "too hard"},
                    )]
                )
        class _FakeLLM:
            messages = _FakeMessages()
        return _FakeLLM()

    app.dependency_overrides[get_session_llm_client] = _recording_session_llm

    client, learner_id, session_id = session_setup
    await client.post(f"/sessions/{session_id}/turn", json={"text": "start"})
    for _ in range(3):
        await client.post(
            f"/sessions/{session_id}/events",
            json={"event": {"kind": "turn_signal", "on_target": False}},
        )
    await client.post(f"/sessions/{session_id}/turn", json={"text": "idk"})

    session = (await client.get(f"/sessions/{session_id}")).json()
    intents = [e for e in session["transcript"] if e["kind"] == "coach_intent"]
    # Should have at least 2 intents: start + post-struggle
    assert len(intents) >= 2
    # Last intent should reflect the struggle response (teach/easier on add-1digit)
    last = intents[-1]
    assert last["skill_id"] == "add-1digit"
```

- [ ] **Step 4: Run to confirm failure**

Run:
```bash
uv run pytest tests/api/test_session_planning_api.py -v
```

Expected: failures — either 404s or the session role not being called.

- [ ] **Step 5: Rewrite `app/api/sessions.py` to wire all components**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.content_registry.registry import registry
from app.domain.events import CoachIntentEvent, LearnerTextEvent, TranscriptEvent
from app.domain.session import Session, SessionCreate
from app.roles.session_role import get_session_llm_client, run_session
from app.roles.state_updater import apply_turn_signal
from app.roles.trigger_policy import should_run_session_role
from app.roles.turn_role import get_llm_client, run_turn
from app.store import learners as learners_store
from app.store import sessions as sessions_store

router = APIRouter(prefix="/sessions", tags=["sessions"])


class AppendEventRequest(BaseModel):
    event: TranscriptEvent


class EndSessionRequest(BaseModel):
    summary_md: str = ""


class TurnRequest(BaseModel):
    text: str


class TurnResponse(BaseModel):
    utterance: str
    turn_signal: dict


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
    turn_llm=Depends(get_llm_client),
    session_llm=Depends(get_session_llm_client),
) -> TurnResponse:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    learner = await learners_store.get(session.learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    program_state = learner.program_states.get(session.program_id, {})

    # Run session role if trigger policy fires (e.g. session start, mastery, struggle)
    if should_run_session_role(session.transcript, program_state):
        reg = registry()
        program = reg.program(session.program_id)
        if program is None:
            raise HTTPException(status_code=422, detail=f"Program '{session.program_id}' not found")
        coach_profile = reg.coach_profile(program.coach_profile_id) if program.coach_profile_id else None
        intent = await run_session(
            program=program,
            coach_profile=coach_profile,
            learner_portrait=learner.portrait_md,
            program_state=program_state,
            transcript_window=session.transcript,
            llm_client=session_llm,
        )
        await sessions_store.append_event(session_id, intent)
        session = await sessions_store.get(session_id)

    # Derive current intent (most recent CoachIntentEvent)
    current_intent: CoachIntentEvent | None = None
    for event in reversed(session.transcript):
        if isinstance(event, CoachIntentEvent):
            current_intent = event
            break

    if current_intent is None or current_intent.skill_id is None:
        raise HTTPException(status_code=422, detail="No skill available for this session")

    skill = registry().skill(current_intent.skill_id)
    if skill is None:
        raise HTTPException(status_code=422, detail=f"Skill '{current_intent.skill_id}' not found in registry")

    # Record learner input
    await sessions_store.append_event(session_id, LearnerTextEvent(text=body.text))
    session = await sessions_store.get(session_id)

    # Run turn role
    utterance_event, signal_event = await run_turn(
        intent=current_intent,
        skill=skill,
        transcript_window=session.transcript,
        learner_text=body.text,
        llm_client=turn_llm,
    )

    await sessions_store.append_event(session_id, utterance_event)
    await sessions_store.append_event(session_id, signal_event)

    # Deterministic state update — no LLM involved
    updated_state = apply_turn_signal(program_state, current_intent.skill_id, signal_event)
    await learners_store.update_program_state(
        learner_id=session.learner_id,
        program_id=session.program_id,
        skill_id=current_intent.skill_id,
        skill_state=updated_state[current_intent.skill_id],
    )

    return TurnResponse(
        utterance=utterance_event.text,
        turn_signal=signal_event.model_dump(mode="json"),
    )
```

- [ ] **Step 6: Run session planning tests**

Run:
```bash
uv run pytest tests/api/test_session_planning_api.py -v
```

Expected: all 4 PASS.

- [ ] **Step 7: Run the full test suite**

Run:
```bash
uv run pytest -v
```

Expected: all 46 existing tests + new tests = **62 tests PASS** (46 + 7 state_updater + 7 trigger_policy + 3 session_role + 4 session_planning + 2 learners_store = ~69 total, exact count depends on what was there before).

- [ ] **Step 8: Commit**

```bash
git add app/ tests/ content/
git commit -m "feat: session-level planning role wired into /turn — trigger policy, state updater, skill switching"
```

---

## Self-Review

**Spec coverage:**

| Phase 3 requirement | Task |
|---|---|
| Session role runs at session start | Task 5 — trigger policy fires when no CoachIntentEvent in transcript |
| Session role runs on threshold triggers | Task 5 — 3 consecutive correct/incorrect fires session role |
| Intent contract (goal, skill_id, difficulty_hint, rationale, tone_note) | Task 4 — `set_intent` tool + `CoachIntentEvent` |
| Skill switching works inside a program | Task 5 — session role can set any `skill_id` from `program.skill_ids` |
| Turn signal folded into program state deterministically | Task 5 — `apply_turn_signal` + `update_program_state` |
| Math program with mandatory skills and assessment rubric | Task 0 — `elementary-math.md` updated with 2 skills |
| Subject teaching guide (CoachProfile) injected into session role | Task 4 + 5 — looked up from registry, passed to `run_session` |
| Most turns are single LLM calls | Task 5 — session role only fires when trigger policy returns True |

**Placeholder scan:** None found. All code blocks present and complete.

**Type consistency:**
- `run_session()` signature in test matches implementation: `(program, coach_profile, learner_portrait, program_state, transcript_window, llm_client) -> CoachIntentEvent` ✓
- `apply_turn_signal(program_state, skill_id, signal) -> dict` consistent across test and impl ✓
- `should_run_session_role(transcript, program_state) -> bool` consistent ✓
- `update_program_state(learner_id, program_id, skill_id, skill_state)` consistent across test and usage in sessions.py ✓
