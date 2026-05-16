# Aurora Operating Workflow v2

**Status:** Draft for implementation
**Date:** 2026-05-16
**Scope:** NayzFreedom Fleet, The Aurora dashboard, page/project PMs, central crew specialists

## Purpose

Aurora v1 behaves mostly like a single content pipeline:

```text
Robin -> Mia -> Zoe -> Bella -> Lila -> Nora -> Roxy -> Emma -> Publish
```

Aurora v2 should behave like a content operating system. It must support:

1. Discovering and validating new pages/projects.
2. Operating existing pages with a dedicated PM.
3. Planning daily content calendars with fixed minimum output requirements.
4. Producing articles, infographics, short videos, and long videos in parallel.
5. Running QA before publishing.
6. Reading engagement after publishing and turning results into scale, repair, or lesson-learned loops.
7. Allowing PMs and specialists to ask for clarification or route work sideways, not only forward.
8. Responding to real audience comments after publishing when Nayz provides a screenshot or pasted comment.
9. Maintaining light daily profile presence such as Bubble/status updates without forcing a full production run.

The PM owns the page. The central Aurora crew provides specialist help.

## Operating Model

Aurora has two layers:

| Layer | Responsibility | Examples |
|---|---|---|
| Central Aurora Team | Shared specialists used by every project | Robin, Mia, Zoe, Nora, Roxy, Emma, Mara Vale, Vera Reel, Sage Ledger, Iris Gauge |
| Page PM Squad | Dedicated owner and production context for one page | Slay for Slay Hack, Stadium for Stadium Sweethearts, future PMs for future pages |

The central team should not replace the PM. The PM decides what the page should do. The central team supplies research, production, QA, distribution, and learning support.

## Mission Types

Aurora v2 should introduce six mission types.

## Modular Routing Principle

Aurora should not force every job through every agent. Robin routes each mission
through the smallest useful lane.

| Work type | Recommended route |
|---|---|
| Image post | PM -> Robin -> Zoe/Bella if needed -> Lila -> Nora -> Roxy -> Publish |
| Short video | PM -> Robin -> Zoe -> Bella -> Lila -> Vera -> Nora -> Roxy -> Publish |
| Long video | PM -> Robin -> Mia/Zoe -> Bella -> Lila -> Vera -> Nora -> Roxy -> Publish |
| Article | PM -> Robin -> Bella -> Nora -> Roxy -> Publish |
| Community post | PM -> Robin -> Bella/Emma -> Nora -> Publish |
| Bubble/status | PM -> Emma -> Roxy timing if needed -> PM/Nayz approval -> Post |
| Comment reply | Nayz/PM screenshot -> Emma -> Nora if risky -> Nayz/PM approval -> Reply |
| Performance review | Iris -> Sage -> Roxy/Zoe if needed -> PM decision |

Rule: specialist lanes are optional unless the ticket type needs them. The system
should stay fast for small posts and only expand for risky, strategic, or
high-effort work.

### 1. `new_project_discovery`

Used when the team is exploring a new page or project.

Goal: find page concepts with real audience, viral, and monetization potential.

Inputs:

- Captain brief or open research theme.
- Candidate niche or platform signal.
- Existing trend or creator/page example.
- Optional constraints: platform, language, monetization type, visual style.

Core flow:

```text
Robin frames the discovery mission
Mia scans trends and platform signals
Mara Vale studies audience, competitors, and revenue paths
Zoe develops page concepts and initial content angles
Sage Ledger checks memory, Drive, Notion, and prior project history
Nora reviews feasibility and risk
Robin packages the proposal for Captain review
```

Outputs:

- Page concept.
- Target audience.
- Platform focus.
- Content pillars.
- Monetization paths.
- Viral thesis.
- 7-day validation plan.
- Asset needs.
- Risks and open questions.
- Recommendation: build, test, watch, or reject.

Acceptance criteria:

- The concept has a clear audience and repeatable content engine.
- There is at least one plausible monetization path.
- There are at least 20 initial content ideas.
- There is a practical 7-day test plan.
- Duplicates or conflicts with existing Fleet projects are checked.

### 2. `content_calendar_plan`

Used when an existing page PM plans a day or week of content.

Goal: produce a structured content slate that satisfies daily minimums and fits the page strategy.

Default daily minimum:

```yaml
articles: 2
infographics: 2
videos:
  short_video:
    count: 1
    duration: "15-40 seconds"
  long_video:
    count: 1
    duration: "60-180 seconds"
    requires_storyboard: true
```

