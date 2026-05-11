# ADR 001: Structured Output First

## Context
The LLM must reliably return fields like `is_correct`, `misconceptions`, and `next_question` — not free text. Unstructured output requires regex or manual parsing, which breaks when the model format shifts.

## Decision
Use PydanticAI with `result_type=TutorStep`. The framework enforces the schema against the model response and auto-retries if validation fails.

## Consequences
- **Positive:** Parsing is robust; no custom extraction code. Type hints flow from model to API to frontend.
- **Negative:** Adds a Python dependency. Slightly higher inference cost than raw completion because schema is injected into the prompt.
