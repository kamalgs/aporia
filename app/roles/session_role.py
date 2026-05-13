import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import AnthropicModel

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


class SessionOutput(BaseModel):
    goal: Literal["warm_up", "probe", "teach", "drill", "consolidate", "rest", "wrap"]
    skill_id: str
    difficulty_hint: Literal["easier", "same", "harder"] | None = None
    rationale: str = ""
    tone_note: str | None = None


@dataclass
class SessionDeps:
    program: Program
    coach_profile: CoachProfile | None
    learner_portrait: str
    program_state: dict
    pending_guidance: str = ""


_session_agent: Agent[SessionDeps, SessionOutput] = Agent(
    model=AnthropicModel(SESSION_MODEL),
    output_type=SessionOutput,
    deps_type=SessionDeps,
)


@_session_agent.instructions
def _session_instructions(ctx: RunContext[SessionDeps]) -> str:
    d = ctx.deps
    skills_list = ", ".join(d.program.skill_ids)
    mandatory_list = ", ".join(d.program.mandatory_skill_ids)
    lines = [
        "You are the session planner for a one-on-one tutoring session.",
        "",
        f"PROGRAM: {d.program.title}",
        f"SKILLS AVAILABLE: {skills_list}",
        f"MANDATORY SKILLS: {mandatory_list}",
        f"COMPLETION CRITERIA: {d.program.assessment_criteria}",
        "",
    ]
    if d.coach_profile:
        lines += [
            f"COACHING STYLE ({d.coach_profile.title}):",
            f"  Tone: {d.coach_profile.tone}",
            f"  Pacing: {d.coach_profile.pacing}",
            "",
        ]
    if d.learner_portrait:
        lines += ["LEARNER PORTRAIT:", d.learner_portrait, ""]
    if d.program_state:
        lines += ["PROGRAM STATE (per-skill progress):", json.dumps(d.program_state, indent=2), ""]
    if d.pending_guidance:
        lines += ["TUTOR GUIDANCE (incorporate into your decision):", d.pending_guidance, ""]
    lines += [
        "Review the recent transcript and progress data above.",
        "Decide what to do next: which skill to focus on, what goal, and how hard.",
    ]
    return "\n".join(lines)


def _format_transcript_for_session(window: list[TranscriptEvent]) -> str:
    lines = []
    for event in window[-TRANSCRIPT_WINDOW_SIZE:]:
        if isinstance(event, LearnerTextEvent):
            lines.append(f"Learner: {event.text}")
        elif isinstance(event, UtteranceEvent):
            lines.append(f"Tutor: {event.text}")
        elif isinstance(event, TurnSignalEvent):
            label = "✓ on-target" if event.on_target else "✗ off-target"
            markers = ", ".join(event.matched_markers) if event.matched_markers else "none"
            lines.append(f"[Signal: {label}; markers: {markers}]")
    return "\n".join(lines) if lines else "(session start — no turns yet)"


async def run_session(
    program: Program,
    coach_profile: CoachProfile | None,
    learner_portrait: str,
    program_state: dict,
    transcript_window: list[TranscriptEvent],
    llm_client: Any = None,
    pending_guidance: str = "",
) -> CoachIntentEvent:
    """Call the session-level LLM role and return a CoachIntentEvent."""
    deps = SessionDeps(
        program=program,
        coach_profile=coach_profile,
        learner_portrait=learner_portrait,
        program_state=program_state,
        pending_guidance=pending_guidance,
    )
    transcript_text = _format_transcript_for_session(transcript_window)
    kwargs: dict[str, Any] = dict(deps=deps)
    if llm_client is not None:
        kwargs["model"] = llm_client

    result = await _session_agent.run(transcript_text, **kwargs)
    out = result.output
    return CoachIntentEvent(
        goal=out.goal,
        skill_id=out.skill_id,
        difficulty_hint=out.difficulty_hint,
        rationale=out.rationale or "",
        tone_note=out.tone_note,
    )


def get_session_model() -> AnthropicModel:
    return AnthropicModel(SESSION_MODEL)
