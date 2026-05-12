from datetime import datetime, timezone
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _EventBase(BaseModel):
    created_at: datetime = Field(default_factory=_now)


class LearnerTextEvent(_EventBase):
    kind: Literal["learner_text"] = "learner_text"
    text: str


class UtteranceEvent(_EventBase):
    kind: Literal["utterance"] = "utterance"
    text: str
    skill_id: str | None = None


class CoachIntentEvent(_EventBase):
    kind: Literal["coach_intent"] = "coach_intent"
    goal: str
    skill_id: str | None = None
    difficulty_hint: str | None = None
    rationale: str = ""
    tone_note: str | None = None


class TurnSignalEvent(_EventBase):
    kind: Literal["turn_signal"] = "turn_signal"
    on_target: bool
    matched_markers: list[str] = Field(default_factory=list)
    affect: dict[str, float] = Field(default_factory=dict)
    notes: str = ""


class TutorInputEvent(_EventBase):
    kind: Literal["tutor_input"] = "tutor_input"
    mode: Literal["whisper", "steer", "takeover", "annotation"]
    tutor_id: str
    content: str
    target_turn_idx: int | None = None


TranscriptEvent = Annotated[
    Union[
        LearnerTextEvent,
        UtteranceEvent,
        CoachIntentEvent,
        TurnSignalEvent,
        TutorInputEvent,
    ],
    Field(discriminator="kind"),
]
