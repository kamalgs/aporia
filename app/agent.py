from __future__ import annotations

import asyncio
import json
import os
import random
from abc import ABC, abstractmethod
from typing import List

from openai import AsyncOpenAI

from app.models import TutorStep, Problem, Evaluation, TurnData, StudentAnswerPayload

SYSTEM_PROMPT = """You are a patient, encouraging Socratic math tutor for elementary school students.
You teach basic arithmetic — right now, 2-digit addition with carrying — by asking questions and giving gentle hints, never by giving away the final answer.

RULES:
1. Ask one problem at a time.
2. When the student answers, evaluate the numerical answer yourself.
   - Compute the correct sum to verify.
   - If wrong, diagnose the specific misconception:
     * "omit_carry" — student added columns correctly but forgot to carry the extra ten (e.g. 32+48=70).
     * "place_value" — student treated digits as separate numbers or concatenated them (e.g. 32+48=710).
     * "basic_fact" — a single-digit addition mistake, but strategy looks okay otherwise.
3. Give a Socratic hint that guides the student toward discovering the error. Never say "the answer is X".
4. If the answer is correct, praise briefly, then either:
   - Ask a harder mastery problem if the diagnostic or targeted phase is passed.
   - Or finish the session if mastery seems solid.
5. If the student is struggling after one targeted hint, ask a simpler problem that isolates the same concept.

OUTPUT FORMAT:
Return ONLY a JSON object exactly matching this schema (no markdown, no extra keys):
{
  "feedback": "short socratic response to the student's last answer",
  "evaluation": {
    "is_correct": true or false,
    "misconceptions": [list of diagnosed misconception strings, or ["none"]],
    "hint": "the core idea the student missed, stated as a guiding question"
  },
  "question": {
    "operation": "add",
    "a": integer,
    "b": integer
  } or null if the session is complete,
  "phase": "diagnostic" | "targeted" | "mastery" | "complete"
}
"""


def _format_history(history: List[TurnData]) -> str:
    lines = []
    for turn in history:
        if turn.role == "tutor" and turn.question:
            lines.append(f"Tutor: What is {turn.question.a} + {turn.question.b}?")
        elif turn.role == "student" and turn.answer:
            exp = f" ({turn.answer.explanation})" if turn.answer.explanation else ""
            lines.append(f"Student: {turn.answer.value}{exp}")
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
        self.model_name = model_name or os.environ.get("TUTOR_MODEL", "openai/gpt-4o-mini")
        api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        base_url = base_url or "https://openrouter.ai/api/v1"
        if not api_key:
            raise RuntimeError("LLM API key not set")
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._system = SYSTEM_PROMPT

    async def _call(self, user_content: str) -> TutorStep:
        loop = asyncio.get_event_loop()
        # Run sync client call in thread pool so we don't block the loop.
        def _sync_call():
            import openai
            client = openai.OpenAI(base_url=self._client.base_url, api_key=self._client.api_key)
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self._system},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            return json.loads(raw)
        data = await loop.run_in_executor(None, _sync_call)
        # Validate shape via Pydantic
        return TutorStep.model_validate(data)

    async def start(self) -> TutorStep:
        return await self._call(
            "Start a new tutoring session. Ask a 2-digit addition diagnostic problem that requires carrying in the ones place."
        )

    async def next(self, history: List[TurnData]) -> TutorStep:
        prompt = f"Session transcript so far:\n{_format_history(history)}\n\nEvaluate the latest student answer and decide the next tutor action."
        return await self._call(prompt)


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


def _generate_targeted(rng: _SimpleRng) -> Problem:
    a, b = 0, 0
    while True:
        a = rng.range_int(11, 49)
        b = rng.range_int(11, 49)
        if (a % 10) + (b % 10) >= 10 and a + b <= 100:
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
        self._phase: Literal["diagnostic", "targeted", "mastery", "complete"] = "diagnostic"

    async def start(self) -> TutorStep:
        self._phase = "diagnostic"
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

        if is_correct:
            if current_phase == "diagnostic":
                next_phase = "mastery"
                next_problem = _generate_mastery(self.rng)
            elif current_phase == "targeted":
                next_phase = "mastery"
                next_problem = _generate_mastery(self.rng)
            else:  # mastery
                next_phase = "complete"
        else:
            if current_phase == "diagnostic":
                next_phase = "targeted"
                next_problem = _generate_targeted(self.rng)
            elif current_phase == "targeted":
                next_phase = "targeted"
                next_problem = _generate_targeted(self.rng)
            else:  # mastery wrong
                next_phase = "targeted"
                next_problem = _generate_targeted(self.rng)

        self._phase = next_phase
        return TutorStep(
            feedback=hint,
            evaluation=Evaluation(is_correct=is_correct, misconceptions=miscs, hint=hint),
            question=next_problem,
            phase=next_phase,
        )
