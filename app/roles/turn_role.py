from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.anthropic import AnthropicModel

from app.domain.content import Skill
from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TranscriptEvent,
    TurnSignalEvent,
    UtteranceEvent,
)

TURN_MODEL = "claude-haiku-4-5-20251001"
TRANSCRIPT_WINDOW_SIZE = 10


class TurnOutput(BaseModel):
    utterance: str
    on_target: bool
    matched_markers: list[str] = Field(default_factory=list)
    affect: dict[str, float] = Field(default_factory=dict)
    notes: str = ""


@dataclass
class TurnDeps:
    intent: CoachIntentEvent
    skill: Skill


_turn_agent: Agent[TurnDeps, TurnOutput] = Agent(
    AnthropicModel(TURN_MODEL),
    output_type=TurnOutput,
    deps_type=TurnDeps,
)


@_turn_agent.instructions
def _turn_instructions(ctx: RunContext[TurnDeps]) -> str:
    intent = ctx.deps.intent
    skill = ctx.deps.skill
    mistakes = "\n".join(f"- {m}" for m in skill.common_mistakes) or "None documented."
    lines = [
        "You are a skilled tutor working one-on-one with a learner on the following skill.",
        "",
        f"SKILL: {skill.title}",
        f"OBJECTIVE: {skill.objective}",
        f"MASTERY LOOKS LIKE: {skill.mastery_description}",
        "",
        "COMMON MISTAKES TO WATCH FOR:",
        mistakes,
        "",
        "CURRENT INTENT:",
        f"  Goal: {intent.goal}",
        f"  Skill: {intent.skill_id or skill.id}",
    ]
    if intent.difficulty_hint:
        lines.append(f"  Difficulty: {intent.difficulty_hint}")
    if intent.tone_note:
        lines.append(f"  Tone: {intent.tone_note}")
    lines += [
        "",
        "Respond with your next message and assessment of the learner's response.",
        "Keep responses short — one or two sentences maximum.",
        "If the learner's input is their first message, greet them briefly and ask an opening question.",
    ]
    return "\n".join(lines)


def _transcript_to_messages(window: list[TranscriptEvent]) -> list[ModelMessage]:
    messages: list[ModelMessage] = []
    for event in window:
        if isinstance(event, LearnerTextEvent):
            messages.append(ModelRequest(parts=[UserPromptPart(content=event.text)]))
        elif isinstance(event, UtteranceEvent):
            messages.append(ModelResponse(parts=[TextPart(content=event.text)]))
    return messages


async def run_turn(
    intent: CoachIntentEvent,
    skill: Skill,
    transcript_window: list[TranscriptEvent],
    learner_text: str,
    model: Any = None,
) -> tuple[UtteranceEvent, TurnSignalEvent]:
    window = transcript_window[-TRANSCRIPT_WINDOW_SIZE:]
    history = _transcript_to_messages(window)
    deps = TurnDeps(intent=intent, skill=skill)
    kwargs: dict[str, Any] = dict(
        message_history=history,
        deps=deps,
    )
    if model is not None:
        kwargs["model"] = model

    result = await _turn_agent.run(learner_text or "(no input)", **kwargs)
    out = result.output
    utterance = UtteranceEvent(text=out.utterance, skill_id=skill.id)
    signal = TurnSignalEvent(
        on_target=out.on_target,
        matched_markers=out.matched_markers,
        affect=out.affect,
        notes=out.notes,
    )
    return utterance, signal


async def run_turn_for_speculation(
    intent: CoachIntentEvent,
    skill: Skill,
    mistake_text: str,
    model: Any = None,
) -> str:
    deps = TurnDeps(intent=intent, skill=skill)
    kwargs: dict[str, Any] = dict(deps=deps)
    if model is not None:
        kwargs["model"] = model

    result = await _turn_agent.run(mistake_text, **kwargs)
    return result.output.utterance


def get_turn_model() -> AnthropicModel:
    return AnthropicModel(TURN_MODEL)
