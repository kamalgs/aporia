# Aporia — Socratic Arithmetic Tutor

A back-and-forth AI tutor that teaches elementary arithmetic (starting with 2-digit addition and carrying) using the Socratic method. The tutor asks questions, evaluates answers, and adapts the difficulty based on diagnosed misconceptions.

## What's inside

```
aporia/
├── app/                  FastAPI backend — tutor agent, session store, REST API
├── frontend/             Vite + React — minimal chat UI
├── test/                 Black-box API tests
├── docs/                 PRD, architecture, design overview
└── adr/                  Architecture Decision Records
```

## Quick start

**Prerequisites:** Python 3.12+, `uv`, Node 20+

**1. Backend**
```bash
uv sync --extra dev
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**2. Frontend**
```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

**3. Tests**
```bash
uv run pytest -v
```

## Wiring up a real LLM (optional)

By default the server runs a deterministic `FakeAgent` so it works offline. To use a live model via OpenRouter:

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
export TUTOR_MODEL=openai/gpt-4o-mini
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API

| Endpoint | Method | Body | Response |
|----------|--------|------|----------|
| `/sessions` | `POST` | — | `{ session_id, step }` |
| `/sessions/{id}/answer` | `POST` | `{ value: number, explanation?: string }` | `TutorStep` |
| `/sessions/{id}` | `GET` | — | full session history |

A `TutorStep` contains:
- `feedback` — what the tutor says to the student
- `evaluation` — whether the last answer was correct and any diagnosed misconceptions
- `question` — the next problem (or `null` if complete)
- `phase` — `diagnostic` → `targeted` → `mastery` → `complete`
