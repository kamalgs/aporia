# ADR 002: FakeAgent + LlmAgent

## Context
Testing an LLM-based API is expensive, slow, and flaky. We need fast deterministic tests and a cheap way to demo the system offline.

## Decision
Provide two `TutorAgent` implementations:
- `FakeAgent` — deterministic, rule-based, used when no API key is configured.
- `LlmAgent` — calls the real model, used when `TUTOR_MODEL` and `OPENROUTER_API_KEY` are set.

Both speak the same `TutorStep` contract, so routes, tests, and UI are unchanged.

## Consequences
- **Positive:** Tests run offline and instantly. Production can still use a real model without branching code.
- **Negative:** `FakeAgent` must stay in sync with `LlmAgent` logic. The two can diverge on edge-case diagnoses.
