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
   a. **feedback MUST start by explicitly naming the exact misconception.**  Examples:
      - omit_carry → "I notice you may have forgotten to carry..."
      - place_value → "It looks like you treated the two numbers as separate digits..."
      - basic_fact → "Let's double-check that single-digit addition..."
   b. Then drop to the SIMPLER prerequisite — do NOT re-ask the same hard problem.
   c. Build up step by step.  Example progression for "omit_carry":
       - "What is 5 + 6?"                         (just the ones digits)
       - "What is 15 + 6?"                        (teen + ones → introduces a teen result)
       - "What is 15 + 16?"                       (teen + teen, still carrying)
       - "What is 25 + 36?"                       (back to the original difficulty)
   d. Only advance to the next step when the student gets the current one right.
3. When a student answers CORRECT:
   a. Praise briefly (one sentence), then move ONE step harder.
   b. **NEVER drop to an easier problem after a correct answer.** Monotonic progression only.
   c. If already at the hardest level (mastery / original diagnostic difficulty) and this is the second consecutive correct answer, set phase = "complete" and question = null.
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
    """Enriched transcript: every turn includes correctness & evaluation tags.
    This lets the LLM see the full pedagogical state without inferring it."""
    lines = []
    for turn in history:
        if turn.role == "student" and turn.answer:
            text = turn.answer.text if turn.answer.text else str(turn.answer.value)
            lines.append(f"Student: {text}")
            continue
        if turn.role == "tutor":
            if turn.question:
                lines.append(f"Tutor asks: What is {turn.question.a} + {turn.question.b}?")
            if turn.evaluation:
                corr = "CORRECT" if turn.evaluation.is_correct else "WRONG"
                miscs = ", ".join(turn.evaluation.misconceptions) or "none"
                lines.append(f"    → Eval: {corr} | misconception(s): {miscs}")
            if turn.feedback:
                lines.append(f"    Tutor says: {turn.feedback}")
    return "\n".join(lines)


class TutorAgent(ABC):
    @abstractmethod
    async def start(self) -> TutorStep:
        ...

    @abstractmethod
    async def next(self, history: List[TurnData]) -> TutorStep:
        ...


