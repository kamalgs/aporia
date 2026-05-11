from __future__ import annotations

import os
import random
from abc import ABC, abstractmethod
from typing import List

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.models import TutorStep, Problem, Evaluation, TurnData, StudentAnswerPayload

SYSTEM_PROMPT = """You are a patient, encouraging Socratic math tutor for elementary school students.
You teach basic arithmetic — right now, 2-digit addition with carrying — by asking questions and giving gentle hints, never by giving away the final answer.

SCAFFOLDING RULES (critical):
1. Always start with ONE diagnostic problem: two 2-digit numbers that require carrying (e.g. 25 + 36).
2. When a student answers WRONG:
   a. Diagnose the specific misconception first.
   b. Then IMMEDIATELY drop to the SIMPLER prerequisite — do NOT re-ask the same hard problem.
   c. Build up step by step.  Example progression for "omit_carry":
       - "What is 5 + 6?"                         (just the ones digits)
       - "What is 15 + 6?"                        (teen + ones → introduces a teen result)
       - "What is 15 + 16?"                       (teen + teen, still carrying)
       - "What is 25 + 36?"                       (back to the original difficulty)
   d. Only advance to the next step when the student gets the current one right.
3. When a student answers CORRECT:
   - praise simply, then move one step harder (or to mastery if already at target difficulty).
4. Never give the final numerical answer. Hints must be questions: "What do we do with the extra ten?"
5. Keep problems within the student's current zone: numbers ≤ 99, always one problem at a time.

MISCONCEPTION CODES (use exactly):
- "omit_carry"     — added columns correctly but forgot to carry (e.g. 25+36=51)
- "place_value"    — treated digits as separate or concatenated (e.g. 25+36=511)
- "basic_fact"     — a single-digit addition mistake despite correct strategy
- "none"           — answer is correct

OUTPUT FORMAT — return ONLY a JSON object matching this schema (no markdown, no extra keys):
{
  "feedback": "brief Socratic response to the student's last answer",
  "evaluation": {
    "is_correct": true or false,
    "misconceptions": ["omit_carry"] or ["none"],
    "hint": "the guiding question the student needs"
  },
  "question": {"operation": "add", "a": integer, "b": integer} or null if complete,
  "phase": "diagnostic" | "targeted" | "mastery" | "complete"
}
"""


def _format_history(history: List[TurnData]) -> str:
    lines = []
    for turn in history:
        if turn.role == "tutor" and turn.question:
            lines.append(f"Tutor: What is {turn.question.a} + {turn.question.b}?")
        elif turn.role == "student" and turn.answer:
            text = turn.answer.text if turn.answer.text else str(turn.answer.value)
            lines.append(f"Student: {text}")
        elif turn.role == "tutor" and turn.feedback:
            lines.append(f"Tutor: {turn.feedback}")
    return "\n".join(lines)


class TutorAgent(ABC):
    @abstractmethod
    async def start(self) -> TutorStep:
        ...

    @abstractmethod
    async def next(self, history: List[TurnData]) -> TutorStep:
        ...


class LlmAgent(TutorAgent):
    def __init__(self, model_name: str | None = None, api_key: str | None = None, base_url: str | None = None):
        model_name = model_name or os.environ.get("TUTOR_MODEL", "openai/gpt-4o-mini")
        api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        base_url = base_url or "https://openrouter.ai/api/v1"
        if not api_key:
            raise RuntimeError("LLM API key not set")
        model = OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(base_url=base_url, api_key=api_key),
        )
        self._agent = Agent(model, output_type=TutorStep, system_prompt=SYSTEM_PROMPT)

    async def start(self) -> TutorStep:
        result = await self._agent.run(
            "Start a new tutoring session. Ask a 2-digit addition diagnostic problem that requires carrying in the ones place."
        )
        return result.output

    async def next(self, history: List[TurnData]) -> TutorStep:
        prompt = f"Session transcript so far:\n{_format_history(history)}\n\nEvaluate the latest student answer and decide the next tutor action. Follow the SCAFFOLDING RULES strictly."
        result = await self._agent.run(prompt)
        return result.output


# ---- Deterministic Fake Agent (for tests / offline demos) ----

class _SimpleRng:
    def __init__(self, seed: int):
        self.s = seed

    def _next(self) -> float:
        self.s = (self.s * 1664525 + 1013904223) % (1 << 32)
        return self.s / (1 << 32)

    def range_int(self, lo: int, hi: int) -> int:
        return lo + int(self._next() * (hi - lo + 1))


def _correct_answer(p: Problem) -> int:
    return p.a + p.b


def _generate_diagnostic(rng: _SimpleRng) -> Problem:
    a, b = 0, 0
    while True:
        a = rng.range_int(10, 99)
        b = rng.range_int(10, 99)
        if (a % 10) + (b % 10) >= 10:
            break
    return Problem(operation="add", a=a, b=b)


def _generate_ones_only(rng: _SimpleRng) -> Problem:
    """Just the ones digits from a carry problem."""
    a = rng.range_int(5, 9)
    b = rng.range_int(5, 9)
    return Problem(operation="add", a=a, b=b)