Core flow:

```text
PM reviews performance, calendar, and goals
Mia brings current signals
Sage Ledger checks Drive and Notion for prior topics and duplicates
Zoe proposes angles and hooks
PM selects the daily slate
Robin turns the slate into production tickets
Nora checks coverage and risk before production begins
```

Outputs:

- Daily or weekly calendar.
- Per-item brief.
- Content type.
- Target platform.
- Hero character or asset need.
- Owner/specialist assignment.
- Deadline and publish window.
- QA expectations.

Acceptance criteria:

- The daily minimum is satisfied or explicitly waived by the Captain.
- Each item has a clear objective: reach, save, share, revenue, community, or learning.
- Existing content history is checked to reduce duplication.
- Video work includes format and storyboard requirements before production.

### 3. `production_batch`

Used when a PM-approved slate is turned into production work.

Goal: produce the assets needed for the daily content slate.

Core flow:

```text
PM dispatches tickets
Article Writer/Bella writes article copy
Lila builds infographic direction
Vera Reel builds scene plans, script handoff, prompts, tools, and asset lists
Nora QA checks each item
Roxy packages captions, hashtags, timing, and CTAs
Emma prepares community responses and FAQ
PM approves or sends back
Publish runs after approval
```

Production ticket types:

| Ticket type | Owner | Required output |
|---|---|---|
| `article` | Bella or Article Writer | Headline, body, CTA, platform adaptation |
| `infographic` | Lila | 4:5 or platform-specific visual brief, copy blocks, visual prompt |
| `short_video` | Vera Reel, Bella, Lila | 15-40 sec script, scene plan, visual prompts, CTA |
| `long_video` | Vera Reel, Bella, Lila | 60-180 sec storyboard, scene timing, script, prompts, asset checklist |
| `community_post` | Emma | Group/Messenger prompt, moderation guide |
| `bubble_status` | Emma | Daily profile status, short prompt, reply-prep note |
| `distribution_pack` | Roxy | Captions, hashtags, post timing, platform CTAs |

### 4. `daily_bubble_status`

Used for daily profile presence such as a Bubble/status update.

Goal: keep the page feeling alive every day without creating a full production batch.

Inputs:

- Page PM daily vibe.
- Current campaign, sport, mood, offer, or post theme.
- Optional Roxy timing note.
- Optional Bella line if the Bubble needs sharper copy.
- Optional Lila visual cue if the Bubble uses a visual background.

Core flow:

```text
PM gives the daily vibe
Emma drafts the Bubble/status
Roxy checks timing or engagement angle only when needed
PM or Nayz approves
Bubble/status is posted
Emma handles replies or follow-up comments
```

Outputs:

- One short Bubble/status line.
- Optional alternate line.
- Optional reply prompt if viewers respond.
- Optional note for Sage if the Bubble reveals recurring audience interest.

Acceptance criteria:

- The Bubble feels human, light, and on-brand.
- It does not require the full production crew.
- It invites safe engagement without sounding desperate for comments.
- It is short enough to post directly.

### 5. `comment_response`

Used after content is published and followers comment on the page.

Goal: help Nayz or the PM answer real comments with brand-safe, warm, platform-appropriate replies.

Inputs:

- Screenshot of the comment or pasted comment text.
- Platform and page name.
- Link or context for the original post, if available.
- Existing caption or content brief, if available.
- Desired reply direction: friendly, funny, helpful, flirty-safe, clarify AI disclosure, de-escalate, or move to DM.

Core flow:

```text
Nayz captures the comment or screenshot
Emma reads the comment, platform, post context, and brand voice
Emma drafts 2-3 reply options
Nora checks only sensitive or risky replies
PM or Nayz approves the final reply
Sage Ledger records useful recurring questions or audience objections
```

Outputs:

- Short reply option.
- Warmer reply option.
- Brand-safe clarification option, when needed.
- Escalation note if the comment is hostile, privacy-sensitive, legal, medical, financial, or reputationally risky.
- Lesson note if the same question or objection repeats.

Acceptance criteria:

- The reply sounds like the page, not like generic customer service.
- The reply does not argue, overpromise, reveal private information, or intensify conflict.
- AI-generated or fictional-adult disclosures are preserved when the audience asks whether content is real.
- The reply is short enough to use directly on the target platform.

### 6. `performance_review`

Used after content is published.

Goal: convert engagement into the next creative decision.

Core flow:

```text
Iris Gauge pulls platform metrics
Sage Ledger links metrics to the original content ticket and assets
Roxy interprets platform packaging performance
Zoe proposes follow-up creative routes
PM decides scale, repair, or lesson-learned
Robin records the loop in the mission history
```

Metrics to track:

- Views.
- Watch time and retention.
- Shares.
- Saves.
- Comments.
- Likes.
- Follower/subscriber conversion.
- Clicks, if available.
- Revenue signal, if available.
- Qualitative comments and questions.

Decision buckets:

| Bucket | Meaning | Next action |
|---|---|---|
| Scale | Strong content with repeatable signal | Make sequel, remix, series, cross-platform version |
| Repair | Mixed result with clear fix | Change hook, thumbnail, caption, timing, length, or angle |
| Lesson learned | Weak result or wrong direction | Store as avoid/rethink note and do not repeat unchanged |

## Roles

### Existing Aurora Crew

| Role | v2 responsibility |
|---|---|
| Robin | Mission orchestrator, route owner, escalation point |
| Mia | Trend, platform, and signal scout |
| Zoe | Idea generator, hook and angle builder |
| Bella | Article, script, and copy writer |
| Lila | Visual director, prompt direction, visual package owner |
| Nora | QA gate, revision routing, quality risk owner |
| Roxy | Distribution, captions, hashtags, timing, platform packaging |
| Emma | Community, FAQ, daily Bubble/status, comment screenshot review, reply drafting, group/Messenger support |

### New Central Specialists

| Role | Responsibility |
|---|---|
| Mara Vale / Market & Monetization Analyst | Audience, competitor, niche, viral thesis, and revenue path analysis for new project discovery |
| Vera Reel / Video Producer | Storyboard-first video planning, scene timing, tool-aware prompt packages, and video asset requirements |
| Sage Ledger / Lesson Librarian | Drive/Notion/history lookup, duplicate prevention, asset provenance, and durable lesson records |
| Iris Gauge / Growth Analyst | Engagement analysis and scale/repair/lesson decision support |

### Role Modes, Not Separate People

These responsibilities should stay as modes under existing roles until the dashboard shows a real bottleneck:

| Mode | Lives under | Reason |
|---|---|---|
| Calendar planning | PM and Robin | PM chooses priorities; Robin turns the slate into tickets |
| Infographic production | Lila | It is part of visual direction, not a separate routing lane |
| Lesson library | Sage Ledger | Lesson records and duplicate prevention use the same memory system |
| Monetization strategy | Mara Vale | Audience validation and revenue path should be decided together |

## Interactive Routing

Aurora v2 must allow sideways and backward movement.

Examples:

- Nora sends a video back to Vera Reel if the scene flow is unclear.
- Lila asks Bella for tighter visual language if a script is too abstract.
- Roxy asks PM to choose the primary platform if captions conflict.
- Sage Ledger blocks an idea if Notion/Drive shows it was already produced.
- Iris Gauge sends a winner back to Zoe for sequels.
- Emma sends a risky comment reply to Nora before Nayz or the PM posts it.
- Emma asks Roxy for timing help if a daily Bubble/status should align with a publish window.
- PM asks Mara Vale for extra research before approving a new page.

## Anti-Duplication Rules

- Mia owns live signals; Mara Vale owns business viability.
- Zoe proposes routes; the PM selects priorities and final slate.
- Bella owns words; Vera Reel owns scene timing, video structure, and generation package.
- Emma owns post-publish reply drafts; Bella owns planned content copy before publishing.
- Emma can work from screenshots or pasted comments, but she should not invent missing comment context.
- Emma owns daily Bubble/status drafts; Roxy can advise timing but should not turn every Bubble into a growth tactic.
- Lila owns visual language; Vera Reel requests visual assets instead of replacing Lila.
- Nora checks quality and risk; the PM makes page-level business decisions.
- Iris Gauge diagnoses performance; Roxy turns that diagnosis into distribution changes.
- Sage Ledger owns duplicate checks before production and lesson links after performance review.

Every production ticket should carry:

- `decision_owner` for final approval.
- `priority` so not every item competes equally.
- `platform_primary` when multiple platforms are listed.
- `acceptance_criteria` before production begins.
- `evidence_links` or source signals for research traceability.
- `asset_requirements` and `asset_sources` for Drive/Veo3/reference control.
- `linked_lessons` so prior learning affects new work.

The dashboard should eventually show these as "requests" or "blocks", not as failures.

## Slay Hack Page Operation

Slay Hack is the first concrete Page Operation target for v2.

Canonical project slug:

```text
slay_hack
