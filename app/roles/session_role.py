import json
from typing import Any

from anthropic import Anthropic

from app.domain.content import CoachProfile, Program
from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TranscriptEvent,
    TurnSignalEvent,
    UtteranceEvent,
)

SESSION_MODEL = "claude-sonnet-4-6"
TRANSCRIPT_WINDOW_SIZE = 20

_SET_INTENT_TOOL: dict[str, Any] = {
    "name": "set_intent",
    "description": "Set the coaching intent for the next phase of the session.",
    "input_schema": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "enum": ["warm_up", "probe", "teach", "drill", "consolidate", "rest", "wrap"],
                "description": "The coaching goal for the next phase.",
            },
            "skill_id": {
                "type": "string",
                "description": "Which skill to focus on. Must be one of the program's skill_ids.",
            },
            "difficulty_hint": {
                "type": "string",
                "enum": ["easier", "same", "harder"],
                "description": "Relative difficulty adjustment for the next questions.",
            },
            "rationale": {
                "type": "string",
                "description": "Brief explanation of why this intent was chosen (for logs and human-tutor view).",
            },
            "tone_note": {
                "type": "string",
                "description": "Optional tone adjustment for this phase (e.g. 'extra encouraging').",
            },
        },
        "required": ["goal", "skill_id"],
    },
}


def _build_session_prompt(
    program: Program,
    coach_profile: CoachProfile | None,
    learner_portrait: str,
    program_state: dict,
) -> str:
    skills_list = ", ".join(program.skill_ids)
    mandatory_list = ", ".join(program.mandatory_skill_ids)
    lines = [
        "You are the session planner for a one-on-one tutoring session.",
        "",
        f"PROGRAM: {program.title}",
        f"SKILLS AVAILABLE: {skills_list}",
        f"MANDATORY SKILLS: {mandatory_list}",
        f"COMPLETION CRITERIA: {program.assessment_criteria}",
        "",
    ]
    if coach_profile:
        lines += [
            f"COACHING STYLE ({coach_profile.title}):",
            f"  Tone: {coach_profile.tone}",
            f"  Pacing: {coach_profile.pacing}",
            "",
        ]
    if learner_portrait:
        lines += ["LEARNER PORTRAIT:", learner_portrait, ""]
    if program_state:
        lines += ["PROGRAM STATE (per-skill progress):", json.dumps(program_state, indent=2), ""]
    lines += [
        "Review the recent transcript and progress data above.",
        "Decide what to do next: which skill to focus on, what goal, and how hard.",
        "Use set_intent to record your decision.",
    ]
    return "\n".join(lines)


def _format_transcript_for_session(window: list[TranscriptEvent]) -> list[dict]:
    messages = []
    for event in window[-TRANSCRIPT_WINDOW_SIZE:]:
        if isinstance(event, LearnerTextEvent):
            messages.append({"role": "user", "content": event.text})
        elif isinstance(event, UtteranceEvent):
            messages.append({"role": "assistant", "content": event.text})
        elif isinstance(event, TurnSignalEvent):
            label = "✓ on-target" if event.on_target else "✗ off-target"
            markers = ", ".join(event.matched_markers) if event.matched_markers else "none"
            messages.append({
                "role": "assistant",
                "content": f"[Turn signal: {label}; markers: {markers}]",
            })
    return messages


async def run_session(
    program: Program,
    coach_profile: CoachProfile | None,
    learner_portrait: str,
    program_state: dict,
    transcript_window: list[TranscriptEvent],
    llm_client: Any,
) -> CoachIntentEvent:
    """Call the session-level LLM role and return a CoachIntentEvent."""
    messages = _format_transcript_for_session(transcript_window)
    if not messages:
        messages = [{"role": "user", "content": "(session start — no turns yet)"}]

    response = llm_client.messages.create(
        model=SESSION_MODEL,
        system=_build_session_prompt(program, coach_profile, learner_portrait, program_state),
        messages=messages,
        tools=[_SET_INTENT_TOOL],
        tool_choice={"type": "any"},
        max_tokens=512,
    )

    tool_input = response.content[0].input
    return CoachIntentEvent(
        goal=tool_input["goal"],
        skill_id=tool_input["skill_id"],
        difficulty_hint=tool_input.get("difficulty_hint"),
        rationale=tool_input.get("rationale", ""),
        tone_note=tool_input.get("tone_note"),
    )


def get_session_llm_client() -> Anthropic:
    return Anthropic()
