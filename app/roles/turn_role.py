from typing import Any

from anthropic import Anthropic

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

_EMIT_TURN_TOOL: dict[str, Any] = {
    "name": "emit_turn",
    "description": "Emit your next message to the learner and record your assessment of their response.",
    "input_schema": {
        "type": "object",
        "properties": {
            "utterance": {
                "type": "string",
                "description": "The next message to send to the learner.",
            },
            "on_target": {
                "type": "boolean",
                "description": "True if the learner's response was correct or on-track.",
            },
            "matched_markers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Names of common mistake patterns that match the learner's response.",
            },
            "affect": {
                "type": "object",
                "description": "Observed affective signals as float scores, e.g. {'confidence': 0.7}.",
            },
            "notes": {
                "type": "string",
                "description": "Optional free-form notes about this turn.",
            },
        },
        "required": ["utterance", "on_target"],
    },
}


def _format_transcript(window: list[TranscriptEvent]) -> list[dict[str, str]]:
    messages = []
    for event in window:
        if isinstance(event, LearnerTextEvent):
            messages.append({"role": "user", "content": event.text})
        elif isinstance(event, UtteranceEvent):
            messages.append({"role": "assistant", "content": event.text})
    return messages


def _build_system_prompt(intent: CoachIntentEvent, skill: Skill) -> str:
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
        "Use the emit_turn tool to send your next message and record your assessment.",
        "Keep responses short — one or two sentences maximum.",
        "If the learner's input is their first message, greet them briefly and ask an opening question.",
    ]
    return "\n".join(lines)


async def run_turn(
    intent: CoachIntentEvent,
    skill: Skill,
    transcript_window: list[TranscriptEvent],
    learner_text: str,
    llm_client: Any,
) -> tuple[UtteranceEvent, TurnSignalEvent]:
    window = transcript_window[-TRANSCRIPT_WINDOW_SIZE:]
    messages = _format_transcript(window)
    messages.append({"role": "user", "content": learner_text or "(no input)"})

    response = llm_client.messages.create(
        model=TURN_MODEL,
        system=_build_system_prompt(intent, skill),
        messages=messages,
        tools=[_EMIT_TURN_TOOL],
        tool_choice={"type": "any"},
        max_tokens=512,
    )

    tool_input = response.content[0].input
    utterance = UtteranceEvent(text=tool_input["utterance"], skill_id=skill.id)
    signal = TurnSignalEvent(
        on_target=tool_input["on_target"],
        matched_markers=tool_input.get("matched_markers", []),
        affect=tool_input.get("affect", {}),
        notes=tool_input.get("notes", ""),
    )
    return utterance, signal


def get_llm_client() -> Anthropic:
    return Anthropic()
