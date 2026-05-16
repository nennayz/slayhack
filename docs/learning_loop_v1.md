# NayzFreedom Daily Learning Loop v1

**Status:** Working process
**Date:** 2026-05-16
**Scope:** NayzFreedom Fleet, Codex collaboration, Aurora operations, creative review, and beginner-friendly guidance

## Purpose

NayzFreedom should improve every day from three kinds of evidence:

1. What Nayz asked for and decided.
2. What worked or failed in the system.
3. What the audience and performance data reveal after publishing.

This is not model training. It is an operating loop: capture useful signals, turn them into lessons, and feed those lessons into the next decision.

## Learning Sources

| Source | What to capture | Owner |
|---|---|---|
| Daily commands | What Nayz wanted today, what changed, what became priority | Robin |
| Conversation feedback | What Nayz liked, disliked, rejected, or corrected | Sage Ledger |
| Creative review | Approved styles, rejected styles, reference anchors, naming choices | Sage Ledger |
| Operational work | Tests, deploys, failures, incidents, repeated manual steps | Robin / Nora |
| Performance data | Views, retention, saves, shares, comments, conversion | Iris Gauge |
| Audience comments | Repeated questions, objections, useful language from followers | Emma / Sage Ledger |
| Beginner friction | Where Nayz needed explanation, a safer default, or a clearer workflow | Robin |

## Daily Cycle

### 1. Start-of-Day Captain Brief

At the start of a working day, Robin should establish the operating target:

- What is the main goal today?
- Which ship/page/project matters most?
- Is today a build day, review day, publish day, or learning day?
- What is blocked?
- What should not be touched today?

If Nayz does not provide this, Robin should infer from the latest repo state and ask only for the missing decision that materially changes the work.

### 2. During-Work Decision Capture

Whenever Nayz approves, rejects, or corrects something, capture the decision in plain language.

Examples:

- "Nayz prefers Iris-style glossy semi-realistic 3D over ultra-real cinematic renders."
- "Nayz wants review assets kept local until visual direction is approved."
- "Nayz is still learning the system and wants direct recommendations, not only options."

This should not interrupt the work. Capture it as part of the final summary or daily learning brief.

### 3. End-of-Task Learning Note

At the end of meaningful work, the assistant should produce a short learning note:

- What changed?
- What Nayz liked or disliked.
- What should be repeated next time.
- What should be avoided next time.
- What follow-up would make the system more efficient.

For code or dashboard work, include verification. For creative work, include the approved visual anchors and rejected directions.

### 4. End-of-Day Daily Learning Brief

At the end of each day, create one brief using `docs/templates/daily_learning_brief.md`.

The brief should answer:

- What did we learn about Nayz's preferences today?
- What did the system learn operationally?
- What should Robin do differently tomorrow?
- What should Sage store as durable knowledge?
- What should Iris check when performance data exists?
- What should Nayz do next as the beginner Captain?

### 5. Weekly Consolidation

Once per week, Sage Ledger should consolidate repeated daily lessons into durable docs:

- Accepted architecture or product choices -> `docs/decisions/`
- Repeated workflow rules -> relevant workflow docs
- Character or brand direction -> character/brand docs
- Personal/private reflections -> private vault only, not repo
- Performance patterns -> job performance summaries and weekly reports

Do not promote one-off opinions into durable rules until they repeat or Nayz explicitly locks them.

## Direct Guidance Contract

Nayz is still learning. The assistant should be direct when a clearer process would save time, prevent mistakes, or improve quality.

The assistant should proactively advise when:

- The request is broad and will produce messy output without a review gate.
- The system is about to touch production, deploy, publish, or overwrite live assets.
- A task is creative and high-variance, such as character art, naming, brand style, or visual identity.
- A manual workflow is being repeated and should become a template, command, script, or dashboard action.
- There is no metric or evidence for a growth decision.
- Nayz is choosing between multiple paths and one path is clearly safer or more efficient.
- The next step depends on environment, credentials, data privacy, or platform rules.

The assistant should say:

- "Recommended path: ..."
- "Reason: ..."
- "Risk if we skip this: ..."
- "Smallest next action: ..."

The assistant should not hide tradeoffs to be polite. Clear warnings are part of the system.

## Storage Rules

| Learning type | Storage |
|---|---|
| Temporary task notes | Final response and local review folders |
| Daily learning brief | `docs/learning/daily/` if it is project-safe |
| Durable project rule | Relevant doc in `docs/` |
| Accepted major decision | `docs/decisions/` |
| Performance evidence | `output/<page>/<job>/job.json` and reports |
| Private personal reflection | Private vault only |
| Codex cross-session memory | Only when Nayz explicitly asks to save memory |

## Role Responsibilities

| Role | Learning responsibility |
|---|---|
| Nayz | Gives direction, approves taste, decides priorities |
| Robin | Turns learning into better routing and next actions |
| Iris Gauge | Reads performance and detects scale/repair patterns |
| Sage Ledger | Stores reusable lessons and prevents repeated mistakes |
| Nora Sharp | Captures quality failures and risk rules |
| Emma Heart | Captures recurring audience questions and reply patterns |
| Roxy Rise | Turns performance lessons into timing, captions, and platform packaging changes |

## Practical Daily Prompt

Use this at the end of a day or work block:

```text
Create today's NayzFreedom learning brief.
Include:
- what I asked for
- what I liked
- what I disliked
- what you recommend I do next
- what should become a reusable rule
- what should not be stored because it is private or still undecided
```

## Quality Bar

A learning note is useful only if it changes future behavior.

Bad:

```text
We worked on character images today.
```

Good:

```text
For character images, Nayz rejected generic realistic cinema and preferred Iris-style glossy semi-realistic 3D fashion-game renders. Future portrait work should start with one sample, compare it to Iris/Sage/Slay anchors, then generate the full roster only after approval.
```
