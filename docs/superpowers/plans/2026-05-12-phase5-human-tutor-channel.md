# Phase 5 — Human Tutor Channel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the human tutor channel: a tutor identity record, in-process SSE event stream, and four interaction modes — whisper (guidance to session role), steer (direct intent injection), takeover/handback (pause AI roles, tutor types directly), and async turn annotations.

**Architecture:** A `tutors` DB table backs the tutor identity record. An in-process asyncio pub/sub (`app/event_stream.py`) streams all session events to observers; replay from transcript at subscribe time. The session role gains a `pending_guidance` parameter so whispers are incorporated on its next planning call. Steers inject a `CoachIntentEvent` directly without calling the session LLM. Takeover state is derived by scanning for the latest `takeover`/`handback` `TutorInputEvent` in the transcript — no separate state field needed. All four modes log `TutorInputEvent` entries so the identity role sees human intervention in its next reflection.

**Tech Stack:** Same as previous phases. `TutorInputEvent` already exists in `app/domain/events.py`. FastAPI `StreamingResponse` for SSE. `asyncio.Queue` for in-process pub/sub.

---

## File Structure

**Create:**
```
migrations/versions/0002_tutors.py
app/domain/tutor.py
app/store/tutors.py
app/api/tutors.py
app/event_stream.py
tests/api/test_tutors_api.py
tests/test_event_stream.py
tests/api/test_tutor_channel_api.py
```

**Modify:**
```
app/domain/events.py           # add "handback" to TutorInputEvent mode enum
app/roles/trigger_policy.py   # fire when pending whisper exists
app/roles/session_role.py     # add pending_guidance param to run_session()
app/api/sessions.py            # publish events, new endpoints: whisper/steer/takeover/handback/tutor-turn/annotate
app/main.py                    # include tutors router
```

---

## Task 0: Tutor record — migration + model + store + API

**Files:**
- Create: `migrations/versions/0002_tutors.py`
- Create: `app/domain/tutor.py`
- Create: `app/store/tutors.py`
- Create: `app/api/tutors.py`
- Modify: `app/main.py`
- Create: `tests/api/test_tutors_api.py`

- [ ] **Step 1: Add "handback" to TutorInputEvent mode in `app/domain/events.py`**

Replace the `mode` line in `TutorInputEvent`:

```python
class TutorInputEvent(_EventBase):
    kind: Literal["tutor_input"] = "tutor_input"
    mode: Literal["whisper", "steer", "takeover", "handback", "annotation"]
    tutor_id: str
    content: str
    target_turn_idx: int | None = None
```

- [ ] **Step 2: Write migration `migrations/versions/0002_tutors.py`**

```python
"""create tutors table"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS tutors (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tutors")
```

- [ ] **Step 3: Write `app/domain/tutor.py`**

```python
from datetime import datetime
from pydantic import BaseModel


class TutorCreate(BaseModel):
    name: str


class Tutor(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: Write `app/store/tutors.py`**

```python
import uuid
from datetime import datetime, timezone

from app.domain.tutor import Tutor, TutorCreate
from app.store.db import connection


async def insert(data: TutorCreate) -> Tutor:
    now = datetime.now(timezone.utc)
    tutor_id = str(uuid.uuid4())
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO tutors (id, name, created_at, updated_at) VALUES (%s, %s, %s, %s)",
                (tutor_id, data.name, now, now),
            )
        await conn.commit()
    return Tutor(id=tutor_id, name=data.name, created_at=now, updated_at=now)


async def get(tutor_id: str) -> Tutor | None:
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, created_at, updated_at FROM tutors WHERE id = %s",
                (tutor_id,),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    return Tutor(id=row[0], name=row[1], created_at=row[2], updated_at=row[3])
```

- [ ] **Step 5: Write `app/api/tutors.py`**

```python
from fastapi import APIRouter, HTTPException

from app.domain.tutor import Tutor, TutorCreate
from app.store import tutors as tutors_store

router = APIRouter(prefix="/tutors", tags=["tutors"])


@router.post("", response_model=Tutor, status_code=201)
async def create_tutor(body: TutorCreate) -> Tutor:
    return await tutors_store.insert(body)


