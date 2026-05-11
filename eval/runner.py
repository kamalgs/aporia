"""Batch runner: executes tutoring scenarios and saves transcripts + structured verdicts.

Usage:
    uv run python -m eval run          # run all scenarios, save to eval-results/
    uv run python -m eval judge        # batch-judge saved transcripts
    uv run python -m eval report       # generate markdown report from judged results
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field
from openai import AsyncOpenAI

from app.agent import LlmAgent
from app.models import TutorStep, TurnData, StudentAnswerPayload, Problem


# ───────────────────────────────────────────────────────────────────────────────
# Student simulators — given a tutor question, compute the "student's" answer
# ───────────────────────────────────────────────────────────────────────────────

def _correct_answer(p: Problem) -> int:
    return p.a + p.b


def _omit_carry_answer(p: Problem) -> int:
    return (p.a // 10 + p.b // 10) * 10 + ((p.a % 10) + (p.b % 10)) % 10


def _place_value_concat(p: Problem) -> int:
    return int(f"{p.a}{p.b}")


def _choose_answer(step: TutorStep, student_type: str, turn: int) -> int:
    if not step.question:
        raise ValueError("Tutor step has no question")
    if student_type == "always_correct":
        return _correct_answer(step.question)
    if student_type == "omit_carry":
        return _omit_carry_answer(step.question)
    if student_type == "place_value_concat":
        return _place_value_concat(step.question)
    if student_type == "wrong_then_correct":
        if turn == 0:
            return _omit_carry_answer(step.question)
        return _correct_answer(step.question)
    raise ValueError(f"Unknown student type: {student_type}")


def _format_transcript(history: List[TurnData]) -> str:
    lines = []
    for turn in history:
        if turn.role == "tutor" and turn.question:
            lines.append(f"Tutor: What is {turn.question.a} + {turn.question.b}?")
        elif turn.role == "student" and turn.answer:
            lines.append(f"Student: {turn.answer.text}")
        elif turn.role == "tutor" and turn.feedback:
            lines.append(f"Tutor: {turn.feedback}")
    return "\n".join(lines)


# ───────────────────────────────────────────────────────────────────────────────
# Saved record shape (judge fills in later)
# ───────────────────────────────────────────────────────────────────────────────

class EvalRecord(BaseModel):
    name: str
    student_type: str
    max_turns: int
    transcript: str
    final_phase: str
    turn_count: int
    # judge-filled later
    socratic_quality: int | None = Field(default=None)
    scaffolding_adherence: bool | None = Field(default=None)
    never_reveals_answer: bool | None = Field(default=None)
    diagnoses_specifically: bool | None = Field(default=None)
    overall_pass: bool | None = Field(default=None)
    rationale: str | None = Field(default=None)
    failure_reason: str | None = Field(default=None)


class JudgeVerdict(BaseModel):
    socratic_quality: int = Field(ge=1, le=5)
    scaffolding_adherence: bool
    never_reveals_answer: bool
    diagnoses_specifically: bool
    overall_pass: bool
    rationale: str


JUDGE_SYSTEM = """You are a senior mathematics education evaluator.
Review tutoring session transcripts and score the tutor's Socratic quality.

SCORING:
- socratic_quality (1-5): Does the tutor guide via questions without giving answers?
- scaffolding_adherence (bool): After wrong answer on hard problem, does tutor drop to simpler prerequisite, then build monotonically back up?
- never_reveals_answer (bool): Is correct numerical answer NEVER stated verbatim?
- diagnoses_specifically (bool): Are misconceptions named specifically (omit_carry, place_value), or is feedback vague like "try again"?
- overall_pass (bool): Would you recommend this tutor to a 3rd-grade teacher?
- rationale (str): 1-2 sentences quoting specific transcript lines.

