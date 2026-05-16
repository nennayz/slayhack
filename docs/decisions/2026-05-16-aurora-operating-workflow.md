# 2026-05-16 — Aurora operating workflow

**Status:** Accepted

## Context

Aurora already supports a working content pipeline with crew-linked stages:

```text
Robin -> Mia -> Zoe -> Bella -> Lila -> Nora -> Roxy -> Emma -> Publish
```

That linear route is useful for a single content mission, but it is not enough for the operating model Nayz wants:

- A central team should discover and validate new page/project ideas.
- Existing pages, such as Slay Hack, should have dedicated PMs.
- PMs need daily content calendar planning, not only one-off briefs.
- Slay Hack needs at least 2 articles, 2 infographics, and 2 videos per day.
- Videos need storyboard-first planning, especially for 60-180 second work where scene timing depends on tools such as Veo3.
- Google Drive and Notion need to be part of duplicate checks and asset memory.
- Published work needs a performance loop that turns engagement into scale, repair, or lesson-learned decisions.
- Daily profile presence such as Bubble/status updates should stay lightweight and not require a full production run.
- Real comments after publishing need a safe response lane where Nayz can send screenshots or pasted comment text to Emma.
- Team members must be able to ask questions, route work sideways, or send work back to specialists.

## Decision

Aurora will evolve from a single linear pipeline into a multi-route content operating system.

The durable workflow is documented in:

```text
docs/aurora_operating_workflow_v2.md
```

Aurora v2 will use six mission types:

1. `new_project_discovery`
2. `content_calendar_plan`
3. `production_batch`
4. `daily_bubble_status`
5. `comment_response`
6. `performance_review`

Aurora v2 should use modular routing instead of forcing every job through every agent. Robin routes each mission through the smallest useful lane for the content type.

The existing crew remains the core team. New specialist roles should be introduced only when they remove real operational ambiguity or prevent repeated work:

- Mara Vale / Market & Monetization Analyst
- Vera Reel / Video Producer
- Sage Ledger / Lesson Librarian / Archivist
- Iris Gauge / Growth Analyst

Several responsibilities remain as modes under existing roles instead of becoming separate people:

- Calendar planning stays with PM and Robin.
- Infographic production stays with Lila.
- Lesson library stays with Sage Ledger.
- Monetization strategy stays with Mara Vale.
- Daily Bubble/status belongs to Emma with optional Roxy timing support.
- Post-publish comment replies belong to Emma, with Nora reviewing only sensitive or risky replies.

Vera Reel / Video Producer is a first-class role from the start because long-video output is central to the Slay Hack workflow and needs storyboard-first planning before generation.

## Consequences

This makes Aurora closer to how the work actually happens. PMs can own pages, central specialists can serve multiple pages, and performance data can feed future planning instead of living only as reports.

The existing pipeline should remain operational while v2 is introduced. Early implementation should add models and dashboard surfaces before replacing agent flow.