@router.get("/{tutor_id}", response_model=Tutor)
async def get_tutor(tutor_id: str) -> Tutor:
    tutor = await tutors_store.get(tutor_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    return tutor
```

- [ ] **Step 6: Wire tutors router into `app/main.py`**

Add after the other router imports:

```python
from app.api import tutors as tutors_router  # noqa: E402

app.include_router(tutors_router.router)
```

- [ ] **Step 7: Write failing tests `tests/api/test_tutors_api.py`**

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_get_tutor(client: AsyncClient) -> None:
    resp = await client.post("/tutors", json={"name": "Ms. Chen"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Ms. Chen"
    assert "id" in body

    fetched = (await client.get(f"/tutors/{body['id']}")).json()
    assert fetched["name"] == "Ms. Chen"
    assert fetched["id"] == body["id"]


@pytest.mark.asyncio
async def test_get_nonexistent_tutor_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/tutors/no-such-id")
    assert resp.status_code == 404
```

- [ ] **Step 8: Run tests**

Run:
```bash
uv run pytest tests/api/test_tutors_api.py -v
```

Expected: 2 PASS.

- [ ] **Step 9: Run full suite to confirm no regressions**

Run:
```bash
uv run pytest -v 2>&1 | tail -5
```

Expected: all 80 existing + 2 new PASS.

- [ ] **Step 10: Commit**

```bash
git add migrations/versions/0002_tutors.py app/domain/tutor.py app/store/tutors.py \
        app/api/tutors.py app/main.py app/domain/events.py tests/api/test_tutors_api.py
git commit -m "feat: tutor record — table, model, store, API + handback mode in TutorInputEvent"
```

---

## Task 1: In-process event stream + SSE endpoint

**Files:**
- Create: `app/event_stream.py`
- Create: `tests/test_event_stream.py`
- Modify: `app/api/sessions.py` — add `/stream` endpoint; publish after every `append_event` call in `/turn` and `/events`

- [ ] **Step 1: Write failing tests `tests/test_event_stream.py`**

```python
import asyncio

import pytest

from app.event_stream import publish, subscribe


@pytest.mark.asyncio
async def test_subscribe_replays_existing_events() -> None:
    replay = [{"kind": "learner_text", "text": "hello"}]
    received = []

    async def collect():
        async for event in subscribe("sess-replay-1", replay):
            received.append(event)
            break

    await collect()
    assert received == replay


@pytest.mark.asyncio
async def test_publish_reaches_subscriber() -> None:
    received = []

    async def collect():
        async for event in subscribe("sess-pub-1", []):
            received.append(event)
            break

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)
    await publish("sess-pub-1", {"kind": "utterance", "text": "hi"})
    await task
    assert len(received) == 1
    assert received[0]["kind"] == "utterance"


@pytest.mark.asyncio
async def test_publish_to_multiple_subscribers() -> None:
    received_a: list[dict] = []
    received_b: list[dict] = []

    async def collect(store: list):
        async for event in subscribe("sess-multi-1", []):
            store.append(event)
            break

    task_a = asyncio.create_task(collect(received_a))
    task_b = asyncio.create_task(collect(received_b))
    await asyncio.sleep(0)
    await publish("sess-multi-1", {"kind": "turn_signal", "on_target": True})
    await task_a
    await task_b
    assert received_a[0]["on_target"] is True
    assert received_b[0]["on_target"] is True


@pytest.mark.asyncio
async def test_no_cross_session_leakage() -> None:
    received = []

    async def collect():
        async for event in subscribe("sess-iso-A", []):
            received.append(event)
            break

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)
    await publish("sess-iso-B", {"kind": "utterance", "text": "wrong session"})
    await publish("sess-iso-A", {"kind": "utterance", "text": "right session"})
    await task
    assert received[0]["text"] == "right session"
```

- [ ] **Step 2: Run to confirm failure**

Run:
```bash
uv run pytest tests/test_event_stream.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write `app/event_stream.py`**

```python
import asyncio
from collections import defaultdict
from typing import AsyncGenerator

_subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)


async def publish(session_id: str, event: dict) -> None:
    for q in _subscribers.get(session_id, []):
        await q.put(event)


async def subscribe(
    session_id: str,
    replay: list[dict],
) -> AsyncGenerator[dict, None]:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers[session_id].append(q)
    try:
        for event in replay:
            yield event
        while True:
            event = await asyncio.wait_for(q.get(), timeout=30.0)
            yield event
    except asyncio.TimeoutError:
        pass
    finally:
        _subscribers[session_id].remove(q)
```

- [ ] **Step 4: Run event stream unit tests**

Run:
```bash
uv run pytest tests/test_event_stream.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Add SSE `/stream` endpoint and wire `publish` into `/turn` and `/events` in `app/api/sessions.py`**

Add `import json` and these imports at the top of `app/api/sessions.py`:

```python
import json

from fastapi.responses import StreamingResponse

from app import event_stream
from app.store import tutors as tutors_store
```

Add the `stream_session` endpoint after the `append_event` endpoint:

```python
@router.get("/{session_id}/stream")
async def stream_session(session_id: str) -> StreamingResponse:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    replay = [e.model_dump(mode="json") for e in session.transcript]

    async def generator():
        async for evt in event_stream.subscribe(session_id, replay):
            yield f"data: {json.dumps(evt)}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")
```

In the `append_event` endpoint, add a publish call after appending:

```python
@router.post("/{session_id}/events", status_code=204)
async def append_event(session_id: str, body: AppendEventRequest) -> None:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await sessions_store.append_event(session_id, body.event)
    await event_stream.publish(session_id, body.event.model_dump(mode="json"))
```

In the `session_turn` endpoint, add publish after each `append_event` call. After appending `utterance_event`:
```python
    await sessions_store.append_event(session_id, utterance_event)
    await event_stream.publish(session_id, utterance_event.model_dump(mode="json"))
    await sessions_store.append_event(session_id, signal_event)
    await event_stream.publish(session_id, signal_event.model_dump(mode="json"))
```

Also add publish for the learner input and session role events. The complete updated turn loop (only the publish additions shown):
```python
    # After LearnerTextEvent append:
    await sessions_store.append_event(session_id, LearnerTextEvent(text=body.text))
    await event_stream.publish(session_id, LearnerTextEvent(text=body.text).model_dump(mode="json"))
    # After intent append (in the should_run_session_role block):
    await sessions_store.append_event(session_id, intent)
    await event_stream.publish(session_id, intent.model_dump(mode="json"))
```

- [ ] **Step 6: Run full suite**

Run:
```bash
uv run pytest -v 2>&1 | tail -5
```

Expected: all 82+ tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/event_stream.py app/api/sessions.py tests/test_event_stream.py
git commit -m "feat: in-process event stream + SSE /stream endpoint; publish all session events"
```

---

## Task 2: Whisper — tutor guidance to session planner

**Files:**
- Modify: `app/roles/trigger_policy.py`
- Modify: `app/roles/session_role.py`
- Modify: `app/api/sessions.py`
- Modify: `tests/roles/test_trigger_policy.py`
- Create: `tests/api/test_tutor_channel_api.py` (start the file here, tasks 3–5 add to it)

- [ ] **Step 1: Write failing trigger policy tests — add to `tests/roles/test_trigger_policy.py`**

Add at the end of the file (add `TutorInputEvent` to the import):

```python
from app.domain.events import (
    CoachIntentEvent,
    TranscriptEvent,
    TurnSignalEvent,
    TutorInputEvent,
)

def test_pending_whisper_after_intent_triggers() -> None:
    transcript: list[TranscriptEvent] = [
        CoachIntentEvent(goal="warm_up", skill_id="add-1digit"),
        TutorInputEvent(mode="whisper", tutor_id="t1", content="go easier"),
    ]
    assert should_run_session_role(transcript, {}) is True


def test_whisper_before_intent_does_not_double_trigger() -> None:
    """Whisper consumed by the existing intent — no re-trigger."""
    transcript: list[TranscriptEvent] = [
        TutorInputEvent(mode="whisper", tutor_id="t1", content="go easier"),
        CoachIntentEvent(goal="teach", skill_id="add-1digit"),
    ]
    assert should_run_session_role(transcript, {}) is False
```

- [ ] **Step 2: Run to confirm failure**

Run:
```bash
uv run pytest tests/roles/test_trigger_policy.py -v
```

Expected: 2 new tests FAIL.

- [ ] **Step 3: Update `app/roles/trigger_policy.py`**

Replace the entire file:

```python
from app.domain.events import CoachIntentEvent, TranscriptEvent, TurnSignalEvent, TutorInputEvent

MASTERY_THRESHOLD = 3


def _last_intent_idx(transcript: list[TranscriptEvent]) -> int:
    for i in range(len(transcript) - 1, -1, -1):
        if isinstance(transcript[i], CoachIntentEvent):
            return i
    return -1


def should_run_session_role(transcript: list[TranscriptEvent], program_state: dict) -> bool:
    """Return True if the session role should run before the next turn."""
    if not any(isinstance(e, CoachIntentEvent) for e in transcript):
        return True

    last_idx = _last_intent_idx(transcript)
    events_after = transcript[last_idx + 1:]
    if any(isinstance(e, TutorInputEvent) and e.mode == "whisper" for e in events_after):
        return True

    recent_signals = [e for e in transcript if isinstance(e, TurnSignalEvent)][-MASTERY_THRESHOLD:]
    if len(recent_signals) >= MASTERY_THRESHOLD:
        if all(s.on_target for s in recent_signals):
            return True
        if all(not s.on_target for s in recent_signals):
            return True

    return False
