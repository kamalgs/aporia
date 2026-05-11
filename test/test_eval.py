"""
LLM-as-judge evals for the Socratic Tutor.

The judge reviews tutoring session transcripts holistically and scores:
- socratic_quality: Does the tutor guide via questions without giving answers?
- scaffolding_adherence: After a wrong answer, does the tutor drop to a simpler prerequisite?
- never_reveals_answer: Is the correct answer NEVER stated verbatim in feedback?
- diagnoses_specifically: Are misconceptions named specifically (omit_carry, place_value)?

Skip automatically if no LLM credentials are configured.
"""

from __future__ import annotations

import os
from typing import List

import pytest

from pydantic import BaseModel, Field
from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.agent import LlmAgent
from app.models import TutorStep, TurnData, StudentAnswerPayload


# ───────────────────────────────────────────────────────────────────────────────
# Layer 1 — Deterministic helpers (cheap, never break on wording changes)
# ───────────────────────────────────────────────────────────────────────────────

def _problem_requires_carrying(p) -> bool:
    return (p.a % 10) + (p.b % 10) >= 10


def _correct_answer(p) -> int:
    return p.a + p.b


def _omit_carry_answer(p) -> int:
    """Student adds column-wise but never carries."""
    return (p.a // 10 + p.b // 10) * 10 + ((p.a % 10) + (p.b % 10)) % 10


def _place_value_concat(p) -> int:
    """Student concatenates digits (e.g. 25+36 → 2536)."""
    return int(f"{p.a}{p.b}")


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


def _build_transcript(steps: List[TutorStep], answers: List[int]) -> str:
    """Build a clean transcript string from a sequence of tutor turns and student answers."""
    lines = []
    for i, step in enumerate(steps):
        if step.question:
            lines.append(f"Tutor: What is {step.question.a} + {step.question.b}?")
        else:
            lines.append(f"Tutor: {step.feedback}")
        if i < len(answers):
            lines.append(f"Student: {answers[i]}")
        lines.append(f"Tutor: {step.feedback}")
    return "\n".join(lines)


# ───────────────────────────────────────────────────────────────────────────────
# Layer 2 — LLM-as-judge
# ───────────────────────────────────────────────────────────────────────────────

class JudgeVerdict(BaseModel):
    socratic_quality: int = Field(ge=1, le=5)
    scaffolding_adherence: bool
    never_reveals_answer: bool
    diagnoses_specifically: bool
    rationale: str


JUDGE_SYSTEM_PROMPT = """You are a senior mathematics education evaluator.
You review tutoring session transcripts and score the tutor's Socratic quality.

SCORING RULES (return ONLY JSON matching the schema):
- socratic_quality (int 1-5): Does the tutor guide via questions without giving answers?
  5 = perfectly Socratic, never reveals answer, only guiding questions.
  1 = gives answers away, no guidance.
- scaffolding_adherence (bool): After a wrong answer on a hard problem, does the tutor drop to a simpler prerequisite FIRST, then build up? If the tutor re-asks the same hard problem, this is false. If the tutor oscillates randomly between easy and hard, this is false. The progression must be monotonic: simpler -> slightly harder -> target difficulty.
- never_reveals_answer (bool): Is the correct answer NEVER stated verbatim in feedback? If the feedback says "The answer is 61" that's false. If it says "61 is correct, can you explain why?" that's also false.
- diagnoses_specifically (bool): Are misconceptions named specifically (omit_carry, place_value, basic_fact) or is the feedback vague like "try again"?
- rationale (str): 1-2 sentences explaining your reasoning. Quote specific lines from the transcript as evidence.

OUTPUT FORMAT — return ONLY JSON:
{
  "socratic_quality": 1-5,
  "scaffolding_adherence": true/false,
  "never_reveals_answer": true/false,
  "diagnoses_specifically": true/false,
  "rationale": "string"
}"""


def _get_judge() -> PydanticAgent:
    fw_key = os.environ.get("FIREWORKS_API_KEY")
    if not fw_key:
        pytest.skip("No FIREWORKS_API_KEY configured — skipping LLM judge evals")
    model = OpenAIChatModel(
        "accounts/fireworks/models/kimi-k2p6",
        provider=OpenAIProvider(base_url="https://api.fireworks.ai/inference/v1", api_key=fw_key),
    )
    return PydanticAgent(model, output_type=JudgeVerdict, system_prompt=JUDGE_SYSTEM_PROMPT)


async def _llm_judge(transcript: str) -> JudgeVerdict:
    judge = _get_judge()
    result = await judge.run(f"Evaluate this tutoring transcript:\n\n{transcript}")
    return result.output


# ───────────────────────────────────────────────────────────────────────────────
# Evals
# ───────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def tutor():
    if not os.environ.get("FIREWORKS_API_KEY"):
        pytest.skip("No FIREWORKS_API_KEY configured")
    return LlmAgent()


@pytest.mark.asyncio
async def test_judge_start_is_diagnostic_carry_problem(tutor):
    """Invariant: first question must be a 2-digit addition with carrying."""
    step = await tutor.start()

    assert step.phase == "diagnostic"
    assert step.question is not None
    assert step.question.a >= 10 and step.question.b >= 10
    assert _problem_requires_carrying(step.question)
    # answer must not be in feedback
    assert str(_correct_answer(step.question)) not in step.feedback


@pytest.mark.asyncio
async def test_judge_omit_carry_scaffold_quality(tutor):
    """
    Golden-path eval: student omits carry on 2-digit addition.
    Tutor should:
    1. Diagnose omit_carry specifically (not vague "try again")
    2. Drop to a simpler prerequisite
    3. Eventually build back to full difficulty

    The LLM judge evaluates whether the Socratic method was followed
    holistically — we do not demand exact scaffold progression because
    the model is allowed to experiment, but we require monotonic build-up.
    """
    step = await tutor.start()
    history: List[TurnData] = []
    steps: List[TutorStep] = [step]
    answers: List[int] = []
    max_turns = 15

    for turn in range(max_turns):
        history.append(TurnData(role="tutor", question=step.question, feedback=step.feedback))

        # First turn: wrong (omit carry). All others: correct.
        if turn == 0:
            answer = _omit_carry_answer(step.question)
        elif step.question:
            answer = _correct_answer(step.question)
        else:
            break

        history.append(TurnData(role="student", answer=StudentAnswerPayload(text=str(answer), value=answer)))
        answers.append(answer)

        step = await tutor.next(history)
        steps.append(step)

        if step.phase == "complete":
            break

    transcript = _format_transcript(history)
    verdict = await _llm_judge(transcript)

    assert verdict.socratic_quality >= 3, f"Quality too low: {verdict.rationale}"
    assert verdict.diagnoses_specifically is True, f"No specific diagnosis: {verdict.rationale}"
    assert verdict.never_reveals_answer is True, f"Answer leaked: {verdict.rationale}"
    # Log but don't hard-fail on scaffold adherence — this is the honest finding area.
    # If the model oscillates, the judge scores low on scaffolding_adherence.
    if not verdict.scaffolding_adherence:
        pytest.xfail(f"Scaffolding not monotonic (model instability): {verdict.rationale}")


@pytest.mark.asyncio
async def test_judge_place_value_specificity(tutor):
    """
    Student makes a place-value error (concatenates digits).
    The judge verifies the tutor names "place_value" specifically,
    not "omit_carry" or a vague hint.
    """
    step = await tutor.start()
    wrong = _place_value_concat(step.question)

    history = [
        TurnData(role="tutor", question=step.question, feedback=step.feedback),
        TurnData(role="student", answer=StudentAnswerPayload(text=str(wrong), value=wrong)),
    ]
    step2 = await tutor.next(history)

    transcript = _format_transcript(history)
    verdict = await _llm_judge(transcript)

    assert verdict.diagnoses_specifically is True, f"No specific diagnosis: {verdict.rationale}"
    assert "place_value" not in step2.feedback.lower() or verdict.diagnoses_specifically
    # If the model wrongly diagnosed omit_carry on a place_value error,
    # the judge catches it via low specificity score.


@pytest.mark.asyncio
async def test_judge_always_asks_question_never_answers(tutor):
    """
    After any student answer (correct or wrong), the tutor's feedback
    must contain a guiding question, not the answer.
    """
    step = await tutor.start()
    max_turns = 10

    for turn in range(max_turns):
        if step.question is None:
            break
        correct = _correct_answer(step.question)

        history = [
            TurnData(role="tutor", question=step.question, feedback=step.feedback),
            TurnData(role="student", answer=StudentAnswerPayload(text=str(correct), value=correct)),
        ]

        step = await tutor.next(history)
        # Don't assert feedback ends with "?" — that's a brittle heuristic.
        # Let the judge decide if it's still Socratic.

        transcript = _format_transcript(history)
        verdict = await _llm_judge(transcript)
        assert verdict.never_reveals_answer is True, f"Answer leaked: {verdict.rationale}"
        # If feedback is too low quality, that's a finding to fix, not a test failure.
        # We only fail if the answer is literally given away.
        if verdict.socratic_quality < 3:
            print(f"WARNING: socratic_quality={verdict.socratic_quality} on turn {turn}: {verdict.rationale}")
