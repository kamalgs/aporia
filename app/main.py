from __future__ import annotations
import os
from typing import Annotated

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.agent import TutorAgent, LlmAgent, FakeAgent
from app.models import (
    StudentAnswerPayload,
    TutorStep,
    TurnData,
    SessionState,
    SessionCreatedResponse,
)
from app.session_store import SessionStore, get_store

app = FastAPI(title="Socratic Tutor")

# CORS only needed in local dev; Caddy handles prod.
if os.environ.get("ENV", "dev") == "dev":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _pick_llm_agent() -> LlmAgent:
    # Fireworks (frontier-class models, OpenAI-compatible)
    fw_key = os.environ.get("FIREWORKS_API_KEY")
    fw_model = os.environ.get("FIREWORKS_MODEL")
    if fw_key and fw_model:
        return LlmAgent(
            model_name=fw_model,
            api_key=fw_key,
            base_url="https://api.fireworks.ai/inference/v1",
        )

    # OpenRouter fallback
    or_key = os.environ.get("OPENROUTER_API_KEY")
    or_model = os.environ.get("TUTOR_MODEL")
    if or_key and or_model:
        return LlmAgent(
            model_name=or_model,
            api_key=or_key,
            base_url="https://openrouter.ai/api/v1",
        )

    raise RuntimeError(
        "No LLM credentials configured. Set FIREWORKS_API_KEY + FIREWORKS_MODEL, "
        "or OPENROUTER_API_KEY + TUTOR_MODEL."
    )


def get_agent() -> TutorAgent:
    # Use FakeAgent unless an LLM env var is set.
    if os.environ.get("TUTOR_MODEL") or os.environ.get("FIREWORKS_MODEL"):
        return _pick_llm_agent()
    return FakeAgent()


@app.post("/sessions", response_model=SessionCreatedResponse)
async def create_session(
    agent: Annotated[TutorAgent, Depends(get_agent)],
    store: Annotated[SessionStore, Depends(get_store)],
):
    step = await agent.start()
    session_id = store.create()
    store.append(
        session_id,
        TurnData(role="tutor", question=step.question, feedback=step.feedback, evaluation=step.evaluation),
    )
    return SessionCreatedResponse(session_id=session_id, step=step)


@app.post("/sessions/{session_id}/answer", response_model=TutorStep)
async def submit_answer(
    session_id: str,
    payload: StudentAnswerPayload,
    agent: Annotated[TutorAgent, Depends(get_agent)],
    store: Annotated[SessionStore, Depends(get_store)],
):
    history = store.all_turns(session_id)
    if not history:
        raise HTTPException(status_code=404, detail="Session not found or empty")

    store.append(session_id, TurnData(role="student", answer=payload))
    updated_history = store.all_turns(session_id)
    step = await agent.next(updated_history)

    store.append(
        session_id,
        TurnData(
            role="tutor",
            question=step.question,
            feedback=step.feedback,
            evaluation=step.evaluation,
        ),
    )
    return step


@app.get("/sessions/{session_id}", response_model=SessionState)
async def get_session(
    session_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    turns = store.get(session_id)
    if turns is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionState(session_id=session_id, turns=turns, current_step=None)


# ═══════════════════════════════════════════════════════════════════════════════
# Static frontend (SPA) — mounted last so API routes take precedence.
# ═══════════════════════════════════════════════════════════════════════════════
_static_dir = os.environ.get("FRONTEND_STATIC_DIR", os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))

if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="assets")

    @app.get("/{path:path}")
    async def spa_catch_all(path: str):
        # All non-API routes serve index.html for client-side routing.
        index = os.path.join(_static_dir, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        raise HTTPException(status_code=404)