```

- [ ] **Step 4: Run trigger policy tests**

Run:
```bash
uv run pytest tests/roles/test_trigger_policy.py -v
```

Expected: all 9 PASS.

- [ ] **Step 5: Update `app/roles/session_role.py` — add `pending_guidance` param**

Replace `_build_session_prompt` to accept the extra param and include it in the prompt when non-empty:

```python
def _build_session_prompt(
    program: Program,
    coach_profile: CoachProfile | None,
    learner_portrait: str,
    program_state: dict,
    pending_guidance: str = "",
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
        lines += ["LEARNER PORTRAIT:", learner_portrait, ""]
    if program_state:
        lines += ["PROGRAM STATE (per-skill progress):", json.dumps(program_state, indent=2), ""]
    if pending_guidance:
        lines += ["TUTOR GUIDANCE (incorporate into your decision):", pending_guidance, ""]
    lines += [
        "Review the recent transcript and progress data above.",
        "Decide what to do next: which skill to focus on, what goal, and how hard.",
        "Use set_intent to record your decision.",
    ]
    return "\n".join(lines)
```

Update `run_session` signature to accept and forward `pending_guidance`:

```python
async def run_session(
    program: Program,
    coach_profile: CoachProfile | None,
    learner_portrait: str,
    program_state: dict,
    transcript_window: list[TranscriptEvent],
    llm_client: Any,
    pending_guidance: str = "",
) -> CoachIntentEvent:
    """Call the session-level LLM role and return a CoachIntentEvent."""
    messages = _format_transcript_for_session(transcript_window)
    if not messages:
        messages = [{"role": "user", "content": "(session start — no turns yet)"}]

    response = llm_client.messages.create(
        model=SESSION_MODEL,
        system=_build_session_prompt(
            program, coach_profile, learner_portrait, program_state, pending_guidance
        ),
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
```

- [ ] **Step 6: Add helper `_extract_pending_guidance` and whisper endpoint to `app/api/sessions.py`**

Add this helper function before the route definitions:

```python
def _extract_pending_guidance(transcript: list[TranscriptEvent]) -> str:
    last_intent_idx = -1
    for i, e in enumerate(transcript):
        if isinstance(e, CoachIntentEvent):
            last_intent_idx = i
    whispers = [
        e for e in transcript[last_intent_idx + 1:]
        if isinstance(e, TutorInputEvent) and e.mode == "whisper"
    ]
    return "\n".join(w.content for w in whispers)
```

Add `TutorInputEvent` to the domain events import:

```python
from app.domain.events import CoachIntentEvent, LearnerTextEvent, TranscriptEvent, TutorInputEvent
```

Add a new request model and whisper endpoint:

```python
class WhisperRequest(BaseModel):
    tutor_id: str
    content: str


@router.post("/{session_id}/whisper", status_code=204)
async def post_whisper(session_id: str, body: WhisperRequest) -> None:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    tutor = await tutors_store.get(body.tutor_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    event = TutorInputEvent(mode="whisper", tutor_id=body.tutor_id, content=body.content)
    await sessions_store.append_event(session_id, event)
    await event_stream.publish(session_id, event.model_dump(mode="json"))
```

In the `session_turn` endpoint, extract pending guidance and pass it to `run_session`:

```python
    # Run session role if trigger policy fires
    if should_run_session_role(session.transcript, program_state):
        reg = registry()
        program = reg.program(session.program_id)
        if program is None:
            raise HTTPException(status_code=422, detail=f"Program '{session.program_id}' not found")
        coach_profile = reg.coach_profile(program.coach_profile_id) if program.coach_profile_id else None
        pending_guidance = _extract_pending_guidance(session.transcript)
        intent = await run_session(
            program=program,
            coach_profile=coach_profile,
            learner_portrait=learner.portrait_md,
            program_state=program_state,
            transcript_window=session.transcript,
            llm_client=session_llm,
            pending_guidance=pending_guidance,
        )
        await sessions_store.append_event(session_id, intent)
        await event_stream.publish(session_id, intent.model_dump(mode="json"))
        session = await sessions_store.get(session_id)
```

- [ ] **Step 7: Write initial `tests/api/test_tutor_channel_api.py`** (whisper tests only for now)

```python
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.roles.identity_role import get_identity_llm_client
from app.roles.session_role import get_session_llm_client
from app.roles.turn_role import get_llm_client


def _fake_turn_llm():
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(
                type="tool_use",
                input={"utterance": "Good.", "on_target": True,
                       "matched_markers": [], "affect": {}, "notes": ""},
            )])
    class _FakeLLM:
        messages = _FakeMessages()
    return _FakeLLM()


def _fake_session_llm():
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(
                type="tool_use",
                input={"goal": "warm_up", "skill_id": "add-1digit",
                       "difficulty_hint": "same", "rationale": "test"},
            )])
    class _FakeLLM:
        messages = _FakeMessages()
    return _FakeLLM()


def _fake_identity_llm():
    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(
                type="tool_use", input={"portrait_md": "Portrait."},
            )])
    class _FakeLLM:
        messages = _FakeMessages()
    return _FakeLLM()


