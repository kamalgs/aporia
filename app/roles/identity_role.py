import json
from typing import Any

from anthropic import Anthropic

from app.domain.content import GuardianProfile, Program
from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TranscriptEvent,
    TurnSignalEvent,
    UtteranceEvent,
)

IDENTITY_MODEL = "claude-sonnet-4-6"

_UPDATE_PORTRAIT_TOOL: dict[str, Any] = {
    "name": "update_portrait",
    "description": "Write the updated learner portrait after this session.",
    "input_schema": {
        "type": "object",
        "properties": {
            "portrait_md": {
                "type": "string",
                "description": (
                    "A markdown narrative describing this learner as if written by a thoughtful tutor "
                    "after the session. Cover: what they worked on, how they performed, patterns observed "
                    "(strengths, recurring errors, affect), and what to remember for next time. "
                    "2–4 short paragraphs. Incorporate the prior portrait if provided."
                ),
            },
        },
        "required": ["portrait_md"],
    },
}


def _build_identity_prompt(
    program: Program,
    guardian_profile: GuardianProfile | None,
    prior_portrait: str,
    program_state: dict,
) -> str:
    lines = [
        "You are the identity keeper for a tutoring system. Your job is to maintain a durable, "
        "human-readable portrait of the learner that accumulates across sessions.",
        "",
        f"PROGRAM JUST COMPLETED: {program.title}",
        f"MANDATORY SKILLS: {', '.join(program.mandatory_skill_ids)}",
        "",
    ]
    if guardian_profile:
        lines += [
            f"LEARNER COHORT ({guardian_profile.title}):",
            guardian_profile.cohort_description,
            guardian_profile.raw_md,
            "",
        ]
    if prior_portrait:
        lines += ["PRIOR PORTRAIT (from earlier sessions):", prior_portrait, ""]
    else:
        lines += ["PRIOR PORTRAIT: (none — this is the learner's first session)", ""]
    if program_state:
        lines += ["PROGRAM STATE (per-skill progress this program):", json.dumps(program_state, indent=2), ""]
    lines += [
        "Review the session transcript below and write an updated portrait using the update_portrait tool.",
        "The portrait should read as if a thoughtful human tutor wrote it — specific, evidence-based, "
        "and useful as context for the next session.",
    ]
    return "\n".join(lines)


def _format_transcript_for_identity(transcript: list[TranscriptEvent]) -> list[dict]:
    messages = []
    for event in transcript:
        if isinstance(event, LearnerTextEvent):
            messages.append({"role": "user", "content": event.text})
        elif isinstance(event, UtteranceEvent):
            messages.append({"role": "assistant", "content": event.text})
        elif isinstance(event, TurnSignalEvent):
            label = "✓" if event.on_target else "✗"
            markers = f" [{', '.join(event.matched_markers)}]" if event.matched_markers else ""
            messages.append({
                "role": "assistant",
                "content": f"[Signal: {label}{markers}]",
            })
        elif isinstance(event, CoachIntentEvent):
            messages.append({
                "role": "assistant",
                "content": f"[Intent: {event.goal} / skill={event.skill_id}]",
            })
    return messages


async def run_identity(
    program: Program,
    guardian_profile: GuardianProfile | None,
    prior_portrait: str,
    program_state: dict,
    transcript: list[TranscriptEvent],
    llm_client: Any,
) -> str:
    """Run the identity role and return an updated portrait_md string."""
    messages = _format_transcript_for_identity(transcript)
    if not messages:
        messages = [{"role": "user", "content": "(no turns in this session)"}]

    response = llm_client.messages.create(
        model=IDENTITY_MODEL,
        system=_build_identity_prompt(program, guardian_profile, prior_portrait, program_state),
        messages=messages,
        tools=[_UPDATE_PORTRAIT_TOOL],
        tool_choice={"type": "any"},
        max_tokens=1024,
    )

    return response.content[0].input["portrait_md"]


def get_identity_llm_client() -> Anthropic:
    return Anthropic()
