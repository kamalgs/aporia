# AI Tutor Platform — Design Spec

**Status:** Draft for review
**Date:** 2026-05-12

## 1. What we're building

An AI tutor that runs a one-on-one coaching relationship with a learner across many subjects and many sessions. Subject specialists author the content; the framework runs the relationship. The experience should feel like a thoughtful human tutor — paced to the learner, fluid, attentive, never marching through a curriculum — and should remain responsive enough that a low-attention learner stays in the flow.

The current code in this repo is an early prototype scoped to one math topic. It is reference material, not a base to preserve.

## 2. Principles

- **Subject-agnostic core.** The framework has no subject-specific logic. Math, language, history, coding, soft-skills coaching — all run on the same engine. Subject knowledge lives in authored content, not in code.
- **Personal coaching, not curriculum.** No fixed prerequisite graph, no rigid lesson sequence. The system holds a model of the learner and decides moment-to-moment what serves them.
- **Authored content over hardcoded rules.** Specialists write loose, human-readable documents — guidelines, markers, examples. The framework leans on language models to flesh these out into live interactions.
- **Three timescales, three roles.** Turn-level dialogue, session-level planning, and durable identity-building each get a dedicated role so prompts stay focused and reasoning happens at the right cadence.
- **Humans in the loop.** A real tutor can observe and shape any live session, and can review past sessions asynchronously. Their input feeds back into the learner's durable record.
- **Responsiveness is a feature.** Short attention spans are assumed. The system optimises for first-token latency, predictable pacing, and short sessions by default.
- **Forward-compatible, not over-built.** v1 is deliberately small. The data shapes and extension points are chosen so multimodal content, spaced repetition, MCQ/match/quiz formats, and additional roles can be added without restructuring.

## 3. Domain model

The system reasons about six things.

- **Skill** — an atomic unit of what a learner can come to know or do. Specialist-authored. A brief describing the objective, what mastery looks like, common mistakes with example student responses, sample exchanges, and topic tags. Skills are not arranged in a prerequisite graph.
- **Program** — a coherent body of work a learner can be enrolled in. Specialist-authored. References a set of in-scope skills, marks which are mandatory for completion, and states the assessment criteria for completion in plain language. Programs and skills are many-to-many.
- **Subject teaching guide** — how a subject is taught well: tone, pacing, what counts as a strong vs. weak answer, when to push and when to comfort. Specialist-authored. A program references one.
- **Learner-cohort guide** — how to work with learners of a given developmental or contextual cohort (e.g., 7–9 year olds, adult beginners, ESL learners). Specialist-authored. Matched to a learner by demographic context; the match itself is authored, not hardcoded.
- **Learner** — a person using the system. Identified initially by a chosen name plus a cookie-bound id. Schema is shaped for a future multi-user platform, but accounts and auth are not part of v1.
- **Session** — one sitting of interaction. Sessions are short by default (a few minutes to a quarter hour), easy to resume, and accumulate into the learner's durable record.

Two derived pieces of state belong to the learner:

- **Learner portrait** — durable, cross-program, cross-session. A short narrative the system maintains over time (traits with evidence, observed patterns, what works for them), readable as if a tutor had written it after each session.
- **Program state** — per-program working memory. Per-skill progress signals, recent affective signals, in-flight notes for the current program. Reset or branched when the learner enters a new program; the learner portrait carries forward.

Specialists ship four kinds of authored artifacts: programs, skills, subject teaching guides, and learner-cohort guides. All are loose markdown with light frontmatter, versioned in git in a `content/` directory, and loaded into an in-process registry at startup. Hot-reload in development; reload-on-deploy in production.

## 4. Roles and timescales

The system has three reasoning roles, each operating at its own cadence.

| Role | Cadence | Reads | Writes |
|---|---|---|---|
| Turn-level role | every learner turn | the current intent + the relevant skill brief + recent transcript + the learner's input | the next utterance + a turn signal |
| Session-level role | session start, on threshold triggers, on human input | program + learner portrait + program state + subject teaching guide + recent transcript + any pending human input | an intent + a patch to program state |
| Identity role | end of session, end of program, on milestones | the closed transcript + program-state delta + prior learner portrait + learner-cohort guide | an updated learner portrait |

**Why split this way.** The turn-level role's prompt stays small and focused on the immediate exchange, which is what keeps the dialogue fluent. The session-level role reasons over slow-changing state at a coarse cadence; running it every turn would be wasteful and would make its prompt sprawl. The identity role works async at session boundaries, has space to reflect, and is the place a human can sensibly review and edit — a learner portrait is something a tutor recognises.