@pytest.fixture
def client_all_fakes(client: AsyncClient):
    from app.main import app
    app.dependency_overrides[get_llm_client] = _fake_turn_llm
    app.dependency_overrides[get_session_llm_client] = _fake_session_llm
    app.dependency_overrides[get_identity_llm_client] = _fake_identity_llm
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def channel_setup(client_all_fakes: AsyncClient):
    tutor = (await client_all_fakes.post("/tutors", json={"name": "Ms. Chen"})).json()
    learner = (await client_all_fakes.post("/learners", json={"name": "Sam"})).json()
    session = (await client_all_fakes.post("/sessions", json={
        "learner_id": learner["id"], "program_id": "elementary-math",
    })).json()
    return client_all_fakes, tutor["id"], learner["id"], session["id"]


# ── Whisper tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_whisper_appended_to_transcript(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    await client.post(f"/sessions/{session_id}/whisper",
                      json={"tutor_id": tutor_id, "content": "slow down a bit"})
    session = (await client.get(f"/sessions/{session_id}")).json()
    whispers = [e for e in session["transcript"] if e["kind"] == "tutor_input" and e["mode"] == "whisper"]
    assert len(whispers) == 1
    assert whispers[0]["content"] == "slow down a bit"


@pytest.mark.asyncio
async def test_whisper_requires_valid_tutor(channel_setup) -> None:
    client, _, _, session_id = channel_setup
    resp = await client.post(f"/sessions/{session_id}/whisper",
                             json={"tutor_id": "no-such-tutor", "content": "hello"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_whisper_triggers_session_role_on_next_turn(channel_setup) -> None:
    from app.main import app
    call_count = {"n": 0}

    def _counting_session_llm():
        call_count["n"] += 1
        return _fake_session_llm()

    app.dependency_overrides[get_session_llm_client] = _counting_session_llm

    client, tutor_id, _, session_id = channel_setup
    # First turn — session role fires once at session start
    await client.post(f"/sessions/{session_id}/turn", json={"text": "hi"})
    count_after_first = call_count["n"]
    # Post a whisper
    await client.post(f"/sessions/{session_id}/whisper",
                      json={"tutor_id": tutor_id, "content": "go easier"})
    # Next turn — session role should fire again due to pending whisper
    await client.post(f"/sessions/{session_id}/turn", json={"text": "ok"})
    assert call_count["n"] > count_after_first


@pytest.mark.asyncio
async def test_whisper_content_reaches_session_role_prompt(channel_setup) -> None:
    from app.main import app
    captured = {}

    def _capturing_session_llm():
        class _FakeMessages:
            def create(self, **kwargs):
                captured["system"] = kwargs.get("system", "")
                return SimpleNamespace(content=[SimpleNamespace(
                    type="tool_use",
                    input={"goal": "teach", "skill_id": "add-1digit",
                           "difficulty_hint": "easier", "rationale": "tutor said so"},
                )])
        class _FakeLLM:
            messages = _FakeMessages()
        return _FakeLLM()

    app.dependency_overrides[get_session_llm_client] = _capturing_session_llm

    client, tutor_id, _, session_id = channel_setup
    await client.post(f"/sessions/{session_id}/whisper",
                      json={"tutor_id": tutor_id, "content": "UNIQUE_WHISPER_MARKER"})
    await client.post(f"/sessions/{session_id}/turn", json={"text": "hi"})
    assert "UNIQUE_WHISPER_MARKER" in captured.get("system", "")
```

- [ ] **Step 8: Run whisper tests**

Run:
```bash
uv run pytest tests/api/test_tutor_channel_api.py -v
```

Expected: 4 PASS.

- [ ] **Step 9: Run full suite**

Run:
```bash
uv run pytest -v 2>&1 | tail -5
```

Expected: all passing.

- [ ] **Step 10: Commit**

```bash
git add app/roles/trigger_policy.py app/roles/session_role.py app/api/sessions.py \
        tests/roles/test_trigger_policy.py tests/api/test_tutor_channel_api.py
git commit -m "feat: whisper — tutor guidance forwarded to session planner on next planning call"
```

---

## Task 3: Steer — direct intent injection

**Files:**
- Modify: `app/api/sessions.py` — add steer endpoint
- Modify: `tests/api/test_tutor_channel_api.py` — add steer tests

- [ ] **Step 1: Add steer tests to `tests/api/test_tutor_channel_api.py`**

Append to the file:

```python
# ── Steer tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_steer_injects_coach_intent(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    resp = await client.post(f"/sessions/{session_id}/steer", json={
        "tutor_id": tutor_id,
        "goal": "teach",
        "skill_id": "add-2digit-carry",
        "difficulty_hint": "easier",
        "rationale": "learner is struggling",
    })
    assert resp.status_code == 204
    session = (await client.get(f"/sessions/{session_id}")).json()
    intents = [e for e in session["transcript"] if e["kind"] == "coach_intent"]
    assert len(intents) >= 1
    last_intent = intents[-1]
    assert last_intent["goal"] == "teach"
    assert last_intent["skill_id"] == "add-2digit-carry"


