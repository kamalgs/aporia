# Architecture

## Layers

```
┌─────────────────────────────────────────┐
│  React UI (Vite)                        │
│  Chat view → REST calls                 │
└──────────────┬──────────────────────────┘
               │ HTTP
┌──────────────▼──────────────────────────┐
│  FastAPI                                │
│  /sessions  /sessions/{id}/answer       │
│  Stateless routes, thin orchestration   │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  SessionStore (in-memory)               │
│  List of Turn objects per session_id    │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  TutorAgent                             │
│  LlmAgent  (PydanticAI + OpenRouter)    │
│  FakeAgent (deterministic, for tests)   │
└─────────────────────────────────────────┘
```

## Key principle: agent sees history, decides next step

The backend keeps **zero business logic** about pacing, diagnosis, or pedagogy. It only:
1. Persists the transcript (question → answer → feedback).
2. Hands the transcript to the agent.
3. Returns whatever structured step the agent produces.

This means the "brain" can be swapped out (deterministic fake in tests, LLM in production) without touching routes, storage, or UI.

## Data flow

```
POST /sessions
  → TutorAgent.start()
  → TutorStep { new_question }
  → store.append(tutor_turn)
  → return { session_id, step }

POST /sessions/{id}/answer
  → store.append(student_turn)
  → TutorAgent.next(full_history)
  → TutorStep { evaluation, next_question? }
  → store.append(tutor_turn)
  → return step
```

## Two-agent strategy

| Concern | FakeAgent | LlmAgent |
|---------|-----------|----------|
| Purpose | Cheap, repeatable tests | Production intelligence |
| Structure | Hand-coded rule engine | PydanticAI `result_type=TutorStep` |
| Cost | Free | ~$0.001–0.005 / call |
| Speed | Instant | Network latency |
| Enabled when | `TUTOR_MODEL` is unset | `TUTOR_MODEL` and `OPENROUTER_API_KEY` are set |
