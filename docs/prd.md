# Product Requirements Document

## Problem
Elementary students often memorize arithmetic procedures without understanding why they work. When a student adds `27 + 35` and writes `512`, the root cause can be any of several misconceptions — but traditional worksheets just mark the answer wrong.

## Vision
A tutor that:
1. **Diagnoses** the specific misconception behind each wrong answer.
2. **Adapts** by generating targeted problems that isolate the gap.
3. **Guides** via Socratic questioning — never giving the answer, only nudges.

## MVP Scope
- **Concept:** 2-digit addition with carrying (the "extra ten").
- **Misconceptions tracked:**
  - *omit_carry* — adds columns correctly but forgets the carry.
  - *place_value* — treats digits as independent numbers or concatenates them.
  - *basic_fact* — single-digit addition error despite correct strategy.
- **Flow:**
  1. Diagnostic problem (guarantees a carry).
  2. If wrong → targeted practice (simpler carry problems until correct).
  3. If correct (or after targeted recovery) → mastery problems (mixed difficulty).
  4. Two consecutive correct mastery answers → session complete.
- **UI:** Minimal chat interface. Semantic markup, no styling (designer-ready).

## Out of scope for MVP
- Subtraction, multiplication, division.
- Progress persistence across server restarts.
- Student identity / login.
- Voice, animation, or gamification.