@pytest.mark.asyncio
async def test_steer_used_on_next_turn(channel_setup) -> None:
    from app.main import app
    received_skill = {}

    def _capturing_turn_llm():
        class _FakeMessages:
            def create(self, **kwargs):
                # Capture what skill was in the intent that was passed
                # The intent is passed via the system prompt, not kwargs directly.
                # We capture it from the actual session transcript after the turn.
                return SimpleNamespace(content=[SimpleNamespace(
                    type="tool_use",
                    input={"utterance": "Try this.", "on_target": True,
                           "matched_markers": [], "affect": {}, "notes": ""},
                )])
        class _FakeLLM:
            messages = _FakeMessages()
        return _FakeLLM()

    app.dependency_overrides[get_llm_client] = _capturing_turn_llm

    client, tutor_id, _, session_id = channel_setup
    # Steer to a specific skill
    await client.post(f"/sessions/{session_id}/steer", json={
        "tutor_id": tutor_id, "goal": "drill", "skill_id": "add-2digit-carry",
    })
    # Do a turn — it should use the steered CoachIntentEvent
    resp = await client.post(f"/sessions/{session_id}/turn", json={"text": "ready"})
    assert resp.status_code == 200
    # The session transcript should show the steer's intent was used
    session = (await client.get(f"/sessions/{session_id}")).json()
    intents = [e for e in session["transcript"] if e["kind"] == "coach_intent"]
    assert intents[-2]["skill_id"] == "add-2digit-carry"  # the steer intent, before the next turn's potential session role replan


@pytest.mark.asyncio
async def test_steer_requires_valid_tutor(channel_setup) -> None:
    client, _, _, session_id = channel_setup
    resp = await client.post(f"/sessions/{session_id}/steer", json={
        "tutor_id": "no-such", "goal": "drill", "skill_id": "add-1digit",
    })
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to confirm failure**

Run:
```bash
uv run pytest tests/api/test_tutor_channel_api.py::test_steer_injects_coach_intent -v
```

Expected: FAIL — endpoint not found.

- [ ] **Step 3: Add steer request model and endpoint to `app/api/sessions.py`**

Add after the `WhisperRequest` model:

```python
class SteerRequest(BaseModel):
    tutor_id: str
    goal: str
    skill_id: str
    difficulty_hint: str = "same"
    rationale: str = ""
```

Add the steer endpoint after the whisper endpoint:

```python
@router.post("/{session_id}/steer", status_code=204)
async def post_steer(session_id: str, body: SteerRequest) -> None:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    tutor = await tutors_store.get(body.tutor_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    steer_log = TutorInputEvent(
        mode="steer",
        tutor_id=body.tutor_id,
        content=json.dumps({
            "goal": body.goal, "skill_id": body.skill_id,
            "difficulty_hint": body.difficulty_hint,
        }),
    )
    await sessions_store.append_event(session_id, steer_log)
    await event_stream.publish(session_id, steer_log.model_dump(mode="json"))
    intent = CoachIntentEvent(
        goal=body.goal,
        skill_id=body.skill_id,
        difficulty_hint=body.difficulty_hint,
        rationale=f"[TUTOR STEER] {body.rationale}",
    )
    await sessions_store.append_event(session_id, intent)
    await event_stream.publish(session_id, intent.model_dump(mode="json"))
```

- [ ] **Step 4: Run steer tests**

Run:
```bash
uv run pytest tests/api/test_tutor_channel_api.py -k steer -v
```

Expected: 3 PASS.

- [ ] **Step 5: Run full suite**

Run:
```bash
uv run pytest -v 2>&1 | tail -5
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add app/api/sessions.py tests/api/test_tutor_channel_api.py
git commit -m "feat: steer — tutor injects CoachIntentEvent directly, bypassing session planner"
```

---

## Task 4: Takeover / handback / tutor-turn

**Files:**
- Modify: `app/api/sessions.py` — `_is_taken_over` helper, three new endpoints, guard in `/turn`
- Modify: `tests/api/test_tutor_channel_api.py` — add takeover tests

- [ ] **Step 1: Add takeover tests to `tests/api/test_tutor_channel_api.py`**

Append to the file:

```python
# ── Takeover / handback / tutor-turn tests ───────────────────────────────────

@pytest.mark.asyncio
async def test_turn_rejected_during_takeover(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    await client.post(f"/sessions/{session_id}/takeover", json={"tutor_id": tutor_id})
    resp = await client.post(f"/sessions/{session_id}/turn", json={"text": "hi"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_tutor_turn_during_takeover(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    await client.post(f"/sessions/{session_id}/takeover", json={"tutor_id": tutor_id})
    resp = await client.post(f"/sessions/{session_id}/tutor-turn",
                             json={"tutor_id": tutor_id, "text": "Let me show you."})
    assert resp.status_code == 200
    assert resp.json()["utterance"] == "Let me show you."
    session = (await client.get(f"/sessions/{session_id}")).json()
    utterances = [e for e in session["transcript"] if e["kind"] == "utterance"]
    assert any(u["text"] == "Let me show you." for u in utterances)


@pytest.mark.asyncio
async def test_tutor_turn_outside_takeover_returns_409(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    resp = await client.post(f"/sessions/{session_id}/tutor-turn",
                             json={"tutor_id": tutor_id, "text": "hello"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_handback_restores_ai_turn(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    await client.post(f"/sessions/{session_id}/takeover", json={"tutor_id": tutor_id})
    await client.post(f"/sessions/{session_id}/handback", json={"tutor_id": tutor_id})
    resp = await client.post(f"/sessions/{session_id}/turn", json={"text": "back to AI"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_takeover_requires_valid_tutor(channel_setup) -> None:
    client, _, _, session_id = channel_setup
    resp = await client.post(f"/sessions/{session_id}/takeover", json={"tutor_id": "ghost"})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to confirm failure**

Run:
```bash
uv run pytest tests/api/test_tutor_channel_api.py -k takeover or handback -v
```

Expected: FAIL — endpoints missing.

- [ ] **Step 3: Add `_is_taken_over` helper and three endpoints to `app/api/sessions.py`**

Add this helper before the route definitions (after `_extract_pending_guidance`):

```python
def _is_taken_over(transcript: list[TranscriptEvent]) -> bool:
    """Scan from the end; return True if the last tutor mode event is takeover."""
    for event in reversed(transcript):
        if isinstance(event, TutorInputEvent):
            if event.mode == "takeover":
                return True
            if event.mode == "handback":
                return False
    return False
```

Add request models:

```python
class TakeoverRequest(BaseModel):
    tutor_id: str


class TutorTurnRequest(BaseModel):
    tutor_id: str
    text: str
