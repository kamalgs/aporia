from datetime import datetime

from pydantic import BaseModel


class LearnerCreate(BaseModel):
    name: str
    cohort_tags: list[str] = []


class Learner(BaseModel):
    id: str
    name: str
    cohort_tags: list[str]
    portrait_md: str
    traits: dict
    program_states: dict
    created_at: datetime
    updated_at: datetime
