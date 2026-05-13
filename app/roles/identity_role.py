import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import AnthropicModel

from app.domain.content import GuardianProfile, Program
from app.domain.events import (
    CoachIntentEvent,
    LearnerTextEvent,
    TranscriptEvent,
    TurnSignalEvent,
    UtteranceEvent,
)

IDENTITY_MODEL = "claude-sonnet-4-6"


class IdentityOutput(BaseModel):
    portrait_md: str


@dataclass
class IdentityDeps:
    program: Program
    guardian_profile: GuardianProfile | None
    prior_portrait: str
    program_state: dict


_identity_agent: Agent[IdentityDeps, IdentityOutput] = Agent(
    model=AnthropicModel(IDENTITY_MODEL),
    output_type=IdentityOutput,
    deps_type=IdentityDeps,
)


@_identity_agent.instructions
def _identity_instructions(ctx: RunContext[IdentityDeps]) -> str:
    d = ctx.deps
    lines = [
        "You are the identity keeper for a tutoring system. Your job is to maintain a durable, "
        "human-readable portrait of the learner that accumulates across sessions.",
        "",
        f"PROGRAM JUST COMPLETED: {d.program.title}",
        f"MANDATORY SKILLS: {', '.join(d.program.mandatory_skill_ids)}",
        "",
    ]
    if d.guardian_profile:
        lines += [
            f"LEARNER COHORT ({d.guardian_profile.title}):",
            d.guardian_profile.cohort_description,
            d.guardian_profile.raw_md,
            "",
        ]
    if d.prior_portrait:
        lines += ["PRIOR PORTRAIT (from earlier sessions):", d.prior_portrait, ""]
    else:
        lines += ["PRIOR PORTRAIT: (none — this is the learner's first session)", ""]
    if d.program_state:
        lines += ["PROGRAM STATE (per-skill progress this program):", json.dumps(d.program_state, indent=2), ""]
    lines += [
        "Review the session transcript below and write an updated portrait.",
        "The portrait should read as if a thoughtful human tutor wrote it — specific, evidence-based, "
        "and useful as context for the next session. Write 2–4 short paragraphs.",
    ]
    return "\n".join(lines)


def _format_transcript_for_identity(transcript: list[TranscriptEvent]) -> str:
    lines = []
    for event in transcript:
        if isinstance(event, LearnerTextEvent):
            lines.append(f"Learner: {event.text}")
        elif isinstance(event, UtteranceEvent):
            lines.append(f"Tutor: {event.text}")
        elif isinstance(event, TurnSignalEvent):
            label = "✓" if event.on_target else "✗"
            markers = f" [{', '.join(event.matched_markers)}]" if event.matched_markers else ""
            lines.append(f"[Signal: {label}{markers}]")
        elif isinstance(event, CoachIntentEvent):
            lines.append(f"[Intent: {event.goal} / skill={event.skill_id}]")
    return "\n".join(lines) if lines else "(no turns in this session)"


async def run_identity(
    program: Program,
    guardian_profile: GuardianProfile | None,
    prior_portrait: str,
    program_state: dict,
    transcript: list[TranscriptEvent],
    model: Any = None,
) -> str:
    """Run the identity role and return an updated portrait_md string."""
    deps = IdentityDeps(
        program=program,
        guardian_profile=guardian_profile,
        prior_portrait=prior_portrait,
        program_state=program_state,
    )
    transcript_text = _format_transcript_for_identity(transcript)
    kwargs: dict[str, Any] = dict(deps=deps)
    if model is not None:
        kwargs["model"] = model

    result = await _identity_agent.run(transcript_text, **kwargs)
    return result.output.portrait_md


def get_identity_model() -> AnthropicModel:
    return AnthropicModel(IDENTITY_MODEL)