```

Add the three endpoints after the steer endpoint:

```python
@router.post("/{session_id}/takeover", status_code=204)
async def takeover_session(session_id: str, body: TakeoverRequest) -> None:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    tutor = await tutors_store.get(body.tutor_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    event = TutorInputEvent(mode="takeover", tutor_id=body.tutor_id, content="")
    await sessions_store.append_event(session_id, event)
    await event_stream.publish(session_id, event.model_dump(mode="json"))


@router.post("/{session_id}/handback", status_code=204)
async def handback_session(session_id: str, body: TakeoverRequest) -> None:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    tutor = await tutors_store.get(body.tutor_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    event = TutorInputEvent(mode="handback", tutor_id=body.tutor_id, content="")
    await sessions_store.append_event(session_id, event)
    await event_stream.publish(session_id, event.model_dump(mode="json"))


@router.post("/{session_id}/tutor-turn", response_model=TurnResponse)
async def tutor_turn(session_id: str, body: TutorTurnRequest) -> TurnResponse:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    tutor = await tutors_store.get(body.tutor_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    if not _is_taken_over(session.transcript):
        raise HTTPException(status_code=409, detail="Session is not in takeover mode")
    utterance = UtteranceEvent(text=body.text)
    await sessions_store.append_event(session_id, utterance)
    await event_stream.publish(session_id, utterance.model_dump(mode="json"))
    return TurnResponse(
        utterance=body.text,
        turn_signal={"kind": "turn_signal", "on_target": True,
                     "matched_markers": [], "affect": {}, "notes": ""},
    )
```

Add the import for `UtteranceEvent` to the events import in sessions.py:

```python
from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TranscriptEvent,
    TutorInputEvent,
    UtteranceEvent,
)
```

Add the takeover guard at the top of `session_turn`, after loading the session:

```python
    if _is_taken_over(session.transcript):
        raise HTTPException(
            status_code=409,
            detail="Session is taken over by tutor; use /tutor-turn instead",
        )
```

- [ ] **Step 4: Run takeover tests**

Run:
```bash
uv run pytest tests/api/test_tutor_channel_api.py -k "takeover or handback or tutor_turn" -v
```

Expected: 5 PASS.

- [ ] **Step 5: Run full suite**

Run:
```bash
uv run pytest -v 2>&1 | tail -5
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add app/api/sessions.py tests/api/test_tutor_channel_api.py
git commit -m "feat: takeover/handback/tutor-turn — tutor can pause AI roles and type directly"
```

---

## Task 5: Async annotations

**Files:**
- Modify: `app/api/sessions.py` — add annotate endpoint
- Modify: `tests/api/test_tutor_channel_api.py` — add annotation tests

- [ ] **Step 1: Add annotation tests to `tests/api/test_tutor_channel_api.py`**

Append to the file:

```python
# ── Annotation tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_annotation_appended_to_transcript(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    # Put something in the transcript to annotate
    await client.post(f"/sessions/{session_id}/turn", json={"text": "5"})
    session = (await client.get(f"/sessions/{session_id}")).json()
    turn_idx = 0  # annotate the first event

    resp = await client.post(
        f"/sessions/{session_id}/turns/{turn_idx}/annotate",
        json={"tutor_id": tutor_id, "text": "Learner hesitated here"},
    )
    assert resp.status_code == 204

    session = (await client.get(f"/sessions/{session_id}")).json()
    annotations = [
        e for e in session["transcript"]
        if e["kind"] == "tutor_input" and e["mode"] == "annotation"
    ]
    assert len(annotations) == 1
    assert annotations[0]["content"] == "Learner hesitated here"
    assert annotations[0]["target_turn_idx"] == turn_idx


@pytest.mark.asyncio
async def test_annotation_out_of_range_returns_422(channel_setup) -> None:
    client, tutor_id, _, session_id = channel_setup
    resp = await client.post(
        f"/sessions/{session_id}/turns/9999/annotate",
        json={"tutor_id": tutor_id, "text": "out of range"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_annotation_requires_valid_tutor(channel_setup) -> None:
    client, _, _, session_id = channel_setup
    resp = await client.post(
        f"/sessions/{session_id}/turns/0/annotate",
        json={"tutor_id": "ghost", "text": "who am I"},
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to confirm failure**

Run:
```bash
uv run pytest tests/api/test_tutor_channel_api.py -k annotate -v
```

Expected: FAIL — endpoint not found.

- [ ] **Step 3: Add annotation request model and endpoint to `app/api/sessions.py`**

Add request model:

```python
class AnnotateRequest(BaseModel):
    tutor_id: str
    text: str
```

Add the endpoint after the tutor-turn endpoint:

```python
@router.post("/{session_id}/turns/{turn_idx}/annotate", status_code=204)
async def annotate_turn(session_id: str, turn_idx: int, body: AnnotateRequest) -> None:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    tutor = await tutors_store.get(body.tutor_id)
    if tutor is None:
        raise HTTPException(status_code=404, detail="Tutor not found")
    if turn_idx < 0 or turn_idx >= len(session.transcript):
        raise HTTPException(status_code=422, detail="turn_idx out of range")
    event = TutorInputEvent(
        mode="annotation",
        tutor_id=body.tutor_id,
        content=body.text,
        target_turn_idx=turn_idx,
    )
    await sessions_store.append_event(session_id, event)
    await event_stream.publish(session_id, event.model_dump(mode="json"))
```

- [ ] **Step 4: Run annotation tests**

Run:
```bash
uv run pytest tests/api/test_tutor_channel_api.py -k annotate -v
```

Expected: 3 PASS.

- [ ] **Step 5: Run full suite**

Run:
```bash
uv run pytest -v 2>&1 | tail -5
```

Expected: all passing.

- [ ] **Step 6: Commit and push**

```bash
git add app/api/sessions.py tests/api/test_tutor_channel_api.py
git commit -m "feat: async turn annotations — tutor can comment on specific transcript events"
git push origin tutoring-platform-v1
```

---

## Self-Review

**Spec coverage:**

| Phase 5 requirement | Task |
|---|---|
| Tutor identity is its own record | Task 0 — `tutors` table, model, store, API |
| Observe (real-time event stream) | Task 1 — SSE `/stream` + pub/sub; all events published |
| Whisper — guidance to session planner | Task 2 — POST `/whisper`; forwarded via `pending_guidance` |
| Session role fires on pending whisper | Task 2 — trigger policy updated |
| Steer — direct intent injection, bypasses session role | Task 3 — POST `/steer` → CoachIntentEvent appended directly |
| Takeover — pause AI roles | Task 4 — POST `/takeover`; `/turn` returns 409 while taken over |
| Handback — resume AI roles | Task 4 — POST `/handback`; `/turn` works again |
| Tutor types directly to learner during takeover | Task 4 — POST `/tutor-turn` → UtteranceEvent |
| Async annotations on past turns | Task 5 — POST `/turns/{idx}/annotate` |
| No special branches in main path | ✓ — all modes log to transcript; main turn path just checks `_is_taken_over` |

**Placeholder scan:** None found. All endpoints and test assertions are complete.

**Type consistency:**
- `TutorInputEvent(mode=..., tutor_id=..., content=..., target_turn_idx=...)` — consistent throughout ✓
- `_is_taken_over(transcript) -> bool` — consistent between helper definition and tests ✓
- `run_session(..., pending_guidance: str = "")` — consistent in signature, call site, and test assertions ✓
