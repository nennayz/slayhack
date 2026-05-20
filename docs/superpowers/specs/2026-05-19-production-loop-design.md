# SP-3 Production Loop — Design Spec

**Status:** APPROVED
**Date:** 2026-05-19
**Depends on:** SP-0 Knowledge Store (PR #143), SP-1 TrendScout (PR #144), SP-2 IdeaPlanner (PR #145)

---

## Goal

Connect the approved-idea pipeline (SP-2 output) to the existing content production pipeline (Robin → Bella → Lila → Nora → Roxy → Emma → Publish). When the Captain approves an idea in the dashboard, the next daily scheduler run picks it up, runs it through production unattended, and deposits the output as a Manual Post Kit.

`agents/mia.py` and `agents/zoe.py` are fully unwired from the orchestrator here. Their deprecation comments (added in SP-2) become real: Robin no longer has `run_mia` or `run_zoe` tools.

---

## Architecture

```
scheduler (daily, 06:00)
  ├─ _run_daily_scout()
  ├─ _run_daily_trend_scan()        ← SP-1
  ├─ _run_daily_idea_planner()      ← SP-2
  └─ _run_daily_production_loop()   ← SP-3 (NEW)
       └─ run_production_loop(page_slug, config, store, dry_run, output_root)
            ├─ store.recent(kind="idea", page=slug, status="approved",
            │               limit=1, order="asc")   ← oldest approved idea first
            ├─ store.set_status(uid, "in_production")
            ├─ idea_to_content_job(idea, pm) → ContentJob
            ├─ Orchestrator(config).run(content_job, unattended=True)
            ├─ on success: log + return
            └─ on failure: store.set_status(uid, "approved")  ← reset for retry tomorrow
```

One approved idea is processed per page per scheduler run (`limit=1`). If multiple ideas are approved, each runs on a subsequent day — one piece of content per day is the correct cadence.

---

## Approved Decisions

### D1 — Robin stays; Mia/Zoe unwired
The orchestrator remains LLM-driven (Robin uses OpenAI tool calls). Only `run_mia` and `run_zoe` are removed from the tool list and `self.agents`. Robin starts directly from the brief with `run_bella`. The `idea_selection` checkpoint handler in `_dispatch` is kept (protects in-flight resume jobs started before SP-3).

### D2 — Scheduler-only trigger
No dashboard "Run Now" button in SP-3. The daily scheduler batch is the only trigger. One job per page per day prevents the scheduler from being overwhelmed (each job takes 5–15 minutes).

### D3 — Fully unattended
All checkpoints (content_review, qa_review, final_approval) auto-approve via `unattended=True`. Output lands as a Manual Post Kit in `output/<page>/<job_id>/`. Captain reviews and posts manually.

### D4 — `"in_production"` on pickup; `"published"` for SP-4
SP-3 transitions idea status `"approved"` → `"in_production"` when the job starts. The `"published"` transition belongs to SP-4 Performance Tracking, which reads the confirmed Meta API post ID.

### D5 — Oldest-approved-first ordering
`store.recent()` gains an `order: str = "desc"` parameter. SP-3 calls it with `order="asc"` to process the oldest approved idea first (FIFO queue). Default remains `"desc"` so all existing callers are unaffected.

### D6 — Failure resets status to `"approved"`
If `Orchestrator.run()` raises, SP-3 calls `store.set_status(uid, "approved")` to reset the idea so tomorrow's scheduler can retry it. `jobs_failed` is incremented in the result.

### D7 — Brief construction with angle
```python
# ks_to_content_job.py
brief = f"{idea.title}: {hook} [{angle}]"
# e.g. "The 60-Second Glow Up Method: this hack changed my whole face [Tutorial]"
```
`hook` comes from `idea.summary` (set in SP-3 Task 1 patch to `idea_planner_pipeline.py`).
`angle` comes from `idea.tags[1]` (SP-2 stores `[content_type, angle, page_slug]`).

Fallback when `idea.summary` is empty (ideas approved before SP-3 patch):
```python
for line in idea.body.splitlines():
    if line.startswith("**Hook:**"):
        hook = line.replace("**Hook:**", "").strip()
        break
```

### D8 — `ContentJob.idea_uid` traceability field
A new `idea_uid: str | None = None` optional field is added to `ContentJob`. Set by `idea_to_content_job()`. Enables SP-4+ to trace a job back to the originating idea. Non-breaking additive change — existing jobs have `idea_uid=None`.

### D9 — `_draft_to_content_object` patch in `idea_planner_pipeline.py`
Task 1 of SP-3 adds `summary=draft.hook` to the `ContentObject(...)` call in `idea_planner_pipeline.py`. This is required so `ks_to_content_job.py` can build a rich brief from `idea.summary` without parsing markdown.

---

## Data Models

### `ProductionLoopResult` (ephemeral, not persisted)
```python
@dataclass
class ProductionLoopResult:
    page_slug: str
    ideas_found: int = 0      # approved ideas available
    jobs_started: int = 0     # jobs attempted
    jobs_completed: int = 0   # orchestrator returned without exception
    jobs_failed: int = 0      # orchestrator raised; idea reset to "approved"
```

### `ContentJob` additions
```python
class ContentJob(BaseModel):
    ...
    idea_uid: str | None = None   # NEW — uid of the KS idea that spawned this job
```

---

## File Map

### Create
- `ks_to_content_job.py` — `idea_to_content_job(idea, pm, platforms, dry_run) -> ContentJob`
- `production_loop.py` — `run_production_loop(page_slug, config, store, dry_run, output_root) -> ProductionLoopResult`
- `tests/test_production_loop.py` — pipeline + mapping tests
- `tests/test_ks_to_content_job.py` — unit tests for brief/content_type mapping

### Modify
- `idea_planner_pipeline.py` — add `summary=draft.hook` in `_draft_to_content_object()`
- `models/content_job.py` — add `idea_uid: str | None = None`
- `tools/agent_tools.py` — remove `run_mia` and `run_zoe` entries
- `orchestrator.py` — remove `MiaAgent`/`ZoeAgent` from `self.agents`; update `_ROBIN_SYSTEM`; remove Mia/Zoe imports
- `knowledge/store.py` — add `order: str = "desc"` parameter to `recent()`
- `scheduler.py` — add `_run_daily_production_loop()` + call in `run_scheduler()`

---

## Orchestrator Changes (detail)

### `tools/agent_tools.py`
Remove the `run_mia` and `run_zoe` dict entries from `get_tool_definitions()`. Resulting tool list:
`run_bella`, `run_lila`, `run_nora`, `run_roxy`, `run_emma`, `run_publish`, `request_checkpoint`.

### `orchestrator.py`
**Imports:** Remove `from agents.mia import MiaAgent` and `from agents.zoe import ZoeAgent`.

**`__init__`:** Remove `"mia": MiaAgent(config)` and `"zoe": ZoeAgent(config)` from `self.agents`.

**`_ROBIN_SYSTEM`:** Replace the header and steps 1–3 with:

```
The brief and content type have already been selected by the Captain from the
Idea Bank — do NOT call run_mia or run_zoe. Start directly with run_bella.

## Team workflow (follow this order):
1. run_bella — write content based on the brief and content_type
2. After Bella completes, check job.content_type:
   - video, image, or infographic → run_lila
   - article → skip run_lila, go directly to step 3
3. request_checkpoint (stage: "content_review")
4. run_nora — QA review. If QA fails and retry < max_retries, re-run relevant agent.
5. request_checkpoint (stage: "qa_review")
6. run_roxy and run_emma — call BOTH in the same response (parallel)
7. request_checkpoint (stage: "final_approval")
8. run_publish — publish to Meta. Pass schedule=true for Roxy's recommended time.
```

`_dispatch` `idea_selection` handler: **kept unchanged** (safe guard for resume jobs).

---

## `ks_to_content_job.py` (full spec)

```python
def idea_to_content_job(
    idea: ContentObject,
    pm: PMProfile,
    platforms: list[str] | None = None,
    dry_run: bool = False,
) -> ContentJob:
    hook = _extract_hook(idea)
    angle = idea.tags[1] if len(idea.tags) > 1 else ""
    brief = f"{idea.title}: {hook}" + (f" [{angle}]" if angle else "")

    content_type = _resolve_content_type(idea.tags)

    job = ContentJob(
        project=idea.page,
        pm=pm,
        brief=brief,
        platforms=platforms or list(pm.brand.platforms),
        dry_run=dry_run,
        idea_uid=idea.uid,
    )
    if content_type is not None:
        job.content_type = content_type
    return job


def _extract_hook(idea: ContentObject) -> str:
    if idea.summary:
        return idea.summary
    for line in idea.body.splitlines():
        stripped = line.strip()
        if stripped.startswith("**Hook:**"):
            return stripped.replace("**Hook:**", "").strip()
    return ""


def _resolve_content_type(tags: list[str]) -> ContentType | None:
    from models.content_job import ContentType
    if not tags:
        return None
    try:
        return ContentType(tags[0])
    except ValueError:
        return None
```

---

## `production_loop.py` (full spec)

```python
def run_production_loop(
    page_slug: str,
    config: Config,
    store: KnowledgeStore,
    dry_run: bool = False,
    output_root: Path | None = None,
) -> ProductionLoopResult:
    result = ProductionLoopResult(page_slug=page_slug)

    approved = store.recent(kind="idea", page=page_slug, status="approved", limit=1, order="asc")
    result.ideas_found = len(approved)
    if not approved:
        logger.info("Production loop: no approved ideas for %s", page_slug)
        return result

    idea = approved[0]
    logger.info("Production loop: starting job for idea=%s page=%s", idea.uid, page_slug)

    try:
        pm = load_project(page_slug)
    except Exception as exc:
        logger.error("Production loop: could not load project %s: %s", page_slug, exc)
        return result

    job = idea_to_content_job(idea, pm, dry_run=dry_run)
    store.set_status(idea.uid, "in_production")
    result.jobs_started += 1

    try:
        orchestrator = Orchestrator(config)
        orchestrator.run(job, unattended=True)
        result.jobs_completed += 1
        logger.info("Production loop: completed job=%s idea=%s", job.id, idea.uid)
    except Exception as exc:
        logger.error("Production loop: job failed idea=%s: %s", idea.uid, exc)
        store.set_status(idea.uid, "approved")   # reset for tomorrow
        result.jobs_failed += 1

    return result
```

---

## `KnowledgeStore.recent()` — `order` parameter

```python
def recent(
    self,
    page: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    limit: int = 20,
    order: str = "desc",          # NEW — "desc" (default, newest first) | "asc" (oldest first)
) -> list[ContentObject]:
    ...
    direction = "ASC" if order.lower() == "asc" else "DESC"
    sql += f" ORDER BY created_at {direction}, uid {direction} LIMIT {int(limit)}"
```

---

## Testing Requirements

### `tests/test_production_loop.py`
1. **`test_picks_up_approved_idea`** — 1 approved idea in store, Orchestrator mocked → idea status `"in_production"`, `jobs_started=1`, `jobs_completed=1`
2. **`test_skips_new_ideas`** — store has only `status="new"` ideas → `ideas_found=0`, orchestrator never called
3. **`test_skips_rejected_ideas`** — store has only `status="rejected"` ideas → `ideas_found=0`
4. **`test_empty_store_returns_immediately`** — empty KS → all result fields zero
5. **`test_orchestrator_failure_resets_status`** — orchestrator raises → idea reset to `"approved"`, `jobs_failed=1`
6. **`test_limit_one_per_run`** — 3 approved ideas → only 1 processed, 2 remain `"approved"`
7. **`test_dry_run_sets_in_production`** — `dry_run=True` → ContentJob has `dry_run=True`, status still updated

### `tests/test_ks_to_content_job.py`
1. **`test_brief_title_hook_angle`** — `summary` set → brief = `"title: hook [angle]"`
2. **`test_brief_fallback_parse_body`** — `summary=""` → hook parsed from `**Hook:**` body line
3. **`test_brief_title_only_fallback`** — `summary=""` and no `**Hook:**` line → brief = title only
4. **`test_content_type_from_tags`** — `tags=["video", "Tutorial", "nayzfreedom_fleet"]` → `content_type=ContentType.VIDEO`
5. **`test_content_type_invalid_tag_returns_none`** — `tags=["not_a_type"]` → `content_type=None`
6. **`test_idea_uid_set`** — `job.idea_uid == idea.uid`
7. **`test_platforms_default_from_brand`** — no explicit platforms → uses `pm.brand.platforms`

### Existing test suites — regression checks
- `pytest tests/test_orchestrator.py -v` — must pass after Mia/Zoe removal
- `pytest tests/test_scheduler.py -v` — must pass after scheduler addition
- `pytest tests/test_idea_planner_pipeline.py -v` — must pass after `summary` patch
- Full suite: 680+ expected after SP-3

---

## Not in SP-3 (deferred)

| Item | Target |
|---|---|
| `"published"` status transition | SP-4 Performance Tracking |
| Dashboard "Run Now" for production | Dashboard iteration |
| Telegram checkpoint callbacks | SP-5 Daily Ops |
| Production run history / audit log | Dashboard iteration |
| Retry with backoff on orchestrator failure | SP-5 or later |
| Orchestrator → deterministic stage machine | Future SP (large refactor) |