def _generate_teen_plus_ones(rng: _SimpleRng) -> Problem:
    a = rng.range_int(10, 19)
    b = rng.range_int(5, 9)
    return Problem(operation="add", a=a, b=b)


def _generate_teen_plus_teen(rng: _SimpleRng) -> Problem:
    a, b = 0, 0
    while True:
        a = rng.range_int(10, 19)
        b = rng.range_int(10, 19)
        if (a % 10) + (b % 10) >= 10:
            break
    return Problem(operation="add", a=a, b=b)


def _generate_mastery(rng: _SimpleRng) -> Problem:
    return Problem(operation="add", a=rng.range_int(10, 99), b=rng.range_int(10, 99))


def _detect_error(problem: Problem, answer: int) -> tuple[bool, List[str], str]:
    expected = _correct_answer(problem)
    if answer == expected:
        return True, ["none"], "Correct! Great work."

    a_ones = problem.a % 10
    b_ones = problem.b % 10
    a_tens = problem.a // 10
    b_tens = problem.b // 10

    unit = (a_ones + b_ones) % 10
    tens = a_tens + b_tens
    if answer == tens * 10 + unit and a_ones + b_ones >= 10:
        return False, ["omit_carry"], "You added the ones correctly, but is there something extra left over when the ones go above 9? What do we do with that extra ten?"
    if answer >= 100 and len(str(answer)) > 2:
        return False, ["place_value"], "Think about what each digit means. The tens digit is not just another number to attach to the end."
    diff = abs(answer - expected)
    if 0 < diff < 10:
        return False, ["basic_fact"], "Check your basic addition step by step."
    return False, [], "Not quite. Walk through it again column by column from right to left."


class FakeAgent(TutorAgent):
    def __init__(self, seed: int = 42):
        self.rng = _SimpleRng(seed)
        self._phase: str = "diagnostic"
        self._retry_count: int = 0

    async def start(self) -> TutorStep:
        self._phase = "diagnostic"
        self._retry_count = 0
        p = _generate_diagnostic(self.rng)
        return TutorStep(
            feedback="Hello! Let us try a quick addition problem.",
            evaluation=Evaluation(is_correct=False, misconceptions=[], hint=""),
            question=p,
            phase="diagnostic",
        )

    async def next(self, history: List[TurnData]) -> TutorStep:
        last_question = next(
            (t for t in reversed(history) if t.role == "tutor" and t.question), None
        )
        last_student = next(
            (t for t in reversed(history) if t.role == "student" and t.answer), None
        )
        if not last_question or not last_student:
            raise ValueError("Missing question or answer in history")

        problem = last_question.question
        assert problem is not None
        val = last_student.answer.value if last_student.answer else 0
        is_correct, miscs, hint = _detect_error(problem, val)

        current_phase = self._phase
        next_problem: Problem | None = None
        next_phase = current_phase

        if is_correct:
            self._retry_count = 0
            if current_phase == "diagnostic":
                next_phase = "mastery"
                next_problem = _generate_mastery(self.rng)
            elif current_phase == "targeted":
                # advance one scaffold step up
                next_problem = self._scaffold_up(problem)
                if next_problem is None:
                    next_phase = "mastery"
                    next_problem = _generate_mastery(self.rng)
                else:
                    next_phase = "targeted"
            else:  # mastery
                next_phase = "complete"
        else:
            self._retry_count += 1
            if current_phase == "diagnostic":
                next_phase = "targeted"
                # drop to simplest: just the ones digits
                next_problem = _generate_ones_only(self.rng)
            elif current_phase == "targeted":
                next_phase = "targeted"
                # stay at same scaffold level or drop further
                next_problem = self._scaffold_down(problem)
            else:  # mastery wrong
                next_phase = "targeted"
                next_problem = _generate_ones_only(self.rng)

        self._phase = next_phase
        return TutorStep(
            feedback=hint,
            evaluation=Evaluation(is_correct=is_correct, misconceptions=miscs, hint=hint),
            question=next_problem,
            phase=next_phase,  # type: ignore[assignment]
        )

    def _scaffold_up(self, problem: Problem | None) -> Problem | None:
        """Return the next harder step, or None if already at full difficulty."""
        if problem is None:
            return _generate_mastery(self.rng)
        a, b = problem.a, problem.b
        if a < 10 and b < 10:
            # was ones-only → teen + ones
            return _generate_teen_plus_ones(self.rng)
        if a < 20 and b < 10:
            # was teen + ones → teen + teen
            return _generate_teen_plus_teen(self.rng)
        if a < 20 and b < 20:
            # was teen + teen → full 2-digit
            return _generate_diagnostic(self.rng)
        return None  # already at full difficulty

    def _scaffold_down(self, problem: Problem | None) -> Problem:
        """Return a simpler version when the student is stuck."""
        if problem is None:
            return _generate_ones_only(self.rng)
        a = problem.a
        if a >= 20 or problem.b >= 20:
            return _generate_teen_plus_teen(self.rng)
        if a >= 10 or problem.b >= 10:
            return _generate_teen_plus_ones(self.rng)
        return _generate_ones_only(self.rng)
