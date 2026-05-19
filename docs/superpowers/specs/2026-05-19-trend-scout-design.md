# SP-1 TrendScout — Design Spec

**Status:** APPROVED  
**Date:** 2026-05-19  
**Depends on:** SP-0 Knowledge Store (merged via PR #143)

---

## Goal

Add a daily-running `TrendScoutPipeline` that scans for trending topics within each active page's established niche and stores each signal as a `ContentObject(kind="trend_signal")` in the SP-0 Knowledge Store. SP-2 Idea Planning reads these signals as input.

The existing niche-discovery Scout (`agents/scout.py`, `scout_pipeline.py`) is **not changed**.

---

## Architecture

```
scheduler (06:00 daily)
  └─ run_trend_scout_pipeline(page_slug, config, store, dry_run=False)
       ├─ load brand.yaml → scout_seed_topics
       ├─ TrendScoutAgent.scan(seed_topics) → list[TrendHit]
       │    ├─ Brave Search (per topic, parallel)
       │    ├─ Google Trends (per topic, serialised — rate limit)
       │    └─ Reddit subreddit search (per topic, parallel)
       ├─ for each hit → ContentObject(kind="trend_signal")
       │    ├─ store.check_duplicate() → STRONG dup → skip
       │    └─ store.add(obj, embed=True)
       ├─ write_trend_digest(hits, output_root)   → output/<page>/scout/<date>/trend_digest.md
       └─ return TrendScanJob
```

---

## Approved Decisions

### D1 — Separate pipeline, existing Scout untouched
`agents/scout.py` / `scout_pipeline.py` / `agents/analyst.py` / `agents/architect.py` remain unchanged. SP-1 adds a parallel track for active-page trend monitoring.

### D2 — Knowledge Store is the canonical output
Each trend signal is stored as `ContentObject(kind="trend_signal")` in the SP-0 vault + SQLite index. The daily digest markdown is a human-readable bonus, not the source of truth.

### D3 — Seed topics from brand.yaml
New optional field `scout_seed_topics: list[str]` added to each page's `brand.yaml`. If empty or absent, the pipeline skips that page silently. Default for `nayzfreedom_fleet`:

```yaml
scout_seed_topics:
  - beauty hacks
  - skincare routine
  - makeup tutorial
  - Gen Z fashion
  - wellness routine
```

### D4 — Sources: Brave + Google Trends + Reddit only
Meta Ads excluded (poor ROI for trend scan; niche-level competitor research is a different use case). All three sources are optional — missing API keys degrade gracefully (source returns empty, pipeline continues).

### D5 — Deterministic score formula (no LLM)
```
score = brave_hit_count × 0.4 + gtrends_score × 0.4 + log10(reddit_subscribers + 1) × 20 × 0.2
```
Clipped to [0, 100]. Direction derived from Google Trends 3-month delta: rising / stable / declining.

### D6 — ContentObject shape

| Field | Value |
|---|---|
| `kind` | `"trend_signal"` |
| `page` | page slug (e.g. `"nayzfreedom_fleet"`) |
| `title` | `"{topic} — {direction}"` |
| `body` | Markdown note (human-readable for vault) |
| `dedup_text` | `"{topic}|{page_slug}|{date}"` |
| `tags` | `[direction, source_list..., page_slug]` |
| `metadata` | `{topic, direction, score, sources: {brave, gtrends, reddit}}` |

### D7 — Dedup contract
- **STRONG dup** (same page + topic + same day, cosine ≥ 0.82): skip silently, increment `TrendScanJob.signals_skipped`
- **SOFT dup** (cross-page): store with `metadata.cross_page_dup = true`

### D8 — Store is injected, not constructed inside pipeline
`run_trend_scout_pipeline` accepts a `KnowledgeStore` parameter. Callers (scheduler, CLI, tests) construct and pass the store. No global state.

### D9 — Daily digest
Written to `output/<page_slug>/scout/<YYYYMMDD>/trend_digest.md`. Format: ranked table (score desc) + raw signal details. Written regardless of embed status.

### D10 — Dry-run signals (5 predefined)
```python
_DRY_HITS = [
    TrendHit(topic="beauty hacks",       direction="rising",   score=82.0, sources={"source": "dry-run"}),
    TrendHit(topic="skincare routine",   direction="stable",   score=71.5, sources={"source": "dry-run"}),
    TrendHit(topic="makeup tutorial",    direction="rising",   score=68.0, sources={"source": "dry-run"}),
    TrendHit(topic="Gen Z fashion",      direction="rising",   score=55.0, sources={"source": "dry-run"}),
    TrendHit(topic="wellness routine",   direction="stable",   score=48.0, sources={"source": "dry-run"}),
]
```

### D11 — Scheduler integration
Trend scan runs before the content pipeline in the daily 06:00 slot. Scheduler calls `run_trend_scout_pipeline` for each active project slug (those with `scout_seed_topics` in brand.yaml). Content pipeline for a page is independent — trend scan failure does not block it.

### D12 — Dashboard trigger
Add "Run Trend Scan Now" button to the `/scout/` route (or per-page island). Calls `run_trend_scout_pipeline` in a background thread and returns the `TrendScanJob` result.

---

## Data Models

### `TrendHit` (internal — not stored in DB directly)
```python
@dataclass
class TrendHit:
    topic: str
    direction: str        # "rising" | "stable" | "declining"
    score: float          # 0–100
    sources: dict         # raw data from each source
```

### `TrendScanJob` (Pydantic, persisted to output/)
```python
class TrendScanJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class TrendScanJob(BaseModel):
    job_id: str
    page_slug: str
    triggered_by: str       # "scheduler" | "dashboard" | "cli"
    created_at: datetime = Field(default_factory=datetime.now)
    status: TrendScanJobStatus = TrendScanJobStatus.PENDING
    signals_found: int = 0
    signals_stored: int = 0
    signals_skipped: int = 0    # dedup skips
    digest_path: Optional[str] = None
    error: Optional[str] = None
```

---

## File Map

### Create
- `models/trend_scan_job.py` — `TrendHit` dataclass + `TrendScanJob` Pydantic model
- `agents/trend_scout.py` — `TrendScoutAgent` (Brave + GTraends + Reddit, score formula)
- `trend_scout_pipeline.py` — `run_trend_scout_pipeline()` + `write_trend_digest()`
- `tests/test_trend_scout_pipeline.py` — TDD tests

### Modify
- `projects/slay_hack/brand.yaml` — add `scout_seed_topics` list
- `scheduler.py` — add per-page trend scan before content pipeline
- `routes/scout.py` — add "Run Trend Scan Now" button

---

## Testing Requirements

1. **Dry-run unit test:** `run_trend_scout_pipeline("nayzfreedom_fleet", config, store, dry_run=True)` stores exactly 5 ContentObjects with `kind="trend_signal"` in a temp Knowledge Store.
2. **Dedup idempotency:** Run pipeline twice with same dry-run signals; second run stores 0 new objects, `signals_skipped == 5`.
3. **Digest written:** After dry-run, `output/nayzfreedom_fleet/scout/<date>/trend_digest.md` exists and contains all 5 topics.
4. **Missing API keys:** All three source fetchers return empty lists when keys are absent — no exception raised.
5. **Score clipping:** Score formula never produces a value outside [0, 100].

---

## Not in SP-1 (deferred)

| Item | Target |
|---|---|
| Telegram digest notification | SP-5 Daily Ops |
| Dashboard card showing today's trend signals | Dashboard iteration after SP-2 |
| Meta Ads source | Evaluate in SP-6 Monetize |
| Per-topic embedding calibration | Handled by SP-0 drain cron |