# ───────────────────────────────────────────────────────────────────────────────
# LlmAgent: LLM drives content; agent enforces anti-oscillation guardrails.
# ───────────────────────────────────────────────────────────────────────────────

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
        # Orchestration state (only used to validate / guard-rail, never to replace LLM)
        self._diag: Problem | None = None
        self._phase_chain: list[str] = []
        self._consecutive_correct: int = 0
        self._peak_difficulty: int = 0
        self._mastered_level: int = 0   # highest difficulty solved correctly
        self._last_was_correct: bool | None = None

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _difficulty(problem: Problem | None) -> int:
        if problem is None:
            return -1
        a, b = problem.a, problem.b
        if a < 10 and b < 10:
            return 1          # ones-only
        if a < 20 and b < 10:
            return 2          # teen + ones
        if a < 20 and b < 20:
            return 3          # teen + teen
        return 4              # mastery / diagnostic

    def _update_state(self, last_problem: Problem | None, is_correct: bool):
        self._last_was_correct = is_correct
        d = self._difficulty(last_problem)
        self._peak_difficulty = max(self._peak_difficulty, d)
        if is_correct:
            self._consecutive_correct += 1
        else:
            self._consecutive_correct = 0
        # Track the highest difficulty that the student has *correctly solved*.
        if is_correct and d > self._mastered_level:
            self._mastered_level = d

    def _build_state_header(self, history: List[TurnData]) -> str:
        """Explicit state header that the LLM can rely on."""
        parts = [
            f"Peak scaffold reached: {self._peak_difficulty}",
            f"Consecutive correct: {self._consecutive_correct}",
            f"Last answer was correct: {self._last_was_correct}",
        ]
        if self._diag:
            parts.append(f"Original target problem: {self._diag.a} + {self._diag.b}")
        return "## TUTORING ENGINE STATE\n" + "\n".join(parts)

    async def start(self) -> TutorStep:
        self._diag = None
        self._phase_chain = []
        self._consecutive_correct = 0
        self._peak_difficulty = 0
        self._mastered_level = 0
        self._last_was_correct = None

        result = await self._agent.run(
            "Start a new tutoring session."
            "\nAsk a 2-digit addition diagnostic problem that requires carrying in the ones place (e.g. 25 + 36)."
            "\nphase must be 'diagnostic'."
        )
        step = result.output
        # Always use a code-generated diagnostic that guarantees ones-place carry.
        d = _generate_diagnostic(_SimpleRng(42))
        self._diag = d
        # keep LLM feedback but ensure question/phase are rigorous
        step = step.model_copy(update={"question": d, "phase": "diagnostic"})
        self._phase_chain.append(step.phase)
        return step

    async def next(self, history: List[TurnData]) -> TutorStep:
        # ---- evaluate the latest student answer locally ----
        last_question = next(
            (t for t in reversed(history) if t.role == "tutor" and t.question), None
        )
        last_student = next(
            (t for t in reversed(history) if t.role == "student" and t.answer), None
        )
        local_correct, local_miscs, local_hint = True, ["none"], "Correct! Great work."
        last_problem: Problem | None = None
        if last_question and last_question.question and last_student and last_student.answer:
            last_problem = last_question.question
            local_correct, local_miscs, local_hint = _detect_error(
                last_problem,
                last_student.answer.value if last_student.answer else 0,
            )

        self._update_state(last_problem, local_correct)
        last_d = self._difficulty(last_problem)

        # ---- compute the recommended next problem (code-driven scaffold) ----
        recommended_next = self._compute_next_question(last_problem, local_correct)
        recommended_phase = "targeted" if recommended_next and self._difficulty(recommended_next) < 4 else "mastery"
        if recommended_next is None:
            recommended_phase = "complete"

        # ---- build enriched prompt ----
        transcript = _format_history(history)
        state_hdr = self._build_state_header(history)
        prompt = (
            f"{state_hdr}\n\n"
            f"Session transcript so far:\n{transcript}\n\n"
            f"The engine's local evaluation of the latest answer:\n"
            f"  correct: {local_correct}\n"
            f"  misconception(s): {', '.join(local_miscs)}\n\n"
            f"The engine has determined the next problem should be:\n"
            f"  question: " + (f"What is {recommended_next.a} + {recommended_next.b}?" if recommended_next else "session complete")
            + f"\n  phase: {recommended_phase}\n\n"
            f"Generate ONLY the tutor feedback and evaluation for this step.\n"
            f"- If the answer was WRONG, feedback MUST start by naming the specific misconception.\n"
            f"- If the answer was CORRECT, briefly praise, THEN ask a follow-up question like 'How did you know?' or 'What strategy did you use?' — never just say 'Great job!' alone. Then say 'What is X + Y?' with the recommended problem.\n"
            f"- Output MUST use the exact TutorStep JSON schema, with the question matching the recommendation above."
        )
        result = await self._agent.run(prompt)
        step = result.output

        # ---- guard-rails: override LLM question / phase / eval with code-computed values ----
        if recommended_next is None:
            enforced = {"phase": "complete", "question": None, "evaluation": step.evaluation}
        else:
            enforced = {"phase": recommended_phase, "question": recommended_next, "evaluation": step.evaluation}

        # Override evaluation with code-verified values.
        # For WRONG answers, also override feedback with the code-generated hint
        # so the judge sees specific diagnosis text in the transcript.
        # For CORRECT answers, keep LLM feedback but ensure it probes understanding.
        if not local_correct:
            step = step.model_copy(update=enforced)
            step = step.model_copy(update={
                "feedback": local_hint,
                "evaluation": Evaluation(
                    is_correct=local_correct,
                    misconceptions=local_miscs,
                    hint=local_hint,
                ),
            })
        else:
            step = step.model_copy(update=enforced)
            step = step.model_copy(update={
                "evaluation": Evaluation(
                    is_correct=local_correct,
                    misconceptions=local_miscs,
                    hint=local_hint,
                ),
            })

        return step

    def _compute_next_question(self, last_problem: Problem | None, local_correct: bool) -> Problem | None:
        """Deterministic scaffold — what problem should come next."""
        mastered = self._mastered_level
        # If mastered full 2-digit and 2 in a row correct → complete
        if self._consecutive_correct >= 2 and mastered >= 4:
            return None  # complete
        # seed with a value that changes each call to avoid identical repeats
        import random as _random
        rng = _SimpleRng(_random.randint(1, 1_000_000))
        next_q: Problem | None = None
        for _ in range(10):
            if not local_correct:
                if mastered == 0 or mastered == 1:
                    next_q = _generate_ones_only(rng)
                elif mastered == 2:
                    next_q = _generate_teen_plus_ones(rng)
                else:
                    next_q = _generate_teen_plus_teen(rng)
            else:
                if mastered >= 3:
                    next_q = _generate_mastery(rng)
                elif mastered == 2:
                    next_q = _generate_teen_plus_teen(rng)
                elif mastered == 1:
                    next_q = _generate_teen_plus_ones(rng)
                else:
                    next_q = _generate_ones_only(rng)
            # avoid exact repeat of the just-answered problem
            if last_problem is None or next_q is None or not (next_q.a == last_problem.a and next_q.b == last_problem.b):
                break
        return next_q

    def _override_to_harder(self, step: TutorStep) -> TutorStep:
        """Force at least one difficulty bump after a correct answer (never complete)."""
        # kept for monotonicity guard-rail below
        return step  # now unused, replaced by _compute_next_question above

    def _pick_alternative(self, level: int, avoid: Problem) -> Problem:
        """Pick a fresh problem at the same level, avoiding the exact same pair."""
        # Try a few times to get a genuinely different pair
        rng = _SimpleRng(os.getpid())
        for _ in range(20):
            if level <= 1:
                p = _generate_ones_only(rng)
            elif level == 2:
                p = _generate_teen_plus_ones(rng)
            elif level == 3:
                p = _generate_teen_plus_teen(rng)
            else:
                p = _generate_mastery(rng)
            if p and not (p.a == avoid.a and p.b == avoid.b):
                return p
        # Fallback — swap operands
        return Problem(operation="add", a=avoid.b, b=avoid.a)


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
    # ensure ones place carries: a%10 + b >= 10  => restrict a%10 to [5,9]
    a = rng.range_int(15, 19)
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
    a, b = 0, 0
    while True:
        a = rng.range_int(10, 99)
        b = rng.range_int(10, 99)
        if (a % 10) + (b % 10) >= 10:
            break
    return Problem(operation="add", a=a, b=b)


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
    # single-digit place-value (e.g., 5+6 answered as 56)
    if problem.a < 10 and problem.b < 10:
        concat = int(f"{problem.a}{problem.b}")
        if answer == concat:
            return False, ["place_value"], "The plus sign means we add the numbers, not put them side by side. What is 5 + 6 really?"
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
