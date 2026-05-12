from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.domain.events import TranscriptEvent
from app.domain.session import Session, SessionCreate
from app.store import sessions as sessions_store

router = APIRouter(prefix="/sessions", tags=["sessions"])


class AppendEventRequest(BaseModel):
    event: TranscriptEvent


class EndSessionRequest(BaseModel):
    summary_md: str = ""


@router.post("", response_model=Session, status_code=201)
async def create_session(body: SessionCreate) -> Session:
    return await sessions_store.insert(body)


@router.get("/{session_id}", response_model=Session)
async def get_session(session_id: str) -> Session:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/{session_id}/events", status_code=204)
async def append_event(session_id: str, body: AppendEventRequest) -> None:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await sessions_store.append_event(session_id, body.event)


@router.post("/{session_id}/end", response_model=Session)
async def end_session(session_id: str, body: EndSessionRequest) -> Session:
    session = await sessions_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return await sessions_store.end(session_id, body.summary_md)
