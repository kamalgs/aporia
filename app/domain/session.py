from datetime import datetime
from typing import Annotated, Union

from pydantic import BaseModel, Field

from app.domain.events import TranscriptEvent


class SessionCreate(BaseModel):
    learner_id: str
    program_id: str


class Session(BaseModel):
    id: str
    learner_id: str
    program_id: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    transcript: list[TranscriptEvent]
    summary_md: str
