# ADR 003: Transcript as State

## Context
A traditional tutoring system might store a `StudentProfile` with fields like `carry_skill: 0.7`. This is brittle — new misconceptions require schema migrations.

## Decision
The only persisted state is the ordered list of turns (who said what, and the evaluation of each answer). The agent receives the full transcript on every call and infers what to do next.

## Consequences
- **Positive:** LLM context naturally includes the whole conversation. No hidden state means debugging is just reading the transcript.
- **Negative:** LLM context window limits session length. In-memory store means sessions evaporate on server restart (acceptable for MVP).
