# Architecture

## Overview

The platform is a FastAPI application backed by PostgreSQL. All AI work is done by three specialised LLM roles implemented with PydanticAI agents.

```
Client
  │
  ▼
FastAPI (app/api/)
  │
  ├── Turn endpoint  ──► Turn Role (Haiku)     ──► UtteranceEvent + TurnSignalEvent
  │                        ▲
  │                        └── Speculation Cache (pre-generated mistake responses)
  │
  ├── Session role trigger ──► Session Role (Sonnet) ──► CoachIntentEvent
  │
  └── End session  ──► Identity Role (Sonnet)  ──► updated learner portrait
  │
PostgreSQL (sessions, learners, tutors)
```

## Three LLM roles

### Turn role (`app/roles/turn_role.py`)
- Model: Claude Haiku (fast, cheap)
- Triggered: every time a learner submits text
- Input: current `CoachIntentEvent`, skill definition, recent transcript window (last 10 events), learner text
- Output: `TurnOutput` — utterance text, `on_target` bool, matched mistake markers, affect scores
- The output is split into two transcript events: `UtteranceEvent` and `TurnSignalEvent`

### Session role (`app/roles/session_role.py`)
- Model: Claude Sonnet
- Triggered: by `trigger_policy.py` — fires on first turn, after mastery/struggle thresholds, or when a human whisper is pending
- Input: program definition, coach profile, learner portrait, per-skill program state, recent transcript window (last 20 events), pending whisper guidance
- Output: `CoachIntentEvent` — goal, skill_id, difficulty_hint, rationale, tone_note
- Goals: `warm_up`, `probe`, `teach`, `drill`, `consolidate`, `rest`, `wrap`

### Identity role (`app/roles/identity_role.py`)
- Model: Claude Sonnet
- Triggered: when a session is ended via `POST /sessions/{id}/end`
- Input: program, guardian profile (cohort), prior learner portrait, program state, full session transcript
- Output: updated `portrait_md` string, stored on the `Learner` record

## Transcript as state

All session state is stored as a typed event log in `sessions.transcript`. The event types are defined in `app/domain/events.py`:

| Event type | Kind | Description |
|---|---|---|
| `CoachIntentEvent` | `coach_intent` | Session role decision |
| `UtteranceEvent` | `utterance` | AI (or tutor) message to learner |
| `LearnerTextEvent` | `learner_text` | Learner's raw input |
| `TurnSignalEvent` | `turn_signal` | Turn role assessment |
| `TutorInputEvent` | `tutor_input` | Human tutor intervention (whisper, steer, takeover, etc.) |

There is no separate mutable state object — the roles derive everything they need by scanning the transcript.

## Speculation cache (`app/speculation.py`)

After each turn the server fires an async background task (`_speculate_branches`) that pre-generates responses for every common mistake defined on the current skill. These are stored in an in-memory LRU-style cache keyed by `(session_id, skill_id, goal, difficulty, mistake_idx)`.

On the next turn, before calling the LLM, the server checks the cache. If the learner's text matches a known mistake and there is a cached response, it is returned immediately (sub-millisecond) without an LLM call.

## Human tutor channel

A human supervisor can interact with any active session:

| Endpoint | Effect |
|---|---|
| `POST /whisper` | Appends a `TutorInputEvent(mode="whisper")` — the session role reads pending whispers in its next prompt |
| `POST /steer` | Appends a `TutorInputEvent(mode="steer")` and a new `CoachIntentEvent` directly |
| `POST /takeover` | Appends `TutorInputEvent(mode="takeover")` — blocks AI `/turn` endpoint |
| `POST /handback` | Appends `TutorInputEvent(mode="handback")` — re-enables AI turns |
| `POST /tutor-turn` | Human sends an utterance while in takeover mode |
| `POST /turns/{idx}/annotate` | Appends a retrospective annotation on any turn |

## Content registry (`app/content_registry/`)

Skills, programs, coach profiles, and guardian profiles are loaded from Markdown files with YAML frontmatter in the `content/` directory. The registry is initialised once at startup and held in memory. It is read-only at runtime.

## Persistence

PostgreSQL via `psycopg` (async). Two tables:

- `sessions` — id, learner_id, program_id, status, transcript (JSON), ended_at, summary_md
- `learners` — id, name, cohort_tags, portrait_md, program_states (JSON)

Migrations are managed with Alembic and run automatically on startup.

## Event stream (`app/event_stream.py`)

`GET /sessions/{id}/stream` returns a Server-Sent Events stream. New events are published to in-memory asyncio queues via `event_stream.publish()`. The stream replays the full transcript on connect, then delivers live events.
