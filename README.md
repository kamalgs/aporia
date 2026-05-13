# AI Tutor Platform

An AI-powered tutoring platform with a three-role LLM architecture, human tutor oversight, and PostgreSQL persistence.

## Architecture overview

Three specialised LLM roles handle different time horizons:

- **Turn role** (Claude Haiku) — responds to each learner message in real time
- **Session role** (Claude Sonnet) — decides the pedagogical goal for the next stretch of turns
- **Identity role** (Claude Sonnet) — updates a durable learner portrait at session end

A **speculation cache** pre-generates responses for each known mistake pattern immediately after a turn, so the next response is ready before the learner types it.

A **human tutor channel** lets a human override, guide, or take over any session via whisper, steer, takeover, handback, and annotate endpoints.

See `docs/architecture.md` and `docs/design.md` for full details.

## Prerequisites

- Python 3.12+
- PostgreSQL 14+ (or Docker for development)
- An Anthropic API key

## Getting started

### 1. Clone and install

```bash
git clone <repo-url>
cd tutor
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 2. Configure environment

Copy the example and fill in your values:

```bash
cp .env.example .env
```

`.env` keys:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://tutor:tutor@localhost:5432/tutor` | PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | _(required)_ | Anthropic API key |
| `CONTENT_DIR` | `content` | Path to the content directory |

### 3. Start PostgreSQL

Using Docker:

```bash
docker run -d --name tutor-pg \
  -e POSTGRES_USER=tutor \
  -e POSTGRES_PASSWORD=tutor \
  -e POSTGRES_DB=tutor \
  -p 5432:5432 postgres:16-alpine
```

### 4. Run the server

```bash
uvicorn app.main:app --reload
```

Migrations run automatically on startup. The API is available at `http://localhost:8000`.

Interactive API docs: `http://localhost:8000/docs`

## Running tests

```bash
# Unit and integration tests (requires Docker for PostgreSQL via testcontainers)
pytest

# Live LLM smoke tests (requires FIREWORKS_API_KEY)
FIREWORKS_API_KEY=<key> pytest -m smoke
```

## Adding content

Skills, programs, coach profiles, and guardian profiles are loaded from the `content/` directory as Markdown files with YAML frontmatter. See existing files in `content/skills/`, `content/programs/`, etc. for the format.

## API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/learners` | Create a learner |
| `GET` | `/learners/{id}` | Get learner (includes portrait and program states) |
| `POST` | `/sessions` | Start a session |
| `GET` | `/sessions/{id}` | Get session (includes transcript) |
| `POST` | `/sessions/{id}/turn` | Submit a learner message, get AI response |
| `POST` | `/sessions/{id}/turn/stream` | Same, streamed as SSE |
| `POST` | `/sessions/{id}/end` | End session and update learner portrait |
| `GET` | `/sessions/{id}/stream` | SSE stream of session events |
| `POST` | `/sessions/{id}/events` | Append a raw event (for seeding/testing) |
| `POST` | `/sessions/{id}/whisper` | Human tutor sends background guidance |
| `POST` | `/sessions/{id}/steer` | Human tutor overrides the coaching intent |
| `POST` | `/sessions/{id}/takeover` | Human tutor takes over the session |
| `POST` | `/sessions/{id}/handback` | Return control to AI after takeover |
| `POST` | `/sessions/{id}/tutor-turn` | Human tutor sends a turn during takeover |
| `POST` | `/sessions/{id}/turns/{idx}/annotate` | Annotate a past turn |
| `GET` | `/content/skills` | List skills |
| `GET` | `/content/programs` | List programs |
