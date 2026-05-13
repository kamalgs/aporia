# Design

## Domain model

### Content (read-only, loaded from `content/`)

- **Skill** — a single learnable unit: id, title, objective, mastery description, list of common mistakes
- **Program** — an ordered set of skills with assessment criteria and a coach profile
- **CoachProfile** — tone and pacing personality for a program (e.g. "Patient Encourager")
- **GuardianProfile** — describes a learner cohort (e.g. "Child aged 7–9") with raw guidance for the AI

### Learner state (persisted)

- **Learner** — name, cohort tags, `portrait_md` (free-text narrative updated each session), `program_states` (JSON map of program_id → skill_id → `{consecutive_correct, consecutive_wrong, ...}`)

### Session state (persisted as event log)

Every action in a session appends a typed event to `sessions.transcript`. The full list of event types is in `app/domain/events.py`. The session role and turn role derive all necessary context by reading the transcript directly — there is no derived state object.

## Session flow

```
[Start session]
       │
       ▼
[Learner submits text]
       │
       ├──► [Session role?] ──yes──► CoachIntentEvent appended
       │         (trigger policy)
       │
       ▼
[LearnerTextEvent appended]
       │
       ▼
[Check speculation cache]
       │
       ├── hit ──► return cached utterance + signal immediately
       │
       └── miss ──► Turn role LLM call
                          │
                          ▼
               UtteranceEvent + TurnSignalEvent appended
                          │
                          ▼
               Update learner program state
                          │
                          ▼
               Background: speculate mistake branches
```

## Session role trigger policy (`app/roles/trigger_policy.py`)

The session role re-runs when any of these conditions are detected in the transcript:

1. No `CoachIntentEvent` exists yet (start of session)
2. A `TutorInputEvent(mode="whisper")` was appended after the last intent (human guidance pending)
3. Three consecutive `TurnSignalEvent(on_target=True)` since the last intent (mastery signal)
4. Three consecutive `TurnSignalEvent(on_target=False)` since the last intent (struggle signal)

## Skill system

Skills are defined in `content/skills/` as Markdown files. The key fields:

```yaml
---
id: add-2digit-carry
title: Two-digit addition with carrying
objective: Add two 2-digit numbers that require carrying.
mastery_description: Student solves 5 in a row correctly.
common_mistakes:
  - "Forgetting to carry — adds ones correctly but ignores carry (e.g. 47+36 = 73 instead of 83)"
  - "Wrong carry amount — carries 2 instead of 1"
---
```

The `common_mistakes` list drives both the turn role's error detection and the speculation cache's pre-generation.

## Learner portrait

The identity role maintains a free-text `portrait_md` for each learner. It is updated at the end of every session. The portrait:

- summarises which skills feel automatic and which are still developing
- notes specific error patterns observed
- records how the learner responds to feedback
- informs the session role's goal selection in future sessions

The identity role receives the prior portrait as context, so information accumulates across sessions.

## PydanticAI agents

All three roles use `pydantic_ai.Agent` with:

- `output_type` — a Pydantic model that defines the structured output schema
- `deps_type` — a dataclass of dependencies injected at call time
- `@agent.instructions` — a dynamic system prompt built from the deps

This pattern makes each role independently testable using `FunctionModel` (no real LLM calls needed in unit/integration tests).

## Testing strategy

- **Unit tests** (`tests/roles/`, `tests/domain/`, `tests/store/`) — test business logic in isolation using `FunctionModel` fakes or direct function calls
- **Integration tests** (`tests/api/`) — full HTTP tests against a real PostgreSQL instance (via testcontainers), with all three LLM roles replaced by deterministic `FunctionModel` fakes
- **Smoke tests** (`tests/smoke/`) — live calls against Fireworks-hosted DeepSeek-V4-Pro; skipped unless `FIREWORKS_API_KEY` is set

Shared fake model factories live in `tests/api/helpers.py`.