OUTPUT — return ONLY JSON, no markdown or explanation outside the JSON."""


# ───────────────────────────────────────────────────────────────────────────────
# Tutor execution (Phase 1 — fast, only tutor LLM calls)
# ───────────────────────────────────────────────────────────────────────────────

async def run_scenario(tutor: LlmAgent, scenario_path: Path, per_call_timeout: int = 60) -> EvalRecord:
    """Execute a single scenario — saves transcript, no judge yet."""
    with open(scenario_path) as f:
        cfg = json.load(f)

    name = cfg["name"]
    student_type = cfg["student_type"]
    max_turns = min(cfg["max_turns"], 8)  # hard cap to keep costs reasonable

    step = await asyncio.wait_for(tutor.start(), timeout=per_call_timeout)
    history: List[TurnData] = [TurnData(role="tutor", question=step.question, feedback=step.feedback)]

    for turn in range(max_turns):
        if step.question is None:
            break
        answer = _choose_answer(step, student_type, turn)
        history.append(TurnData(role="student", answer=StudentAnswerPayload(text=str(answer), value=answer)))

        step = await asyncio.wait_for(tutor.next(history), timeout=per_call_timeout)
        history.append(TurnData(role="tutor", question=step.question, feedback=step.feedback))

        if step.phase == "complete":
            break

    return EvalRecord(
        name=name,
        student_type=student_type,
        max_turns=max_turns,
        transcript=_format_transcript(history),
        final_phase=step.phase,
        turn_count=len(history) // 2,
    )


# ───────────────────────────────────────────────────────────────────────────────
# Judge execution (Phase 2 — direct API, no PydanticAI tool overhead)
# ───────────────────────────────────────────────────────────────────────────────

async def _judge_transcript(transcript: str, timeout: int = 45) -> JudgeVerdict:
    """Direct async OpenAI call — avoids PydanticAI tool-calling overhead that can hang."""
    fw_key = os.environ.get("FIREWORKS_API_KEY")
    if not fw_key:
        raise RuntimeError("FIREWORKS_API_KEY not set")

    client = AsyncOpenAI(base_url="https://api.fireworks.ai/inference/v1", api_key=fw_key)

    response = await asyncio.wait_for(
        client.chat.completions.create(
            model=os.environ.get("FIREWORKS_MODEL", "accounts/fireworks/models/kimi-k2p6"),
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": f"Evaluate this tutoring session transcript:\n\n{transcript}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        ),
        timeout=timeout,
    )

    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)
    return JudgeVerdict.model_validate(data)


def _apply_criteria(record: EvalRecord, criteria: dict) -> str | None:
    """Return failure reason string, or None if all criteria pass."""
    reasons: List[str] = []
    if criteria.get("min_socratic_quality") and (record.socratic_quality or 0) < criteria["min_socratic_quality"]:
        reasons.append(f"quality {record.socratic_quality}/{criteria['min_socratic_quality']}")
    if criteria.get("must_reach") and record.final_phase != criteria["must_reach"]:
        reasons.append(f"phase={record.final_phase}, want={criteria['must_reach']}")
    if criteria.get("must_scaffold") and not (record.scaffolding_adherence or False):
        reasons.append("scaffolding false")
    if criteria.get("must_diagnose") and not (record.diagnoses_specifically or False):
        reasons.append(f"diagnosis missing (want {criteria['must_diagnose']})")
    if criteria.get("never_reveals_answer") and not (record.never_reveals_answer or False):
        reasons.append("reveals answer")
    if criteria.get("scaffolding_adherence") and not (record.scaffolding_adherence or False):
        reasons.append("scaffolding_adherence false")
    if criteria.get("monotonic_progression") and not (record.scaffolding_adherence or False):
        reasons.append("monotonic=false")
    if criteria.get("no_vague_feedback") and not (record.diagnoses_specifically or False):
        reasons.append("vague")
    if criteria.get("overall_must_pass") and not (record.overall_pass or False):
        reasons.append("overall_pass=false")
    return "; ".join(reasons) if reasons else None
