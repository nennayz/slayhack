# Auto-Performance Tracking — Design Spec

**Date:** 2026-05-17
**Status:** Approved
**Scope:** Aurora ship — closes the content feedback loop by automatically scheduling two performance snapshots (24h and 72h) after every live publish

---

## Problem

`python main.py --track JOB_ID` already fetches reach/likes/saves/shares from Meta and writes them to `job.performance`, which flows into Robin's context and the weekly Slack report. The gap: someone has to remember to run it manually. Performance data is therefore sparse and delayed, weakening Zoe's and Bella's prompt context.

---

## Solution Overview

After every successful live publish, enqueue two tracking snapshots at +24h and +72h. An hourly cron job (`track_scheduler.py`) processes overdue entries, retries up to 3× on failure, and alerts via Slack/Telegram on the final failure. No new dependencies. Fits the existing `scheduler.py` + cron pattern.

---

## Data Model

### `ContentJob.published_at` (new field)

Add `published_at: Optional[datetime] = None` to `ContentJob` in `models/content_job.py`.

Set in `PublishAgent.run_live()` after the publish loop:
- **Immediate post:** `job.published_at = datetime.now(timezone.utc)`
- **Scheduled post:** `job.published_at = datetime.fromtimestamp(scheduled_time, tz=timezone.utc)` (Roxy's recommended time)

`enqueue_track_snapshots` uses `job.published_at` as the base for all offset calculations. Falls back to `datetime.now(UTC)` if `published_at` is None (safety guard for edge cases).

---

### Queue file: `output/track_queue.json`

A flat JSON array. Each element is one snapshot job:

```json
[
  {
    "job_id": "20260517_143022_123456",
    "page_name": "Slayhack",
    "track_at": "2026-05-18T14:30:22Z",
    "attempt": 0
  },
  {
    "job_id": "20260517_143022_123456",
    "page_name": "Slayhack",
    "track_at": "2026-05-20T14:30:22Z",
    "attempt": 0
  }
]
```

- `track_at`: ISO 8601 UTC timestamp — when this snapshot should fire
- `attempt`: number of times this entry has been tried (0–2); removed after success or after 3 failures
- Each published job produces exactly two entries (one per offset)
- Writes are atomic: write to `track_queue.json.tmp`, then `os.replace()` to prevent corruption

---

## New Files

### `track_queue.py`

Single-purpose module for queue I/O. Public API:

```python
def enqueue_track_snapshots(job: ContentJob, offsets_hours: list[int] = [24, 72]) -> None:
    """Append snapshot entries to track_queue.json after a live publish."""

def read_queue() -> list[dict]:
    """Return current queue; returns [] if file missing or empty."""

def write_queue(entries: list[dict]) -> None:
    """Atomically write queue to disk."""
```

Queue file path: `output/track_queue.json` (relative to project root, same convention as `output/` jobs).

### `track_scheduler.py`

Hourly cron worker. Algorithm:

1. Read `track_queue.json` — if empty, exit 0
2. Find all entries where `track_at <= utcnow()`
3. For each overdue entry:
   - Run `python main.py --track JOB_ID` as subprocess (timeout: 60s)
   - **Success (exit 0):** remove entry from queue; log OK
   - **Failure (non-zero or timeout):** increment `attempt`
     - If `attempt < 3`: leave entry in queue for next hour's retry
     - If `attempt >= 3`: send alert via `notifier.send_healthcheck_alert()`; remove entry
4. Write updated queue atomically
5. Log all activity to stdout (captured by cron to `/var/log/nayzfreedom.log`)

Subprocess timeout is 60s — tracking is a single Meta API call, not a full pipeline run.

### `deploy/nayzfreedom-track-scheduler.service`

```ini
[Unit]
Description=NayzFreedom Track Scheduler
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/nayzfreedom-fleet
ExecStart=/path/to/.venv/bin/python track_scheduler.py
StandardOutput=append:/var/log/nayzfreedom.log
StandardError=append:/var/log/nayzfreedom.log
```

### `deploy/nayzfreedom-track-scheduler.timer`

```ini
[Unit]
Description=Run NayzFreedom Track Scheduler every hour

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

`Persistent=true` ensures a missed hourly run fires on next boot — important for VPS reboots.

---

## Modified Files

### `agents/publish.py`

In `run_live()`, after the publish loop completes and at least one platform result is `"published"` or `"scheduled"`:

```python
from track_queue import enqueue_track_snapshots

# After: job.publish_result = result
_published_statuses = {"published", "scheduled", "pending_queue"}
if not job.dry_run and any(
    isinstance(v, dict) and v.get("status") in _published_statuses
    for v in (result or {}).values()
):
    enqueue_track_snapshots(job)
```

Dry-run publish skips enqueue — no real post means no tracking.

Partial failures (one platform published, another failed) still enqueue — the successful platforms produced real posts that should be tracked. The check passes as long as at least one platform result has a published/scheduled status.

### `models/content_job.py`

Add one field to `ContentJob`:

```python
published_at: Optional[datetime] = None
```

### `agents/publish.py`

After the publish loop, before calling `enqueue_track_snapshots`:

```python
from datetime import datetime, timezone

# Set published_at: use scheduled time for scheduled posts, now() for immediate
if scheduled_time:
    job.published_at = datetime.fromtimestamp(scheduled_time, tz=timezone.utc)
else:
    job.published_at = datetime.now(timezone.utc)
```

### `deploy/setup.sh`

Add:
```bash
# Track scheduler (hourly)
systemctl enable nayzfreedom-track-scheduler.timer
systemctl start nayzfreedom-track-scheduler.timer
```

And the fallback cron entry (for non-systemd setups):
```
0 * * * * /path/to/.venv/bin/python /path/to/track_scheduler.py >> /var/log/nayzfreedom.log 2>&1
```

### Dashboard job detail (`/jobs/{job_id}`)

Enrich the job detail context with pending queue entries for that job:

- If queue has entries for this job: show **"Next snapshot: {track_at} UTC"**
- Derive snapshot progress from `job.performance` length:
  - 0 snapshots: "No performance data yet"
  - 1 snapshot: "24h tracked ✓ — 72h pending"
  - 2 snapshots: "24h ✓ — 72h ✓"

No new routes. The existing `/jobs/{job_id}` handler reads the queue and passes snapshot state into the template context.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| `track_queue.json` missing | `read_queue()` returns `[]`, scheduler exits 0 |
| Subprocess timeout (60s) | Counted as failure; attempt incremented |
| `main.py --track` exits non-zero | Counted as failure; attempt incremented |
| 3rd consecutive failure | `notifier.send_healthcheck_alert()` fires; entry removed |
| Queue file corrupted (bad JSON) | Log error, back up corrupt file to `track_queue.json.corrupt`, start fresh empty queue |
| Two `track_scheduler.py` instances overlap | Atomic write prevents corruption; worst case: one entry processed twice (harmless — `tracker.py` appends, not overwrites) |

---

## Testing

### `tests/test_track_queue.py`
- `enqueue_track_snapshots` writes exactly 2 entries with correct offsets from `job.published_at`
- Immediate post: `published_at` set to now; scheduled post: `published_at` set to scheduled timestamp
- Dry-run job skips enqueue
- `write_queue` is atomic (simulate interrupted write, assert no corruption)
- `read_queue` returns `[]` when file is missing

### `tests/test_track_scheduler.py`
- Future entries are skipped (not yet due)
- Overdue entries fire `--track` subprocess
- Successful track removes entry from queue
- Failed track increments attempt; entry stays in queue
- 3rd failure sends alert and removes entry
- Corrupted queue file is backed up and reset

---

## Success Criteria

1. Every live published job has performance data in `job.performance` within 25h of publish — no manual intervention
2. Robin's context window for new jobs includes reach/likes data from the last 5 jobs (already wired in `job_store.load_recent_performance`)
3. Failed track jobs surface in Slack/Telegram within 3 hours of the third failure
4. `track_queue.json` is always valid JSON after any operation (atomic writes)
5. All new code has test coverage; no existing tests broken

---

## Out of Scope

- Tracking TikTok/YouTube performance (those platforms need separate tracker implementations — separate feature)
- Retroactively tracking already-published jobs with no queue entries (manual `--track` covers this)
- Per-platform snapshot timing (all platforms tracked together in one `--track` call, same as today)
