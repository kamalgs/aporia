from datetime import datetime

from pydantic import BaseModel


class TutorCreate(BaseModel):
    name: str


class Tutor(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
