# ADR 004: Semantic Markup UI

## Context
We need the UI to be functional now but easy for a designer to improve later without touching the backend.

## Decision
Build the frontend with plain semantic HTML inside React — no CSS framework, no component library, no styling beyond the browser default. The goal is "pure markup that a designer can enhance later."

## Consequences
- **Positive:** Zero styling dependencies. Designer can drop in a theme or stylesheet without fighting Tailwind classes or CSS-in-JS.
- **Negative:** Looks bare until a designer touches it. That's intentional.
