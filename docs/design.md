# High-Level Design

## Domain model

A session is a sequence of **Turns**:
- `tutor` — spoke (asked a question, or gave feedback)
- `student` — answered (provided a number, optionally an explanation)

Only the turn transcript is persisted. There is no session-scoped "state machine" object.

## TutorStep contract

The agent **always** returns the same shape, whether from `start()` or `next(history)`:

```python
TutorStep(
    feedback="what the tutor says to the student",
    evaluation=Evaluation(
        is_correct=True/False,
        misconceptions=["omit_carry"],
        hint="the core idea the student missed"
    ),
    question=Problem(operation="add", a=27, b=35),  # or None if done
    phase="diagnostic" | "targeted" | "mastery" | "complete"
)
```

This contract keeps the UI, API, and tests decoupled from whatever reasoning happens inside the agent.

## Phases

| Phase | Goal | How many correct to exit |
|-------|------|--------------------------|
| **Diagnostic** | Smoke test for carrying | 1 correct → mastery |
| **Targeted** | Isolated carry practice | 1 correct → mastery |
| **Mastery** | Mixed problems, no hints | 2 consecutive correct → complete |
| **Complete** | Done | — |

## Socratic principles enforced

1. **No answer given** — the `hint` field must guide, never state the answer.
2. **One problem at a time** — the `question` field contains exactly one problem.
3. **Misconceptions, not just correctness** — wrong answers are categorized so the tutor can target the specific gap.

## Extensibility hooks

- New operation (subtraction): add `operation: "subtract"` to `Problem`, update the agent system prompt.
- New misconception: add to `Evaluation.misconceptions`, add detection rule in `FakeAgent`, add to system prompt in `LlmAgent`.
- Persistent sessions: replace `SessionStore` (in-memory dict) with a database backend; routes stay the same.
