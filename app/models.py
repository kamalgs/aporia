from __future__ import annotations

from typing import Literal, List
from pydantic import BaseModel, Field


class Problem(BaseModel):
    operation: Literal["add"] = "add"
    a: int
    b: int


class Evaluation(BaseModel):
    is_correct: bool
    misconceptions: List[str] = Field(default_factory=list)
    hint: str


class TutorStep(BaseModel):
    feedback: str
    evaluation: Evaluation
    question: Problem | None = None
    phase: Literal["diagnostic", "targeted", "mastery", "complete"]
    needs_human: bool = False  # true when student is stuck after repeated wrong answers


class StudentAnswerPayload(BaseModel):
    text: str  # free-form student message (answer + explanation)
    value: int | None = None  # parsed numeric answer (optional — backend extracts if missing)


class TurnData(BaseModel):
    role: Literal["tutor", "student"]
    question: Problem | None = None
    answer: StudentAnswerPayload | None = None
    feedback: str | None = None
    evaluation: Evaluation | None = None


class SessionState(BaseModel):
    session_id: str
    turns: List[TurnData]
    current_step: TutorStep | None = None


class SessionCreatedResponse(BaseModel):
    session_id: str
    step: TutorStep
