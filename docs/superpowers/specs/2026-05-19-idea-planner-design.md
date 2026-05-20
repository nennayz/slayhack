# SP-2 IdeaPlanner — Design Spec

**Status:** APPROVED  
**Date:** 2026-05-19  
**Depends on:** SP-0 Knowledge Store (PR #143), SP-1 TrendScout (PR #144)

---

## Goal

Replace the per-job Mia → Zoe trend-research-and-ideation chain with a daily-running `IdeaPlannerPipeline` that produces 7 idea `ContentObject`s per active page from Knowledge Store inputs (trend signals + brand profile + recent ideas for diversity). Captain reviews ideas in the dashboard (and via Telegram digest in SP-5). Approved ideas have `status="approved"` and become input to SP-3 Production Loop.

`agents/mia.py` and `agents/zoe.py` are deprecated (kept as files with deprecation comments; orchestrator unwiring happens in SP-3).

---

## Architecture

```
scheduler (07:00 daily, after TrendScout 06:00)
  └─ run_idea_planner_pipeline(page_slug, config, store)
       ├─ recent trend signals     ← store.recent(kind="trend_signal", page=slug, limit=10)
       ├─ recent ideas (diversity) ← store.recent(kind="idea",         page=slug, limit=30)
       ├─ brand profile            ← load_project(slug)
       ├─ IdeaPlannerAgent.generate(signals, recent_ideas, brand) → list[IdeaDraft]
       │    └─ LLM (OPENAI_AGENT_MODEL) returns 7 idea JSON objects
       ├─ for each draft → ContentObject(kind="idea", status="new")
       │    ├─ store.check_duplicate(...) → STRONG → skip
       │    └─ store.add(obj, embed=True)
       ├─ write digest → output/<page>/ideas/<date>/idea_digest.md
       └─ notifier.send_telegram_idea_digest(page_slug, idea_uids)   # stub in SP-2

Captain interaction:
  Dashboard /ideas → list, filter by status, approve/reject
  Telegram callbacks (SP-5) → hit dashboard endpoints
```

---

## Approved Decisions

### D1 — Retire Mia, replace Zoe with IdeaPlanner
`agents/mia.py` and `agents/zoe.py` are deprecated (file-level deprecation comment, no behavioural change). The orchestrator change to route around them lives in SP-3 Production Loop. SP-2 only adds the new IdeaPlanner pipeline; it does not modify `orchestrator.py`.

### D2 — Daily 7-idea batch
IdeaPlanner runs at 07:00 daily per active page, generates 7 ideas (aligned to the 7-slot weekly_calendar.yaml pattern). Ideas are stored as `ContentObject(kind="idea", status="new")` in Knowledge Store.

### D3 — Approval surface: dashboard + Telegram digest
- Dashboard `/ideas` route: list with status filter chips, per-idea approve/reject buttons
- Telegram digest: send-only in SP-2 (`notifier.send_telegram_idea_digest`). Bot polling for callback responses is SP-5.

### D4 — LLM-driven generation with KS context
Uses `BaseAgent._call_claude()` (which calls OpenAI). Single prompt receives brand profile + 10 trend signals + 30 recent idea titles. Output JSON parsed via existing `BaseAgent._parse_json()` pattern.

### D5 — Approved ideas become ContentJob input (SP-3)
On approval, status flips from `"new"` to `"approved"`. SP-3 Production Loop polls KS for `kind="idea", status="approved"` and constructs ContentJob from idea fields:
- `ContentJob.brief = f"{idea.title}: {idea.hook}"` (or richer mapping defined in SP-3)
- `ContentJob.content_type = idea.tags[0]` (content_type tag)
- Idea UID stored as parent_uid in all downstream artifacts

SP-2 does not implement the SP-3 side. SP-2 ends at status transition.

### D6 — Idea ContentObject shape

| Field | Value |
|---|---|
| `kind` | `"idea"` |
| `page` | page slug |
| `title` | the idea title (≤ 60 chars from LLM) |
| `body` | Markdown vault note (hook, angle, content_type, source signals summary) |
| `dedup_text` | `f"{title}|{hook}|{page_slug}|{date}"` |
| `tags` | `[content_type, angle, page_slug]` |
| `parent_uids` | list of source `trend_signal` UIDs (must contain ≥ 1) |
| `status` | `"new"` → `"approved"` / `"rejected"` → `"in_production"` → `"published"` |

### D7 — Status lifecycle
- `"new"` — idea generated, awaiting Captain decision
- `"approved"` — Captain approved (SP-3 will pick it up)
- `"rejected"` — Captain rejected (kept in vault for learning, not deleted)
- `"in_production"` — SP-3 transitions (out of scope for SP-2)
- `"published"` — terminal success (SP-3+)

Reject is non-destructive. We keep rejected ideas for future LLM tuning.

### D8 — Dedup contract
- STRONG (same `title|hook|page|date`, cosine ≥ 0.82) → skip, log "dup idea"
- SOFT (cross-date, same page, cosine ≥ 0.68) → store, append `"soft-dup"` to tags

### D9 — Empty KS resilience
If `store.recent(kind="trend_signal")` returns empty (first-ever run, or all signals expired), IdeaPlanner falls back to brand-context-only generation with a logged warning. Still generates 7 ideas.

### D10 — LLM JSON parsing resilience
If LLM returns invalid JSON or fewer than 7 ideas, log error, store whatever was parsed (even if 0), do not crash the pipeline.

### D11 — Dry-run set (7 predefined IdeaDrafts)
For SlayHack:
```python
_DRY_IDEAS = [
    IdeaDraft(title="The Invisible Lip Liner Hack",        hook="POV: your lips last all day",      angle="Tutorial", content_type="video"),
    IdeaDraft(title="Quiet Luxury Morning Routine",        hook="This is how rich girls start their day", angle="Lifestyle", content_type="image"),
    IdeaDraft(title="5 Dupes That Beat the Original",      hook="Stop wasting money on pricey formulas", angle="Review", content_type="article"),
    IdeaDraft(title="The 3-Step Kiss-Proof Secret",        hook="omg why didn't anyone tell me sooner", angle="Tutorial", content_type="video"),
    IdeaDraft(title="Get Ready With Me: Date Night",       hook="come get ready with me for date night", angle="GRWM", content_type="infographic"),
    IdeaDraft(title="The 60-Second Glow Up Method",        hook="this hack changed my whole face",  angle="Tutorial", content_type="video"),
    IdeaDraft(title="Why Your Skincare Order Matters",     hook="you've been doing this wrong forever", angle="Educational", content_type="article"),
]
```

### D12 — Scheduler integration
After `_run_daily_trend_scan` in `run_scheduler`, call `_run_daily_idea_planner(active_slugs, dry_run, root)`. Idea planning runs after trend scanning each day. Failure in idea planning does not block content pipeline (which may still run on previously approved ideas).

### D13 — Dashboard routes (`routes/ideas.py`)
- `GET /ideas?page=<slug>&status=<status>` — paginated idea list with status filter
- `POST /ideas/{uid}/approve` — flip to "approved", return JSON
- `POST /ideas/{uid}/reject` — flip to "rejected", return JSON
- `POST /ideas/generate/{page_slug}` — manual trigger, background thread, returns 202

All POST endpoints require auth via `Depends(verify_auth)`.

### D14 — Status mutation API
Add `KnowledgeStore.set_status(uid, new_status)` method to SP-0 if not already present. Updates SQLite index `notes.status` column AND rewrites the vault note frontmatter `status:` field. Atomic — either both succeed or both roll back.

If this method doesn't exist in SP-0, it is added as part of SP-2 Task 4 (idea routes need it).

---

## Data Models

### `IdeaDraft` (internal, ephemeral)
```python
@dataclass
class IdeaDraft:
    title: str
    hook: str
    angle: str
    content_type: str           # one of brand.allowed_content_types
    source_signal_uids: list[str] = field(default_factory=list)
```

### `IdeaPlanJob` (Pydantic, persisted)
```python
class IdeaPlanJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class IdeaPlanJob(BaseModel):
    job_id: str
    page_slug: str
    triggered_by: str          # "scheduler" | "dashboard" | "cli"
    created_at: datetime = Field(default_factory=datetime.now)
    status: IdeaPlanJobStatus = IdeaPlanJobStatus.PENDING
    ideas_generated: int = 0
    ideas_stored: int = 0
    ideas_skipped: int = 0     # dedup skips
    signals_used: int = 0
    digest_path: Optional[str] = None
    error: Optional[str] = None
```

---

## File Map

### Create
- `models/idea_plan_job.py` — `IdeaDraft` dataclass + `IdeaPlanJob` Pydantic model
- `agents/idea_planner.py` — `IdeaPlannerAgent` with LLM contract + dry-run drafts
- `idea_planner_pipeline.py` — `run_idea_planner_pipeline()` + `write_idea_digest()`
- `routes/ideas.py` — dashboard idea bank endpoints
- `templates/ideas/list.html` — idea list view (simple, can iterate)
- `tests/test_idea_planner_pipeline.py` — TDD tests

### Modify
- `scheduler.py` — add `_run_daily_idea_planner()` call after trend scan
- `notifier.py` — add `send_telegram_idea_digest(page_slug, idea_uids)` (stub OK in SP-2)
- `agents/mia.py` — file-top deprecation comment (no behaviour change)
- `agents/zoe.py` — file-top deprecation comment (no behaviour change)
- `dashboard.py` / `routes/deps.py` — register `routes.ideas` router
- `knowledge/store.py` — add `set_status(uid, new_status)` if absent (vault + index atomic update)

---

## Testing Requirements

1. **Dry-run unit test:** `run_idea_planner_pipeline("nayzfreedom_fleet", cfg, store, dry_run=True)` stores 7 ContentObjects with `kind="idea"`, `status="new"`. `ideas_stored == 7`.
2. **Dedup idempotency:** Second run with same dry-run drafts → `ideas_stored == 0, ideas_skipped == 7`.
3. **Status transition test:** `POST /ideas/<uid>/approve` flips status to `"approved"` in both vault and index.
4. **Empty KS fallback:** Run with zero trend signals in KS → still generates 7 ideas (warning logged).
5. **LLM JSON resilience:** Inject malformed LLM response → pipeline returns `IdeaPlanJob` with `ideas_stored < 7` but no exception.
6. **Digest written:** `output/nayzfreedom_fleet/ideas/<date>/idea_digest.md` exists with all 7 titles.
7. **Dashboard list filter:** `GET /ideas?status=new` returns only `"new"` ideas; `?status=approved` returns only `"approved"`.

---

## Not in SP-2 (deferred)

| Item | Target |
|---|---|
| Telegram bot polling for inline button callbacks | SP-5 Daily Ops |
| `ContentObject.metadata` dict field (richer idea structured data: CTA, target keywords, est. reach) | SP-0.1 patch |
| Orchestrator rewiring (Mia/Zoe removed from `orchestrator.py`) | SP-3 Production Loop |
| Constructing `ContentJob` from approved idea | SP-3 Production Loop |
| Performance feedback loop (reach data feeds back into generation prompt) | SP-6 Monetize / later |
| Bulk approve/reject UI | Dashboard iteration |
| Rich `templates/ideas/list.html` (Tailwind, cards, etc.) | Dashboard iteration; SP-2 ships a functional minimum template |