**Intent** is the contract from the session role to the turn role. It carries a goal (warm-up, probe, teach, drill, consolidate, rest, wrap, and additional goals as needed later for play / review-due / quiz), the skill in focus, a difficulty hint, a short rationale for logs and human-tutor view, and an optional tone note. The turn role does not plan; it executes the intent.

**Turn signal** is the contract from the turn role back. It carries: was the response on-target, which authored mistake patterns matched (if any), affective signals observed, and any free-form notes. A deterministic updater folds it into program state; no language model is involved in that update.

**Trigger policy for the session role.** It runs at session start, when a turn signal crosses a threshold (mastery move, repeated failure, frustration spike, skill complete, rubric satisfied), and when a human tutor submits guidance or a steer. Most turns reuse the existing intent — so most turns are a single language-model call.

**Role specialisation.** Both the session role and the identity role are *roles*, not single global agents. Each session loads a subject teaching guide (selected by the active program) into the session role, and a learner-cohort guide (selected by the learner's demographic context) into the identity role. The turn role stays generic and executes whatever intent and skill brief it is handed.

## 5. Calibration

Calibration is continuous and invisible. There is no upfront placement test. A session opens with a warm-up at the learner's likely current level, then adapts — jumping forward when they look comfortable, dropping back when they don't, in conversational moves rather than test items. The structure exists in the session role's planning; the learner does not see it.

For a brand-new learner, calibration draws on the learner-cohort guide for sensible defaults and updates the program state rapidly during the first session. By the end of the first sitting, the portrait and program state carry enough signal to start the next session in a more informed place.

## 6. Human tutor in the loop

A human tutor is a first-class participant, not a special case. Tutor identity is its own record so multi-tutor settings work later.

A tutor can **attach** to a live session in one of four modes:

- **Observe.** Read-only live view: learner turns, the turn role's replies, the session role's decisions with rationale, and program-state updates. Real-time event stream.
- **Whisper.** A free-text note attached to the session. The session role picks it up as guidance on its next call and decides how to incorporate it. The note is logged alongside the resulting intent so the tutor can see how it landed.
- **Steer.** A structured directive: change the active skill, change the goal, set difficulty, mark a skill as mastered, force a wrap. Bypasses the session role's discretion. Logged.
- **Take over.** Pauses both reasoning roles. The tutor types directly to the learner until they hand back. Their exchanges are added to the transcript normally; when the agent resumes, the turn role sees them and the identity role reflects on them later.

A tutor can also work **asynchronously**: browse past sessions, leave comments on specific turns, and those comments feed the identity role's next reflection. Human judgement shapes the durable learner portrait over time.

In the code, the human channel is two extra input fields on the session role's call (pending guidance, pending steer) and one output stream of session events. There are no special branches in the main path — which is what keeps the human channel from rotting.

## 7. Per-turn data flow

The hot path is small. Most turns are a single language-model call.

1. Learner input arrives at the session endpoint.
2. The server appends the input to the transcript as a typed event and publishes it on the session event stream.
3. The turn role is called with the current intent, the relevant skill brief, a transcript window, and the learner's input. It returns the next utterance and a turn signal.
4. A deterministic updater folds the turn signal into program state.
5. The server appends the turn role's output to the transcript, publishes it, and persists the state update.
6. The trigger policy checks whether the session role should run. If yes, it runs; the resulting intent is appended and published. If no, the existing intent continues.
7. The response is returned to the client.

Session lifecycle: the session role runs cold at start with a warm-up goal; the turn role produces the first utterance. The session ends when the learner stops, the session role calls wrap, or the program rubric is satisfied. The identity role then runs async on the closed transcript and updates the learner portrait.

## 8. Persistence

Postgres from day one. The schema is deliberately coarse and denormalised. It will be normalised later when query patterns demand it.

- **`learners`** — id, name, cohort tags, portrait (markdown narrative), traits (structured JSON), program states (JSON keyed by program id), timestamps.
- **`sessions`** — id, learner id, program id, started_at, ended_at, status, transcript (ordered typed-event log), summary (markdown reflection written by the identity role at session end).

Everything that happens in a session — learner inputs, turn-role utterances, session-role intents, human-tutor inputs, milestone markers — is stored as typed events inside the single `transcript` column. Single-row reads, easy to inspect, easy to export. When access patterns demand normalisation, the migration is straightforward.

Authored content lives as markdown files in `content/programs/`, `content/skills/`, `content/coach_profiles/`, `content/guardian_profiles/`. It is not synced into the database; the registry loads from disk at startup.

A live event stream for human-tutor observation is an in-process pub/sub keyed by session id, with replay from the transcript. No external broker.

## 9. Responsiveness

Two complementary mechanisms keep the experience flowing.

**Fast model for the turn role.** The turn role runs on a small, fast model by default. The session role uses a more capable model but runs rarely, so it does not pace the experience.

**Speculative branch pre-generation.** As soon as the turn role posts an utterance, the server kicks off background generation of likely next responses. The skill brief's "common mistakes" section enumerates the predictable branches; the turn role's reply for each is generated in parallel at low temperature while the learner is typing. When the real input arrives, a cheap classifier matches it to a branch — exact match for closed-form answers, embedding or rule match for free text, or a small judge model where needed. A hit serves the cached reply; a miss falls through to a live call. The cache is keyed by the current intent and invalidated if the intent changes.

**Streaming.** Turn-role utterances stream token-by-token to the frontend regardless of caching; first token in roughly 200 ms is the target even on cache miss.

The skill brief is the anchor for both pedagogy and speed. Specialists writing good "common mistakes" examples directly improves both.

## 10. Subject-agnostic core (constraints on the implementation)

The framework code holds these constraints. They are testable.

- No subject-specific types in the core. Anything resembling math, language, or any other domain lives in content packs.
- Skill briefs declare their own response-classification approach: closed-form match, keyword/regex, embedding similarity, a small judge call, or "live language model". The framework dispatches uniformly; speculation works against whatever the brief declares.
- Per-skill program-state shape is free-form JSON. The framework does not enforce that mastery is a scalar. Helpers (e.g., exponential moving averages) exist as utilities, not as a fixed model.
- No assumed learner age. Adult-learner cohort guides ship alongside child ones; tone comes from the loaded guides.
- Sessions are short by default. Long sessions are possible but not the shape the system optimises for.

## 11. Forward-compatibility constraints

v1 builds none of the following, but v1 must not preclude any of them.

- **Multimodal turns.** Transcript events are typed (`utterance`, `learner_text`, `mcq`, `match`, `ordering`, `image_prompt`, `audio_prompt`, etc.). v1 emits only the text variants; adding image or audio is a new event kind and a renderer, not a transcript migration.
- **Item formats beyond Socratic dialogue.** Skill briefs may declare which formats they support (Socratic, MCQ, match-the-following, drill, quiz, trivia). The session role's intent picks a format; the turn role and the frontend render accordingly. Speculation works the same way across formats.
- **Spaced repetition.** Per-skill program state is free-form JSON; it can carry `next_due_at`, `recall_strength`, and similar fields without schema change. A scheduler service feeding a `review_due` goal into the session role's planning is additive.
- **Additional reasoning roles.** Adding a fourth role later (e.g., a long-horizon planner across programs) is additive — it consumes the same authored content and writes to the same learner record.

## 12. Build order

The current prototype is discarded. The build proceeds in steps; each step is shippable to master, but there is no requirement to preserve the prototype's behaviour at any point.

1. **Scaffold.** Two-table schema; typed-event transcript; `content/` directory layout and registry; frontend rewritten around event-typed turns with renderers keyed by event kind.
2. **Turn role and first skill.** Minimum viable agent: a turn role that runs Q&A against a single skill brief, emitting events. Port the existing math-2-digit-addition topic as the first skill pack. End-to-end usable for one skill, no planning yet.
3. **Session role, program, subject teaching guide.** Add planning with the intent contract. Skill switching works inside a program. The math program is declared with mandatory skills and an assessment rubric.
4. **Identity role, learner portrait, cohort guide.** Cross-session memory. The session role reads the portrait when planning. The identity role runs at session end.
5. **Human tutor channel.** Tutor identity, attachment, event stream, whisper / steer / takeover / async annotations. Minimal tutor UI.
6. **Responsiveness.** Switch the turn role to a small/fast model. Background speculative branch generation with intent-keyed cache invalidation. Token streaming to the frontend.
7. **Second subject as smoke test.** Ship one non-math content pack (vocabulary or short-form trivia, adult-learner cohort). If the core needs touching to make it work, that is a framework leak — fix before declaring v1 done.

The evaluation harness is rebuilt at step 2 against the new event shape. Scenarios are re-expressed and expanded each step: planning scenarios at step 3, identity-role scenarios at step 4, human-intervention scenarios at step 5. The eval harness is the regression net throughout.

Implementation-level details — prompt assembly, role glue, today's tuning notes, fallback handling — live in scratch files in the working branch and are stripped before each PR merges to master. This spec carries only the durable decisions.

## 13. Out of scope for v1

- Authentication and accounts.
- Multimodal turns (images, audio, video).
- Item formats beyond Socratic dialogue.
- Spaced repetition scheduling.
- Multi-tutor coordination beyond tutor identity existing as a record.
- A web-based authoring tool for specialists (authoring is via markdown files in git, reviewed by PR).
- Cross-program planning (e.g., suggesting a new program when one completes).
