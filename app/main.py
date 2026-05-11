from __future__ import annotations
import os
from typing import Annotated

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # default Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_agent() -> TutorAgent:
    model = os.environ.get("TUTOR_MODEL")
    if model:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("TUTOR_MODEL is set but OPENROUTER_API_KEY is missing")
        return LlmAgent(model_name=model, api_key=key)
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

    store.append(
        session_id,
        TurnData(role="student", answer=payload),
    )
    # agent sees the updated history
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
