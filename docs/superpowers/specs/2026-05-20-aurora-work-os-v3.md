# Aurora Work OS v3

**Status:** Implementation spec
**Scope:** Work-phase operating system for NayzFreedom Fleet creator/business workflows
**Safety posture:** Offline-first, Captain-reviewed, no live posting/checkout/affiliate execution in v1

## Purpose

Aurora Work OS v3 turns the existing Fleet pieces into a simpler daily operating system:

```text
Page / Brand
→ Signal / Reference Example
→ Idea
→ Content Plan
→ Content Slate
→ Production Ticket
→ Artifact
→ Social Package
→ Publish Queue
→ Performance / Learning
→ Monetize Opportunity
```

The goal is practical work output, not more agents. Every item must have an ID, page, source/parent, status, next action, and artifact/reference path when available.

## Current repo foundation

Implemented foundations that v3 reuses:

- Trend Scout: `trend_scout_pipeline.py`, `/scout/`, scheduler trend scan.
- Idea Bank: `idea_planner_pipeline.py`, `/ideas`, Knowledge Store idea objects.
- Production: `production_loop.py`, `orchestrator.py`, `ContentJob` output folders.
- Social packaging: `social_packaging.py`, `output/publish_queue.jsonl`, live publish locked.
- Comment assistant: `comment_reply_bot.py`.
- Knowledge Store: Obsidian/vault-first notes + SQLite index + dedup/embed backfill.
- Monetize governance: `/aurora/ebooks` and e-book runbook.
- Personal/Freedom/Lyra: concept placeholders only.

## Missing center

The old system can discover, generate, and package, but it lacks a command/planning layer. v3 adds the missing center:

1. `ContentPlan` — a serious plan made from an idea or manual direction.
2. `ContentSlate` — today's/weekly page plan.
3. `ProductionTicket` — the production contract consumed by production loops.
4. `PublishQueueReview` — local approval/rejection over generated social packages.
5. `DailyWorkBrief` — one page showing today's decisions and next actions.
6. `BubbleMessage` — proactive page status/story prompt for daily presence.
7. `MonetizeOpportunity` — safe registry for e-book/affiliate/offer ideas.

## Object model

### ContentPlan

Fields:

- `id`
- `page`
- `source_idea_uid`
- `pillar`
- `objective`: `reach`, `save`, `share`, `revenue`, `community`, `learning`
- `content_type`: `article`, `image`, `infographic`, `short_video`, `long_video`, `prompt_only_video`, `bubble`
- `target_platforms`
- `hook`
- `angle`
- `production_brief`
- `publish_window`
- `status`: `draft`, `approved`, `ticketed`, `done`, `rejected`

### ContentSlate

Fields:

- `id`
- `date`
- `page`
- `daily_focus`
- `plan_ids`
- `status`: `draft`, `approved`, `in_production`, `completed`

### ProductionTicket

Fields:

- `id`
- `plan_id`
- `page`
- `ticket_type`
- `brief`
- `required_assets`
- `acceptance_criteria`
- `status`: `queued`, `in_progress`, `qa_ready`, `production_ready`, `blocked`, `done`
- `artifact_path`

### PublishQueueReview

Fields:

- `package_id`
- `job_id`
- `status`: `pending`, `approved`, `rejected`, `posted_manually`
- `review_note`
- `reviewed_at`

### BubbleMessage

Fields:

- `id`
- `page`
- `date`
- `story_prompt`
- `bubble_text`
- `trend_context`
- `status`: `draft`, `approved`, `used`, `archived`

### MonetizeOpportunity

Fields:

- `id`
- `page`
- `source`
- `offer_type`: `ebook`, `affiliate`, `lead_magnet`, `sales_page`, `website`, `course`, `other`
- `audience_pain`
- `suggested_offer`
- `matching_content_ids`
- `risk_notes`
- `status`: `new`, `researching`, `approved`, `building`, `live`, `archived`

## Storage strategy

v1 starts with local offline files under:

```text
output/work_os/
```

This keeps v3 safe and inspectable while the planner matures. Content Planner v1 now reads approved Knowledge Store ideas (`kind="idea"`, `status="approved"`) into idempotent `ContentPlan` drafts keyed by `source_idea_uid`, then mirrors newly created plan drafts back into the Knowledge Store as `kind="content_plan"` with the source idea in `parent_uids`. The operational review/queue state remains local JSON for v1 so Captain approval and production-ticket handoff stay reversible and easy to inspect.

Recommended long-term storage:

- Obsidian/vault: source of truth for text/metadata.
- SQLite: index/search/cache.
- Google Drive: large binary assets and backups.
- Notion: optional presentation layer only, not source of truth.

## Routes

v1 command surfaces:

- `/aurora/planner` — content plans, slates, production tickets.
- `/aurora/publish-queue` — local review for social packages; no live API.
- `/aurora/work-brief` — daily work command center.
- `/aurora/bubbles` — daily bubble/status planner.
- `/aurora/monetize` — safe opportunity registry.
- `/freedom/daily-brief` — low-sensitivity Nami daily brief.

## Production loop rule

Production must stop pulling ideas directly once ticketed planning is available. The compatibility path can remain, but the preferred path is:

```text
ContentPlan approved
→ ContentSlate draft/approved
→ ProductionTicket queued
→ production loop consumes ticket
→ artifact/package
```

Content Planner v1 supports this path with local review actions:

- sync approved KS ideas into draft plans,
- approve/reject plans,
- create today's slate from approved/ticketed plans,
- approve slate,
- create tickets only from approved/ticketed plans.

## Locked boundaries

v1 must not:

- call live social publishing APIs,
- activate checkout,
- scrape/insert affiliate links automatically,
- import private finance/investment/song catalog data,
- store sensitive personal data in the work dashboard.

## MVP definition

The MVP is usable when Captain Nayz can open one set of pages and see:

- today's trends/ideas/plans,
- content slate by page,
- production tickets ready to run,
- publish packages waiting for manual review,
- bubble/status suggestion,
- comment assistant remains separate,
- monetize opportunities captured safely,
- Nami daily brief without sensitive data.
