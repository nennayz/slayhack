# Auto-Performance Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically schedule two performance snapshots (24h and 72h) after every live publish, processed by an hourly cron worker, with retry and Slack/Telegram alerting on failure.

**Architecture:** A new `track_queue.py` module manages a persistent `output/track_queue.json` queue. `PublishAgent` writes to it after every live publish. A new `track_scheduler.py` hourly cron worker reads the queue, fires `python main.py --track JOB_ID` for overdue entries, retries up to 3× on failure, and alerts via the existing `notifier.py` on final failure.

**Tech Stack:** Python stdlib only (json, subprocess, os.replace for atomic writes). Fits existing `scheduler.py` + systemd timer + cron pattern. No new dependencies.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `models/content_job.py` | Add `published_at: Optional[datetime]` field |
| Modify | `tracker.py` | Use `job.published_at` in `_job_publish_time`; fix new ID format |
| Create | `track_queue.py` | Queue read/write/enqueue helpers |
| Modify | `agents/publish.py` | Set `job.published_at`; call `enqueue_track_snapshots` |
| Create | `track_scheduler.py` | Hourly cron worker |
| Create | `deploy/nayzfreedom-track-scheduler.service` | Systemd service unit |
| Create | `deploy/nayzfreedom-track-scheduler.timer` | Systemd hourly timer |
| Modify | `deploy/setup.sh` | Register new timer |
| Modify | `dashboard.py` | Show snapshot status on `/jobs/{job_id}` detail |
| Create | `tests/test_track_queue.py` | Queue helper tests |
| Create | `tests/test_track_scheduler.py` | Scheduler worker tests |

---

## Task 1: Add `published_at` to `ContentJob` and fix `_job_publish_time`

**Files:**
- Modify: `models/content_job.py`
- Modify: `tracker.py`
- Modify: `tests/test_models.py`

**Context:** `ContentJob.id` was recently changed from `%Y%m%d_%H%M%S` (15 chars) to `%Y%m%d_%H%M%S_%f` (22 chars). `tracker.py:_job_publish_time` still parses with the old format and will fail. Adding `published_at` fixes this and gives accurate tracking offsets for scheduled posts.

- [ ] **Step 1: Write the failing test for `published_at` field**

Add to `tests/test_models.py`:

```python
def test_content_job_published_at_defaults_none():
    job = ContentJob(project="test", pm=make_pm(), brief="b", platforms=["instagram"])
    assert job.published_at is None

def test_content_job_published_at_serializes():
    from datetime import datetime, timezone
    job = ContentJob(project="test", pm=make_pm(), brief="b", platforms=["instagram"])
    job.published_at = datetime(2026, 5, 17, 14, 0, 0, tzinfo=timezone.utc)
    data = job.model_dump_json()
    assert "published_at" in data
    job2 = ContentJob.model_validate_json(data)
    assert job2.published_at == job.published_at
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/nennayz/Documents/NayzFreedom/code/nayzfreedom-fleet
source .venv/bin/activate
pytest tests/test_models.py::test_content_job_published_at_defaults_none -v
```
Expected: `FAILED` — `ContentJob` has no `published_at` attribute.

- [ ] **Step 3: Add `published_at` to `ContentJob`**

In `models/content_job.py`, add after the `performance` field:

```python
class ContentJob(BaseModel):
    id: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    project: str
    pm: PMProfile
    brief: str
    platforms: list[str]
    stage: str = "init"
    status: JobStatus = JobStatus.PENDING
    dry_run: bool = False
    trend_data: Optional[dict] = None
    ideas: Optional[list[Idea]] = None
    selected_idea: Optional[Idea] = None
    content_type: Optional[ContentType] = None
    bella_output: Optional[BellaOutput] = None
    visual_prompt: Optional[str] = None
    image_path: Optional[str] = None
    video_path: Optional[str] = None
    production_ticket: Optional[dict] = None
    video_package: Optional[dict] = None
    generation_request: Optional[dict] = None
    generation_result: Optional[dict] = None
    qa_result: Optional[QAResult] = None
    nora_retry_count: int = 0
    growth_strategy: Optional[GrowthStrategy] = None
    community_faq_path: Optional[str] = None
    publish_package: Optional[dict] = None
    publish_execution: Optional[dict] = None
    publish_result: Optional[dict] = None
    checkpoint_log: list[CheckpointDecision] = Field(default_factory=list)
    performance: list[PostPerformance] = Field(default_factory=list)
    published_at: Optional[datetime] = None
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/test_models.py::test_content_job_published_at_defaults_none tests/test_models.py::test_content_job_published_at_serializes -v
```
Expected: both `PASSED`.

- [ ] **Step 5: Fix `_job_publish_time` in `tracker.py`**

Replace the function in `tracker.py`:

```python
def _job_publish_time(job: ContentJob) -> int:
    if job.published_at is not None:
        return int(job.published_at.timestamp())
    try:
        # Fallback: parse from job ID — handle both 15-char and 22-char formats
        dt = datetime.strptime(job.id[:15], "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, AttributeError):
        return int(datetime.now(timezone.utc).timestamp())
```

- [ ] **Step 6: Run full model + tracker tests**

```bash
pytest tests/test_models.py tests/test_tracker.py -v
```
Expected: all `PASSED`.

- [ ] **Step 7: Commit**

```bash
git add models/content_job.py tracker.py tests/test_models.py
git commit -m "feat: add published_at to ContentJob; fix _job_publish_time for new ID format"
```

---

## Task 2: Create `track_queue.py`

**Files:**
- Create: `track_queue.py`
- Create: `tests/test_track_queue.py`

**Context:** `track_queue.py` sits alongside `job_store.py` and `tracker.py`. The queue file lives at `output/track_queue.json` (relative to working directory — same convention as all other `output/` files). Writes are atomic via `os.replace()`.

- [ ] **Step 1: Create `tests/test_track_queue.py` with all failing tests**

```python
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import sys
import pytest

# Google stub (matches conftest.py pattern)
_google = MagicMock()
sys.modules.setdefault("google", _google)
sys.modules.setdefault("google.genai", _google.genai)


def _make_pm():
    from models.content_job import PMProfile, BrandProfile, VisualIdentity
    return PMProfile(
        name="Test",
        page_name="TestPage",
        persona="test pm",
        brand=BrandProfile(
            mission="test",
            visual=VisualIdentity(colors=["#FFF"], style="minimal"),
            platforms=["instagram"],
            tone="casual",
            target_audience="Gen Z",
            script_style="lowercase",
        ),
    )


def _make_job(published_at=None):
    from models.content_job import ContentJob
    job = ContentJob(project="test", pm=_make_pm(), brief="test", platforms=["instagram"])
    job.published_at = published_at
    return job


def test_read_queue_returns_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from track_queue import read_queue
    assert read_queue() == []


def test_write_and_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue, read_queue
    entries = [{"job_id": "abc", "page_name": "TestPage",
                "track_at": "2026-05-18T14:00:00Z", "attempt": 0}]
    write_queue(entries)
    assert read_queue() == entries


def test_write_queue_is_atomic_no_tmp_file_left(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue
    write_queue([{"job_id": "abc", "page_name": "TestPage",
                  "track_at": "2026-05-18T14:00:00Z", "attempt": 0}])
    assert not (tmp_path / "output" / "track_queue.json.tmp").exists()
    data = json.loads((tmp_path / "output" / "track_queue.json").read_text())
    assert isinstance(data, list)


def test_read_queue_backs_up_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "track_queue.json").write_text("not valid json ][")
    from track_queue import read_queue
    assert read_queue() == []
    assert (tmp_path / "output" / "track_queue.json.corrupt").exists()


def test_enqueue_writes_two_entries_with_correct_offsets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import enqueue_track_snapshots, read_queue
    published_at = datetime(2026, 5, 17, 14, 0, 0, tzinfo=timezone.utc)
    job = _make_job(published_at=published_at)
    enqueue_track_snapshots(job)
    entries = read_queue()
    assert len(entries) == 2
    assert entries[0]["track_at"] == "2026-05-18T14:00:00Z"
    assert entries[1]["track_at"] == "2026-05-20T14:00:00Z"
    assert entries[0]["job_id"] == job.id
    assert entries[0]["page_name"] == "TestPage"
    assert entries[0]["attempt"] == 0


def test_enqueue_falls_back_to_now_when_published_at_is_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import enqueue_track_snapshots, read_queue
    before = datetime.now(timezone.utc)
    job = _make_job(published_at=None)
    enqueue_track_snapshots(job)
    after = datetime.now(timezone.utc)
    entries = read_queue()
    assert len(entries) == 2
    t24 = datetime.strptime(entries[0]["track_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert before + timedelta(hours=24) <= t24 <= after + timedelta(hours=24)


def test_enqueue_appends_to_existing_queue(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import enqueue_track_snapshots, read_queue
    published_at = datetime(2026, 5, 17, 14, 0, 0, tzinfo=timezone.utc)
    job1 = _make_job(published_at=published_at)
    job2 = _make_job(published_at=published_at)
    enqueue_track_snapshots(job1)
    enqueue_track_snapshots(job2)
    assert len(read_queue()) == 4
```

- [ ] **Step 2: Run to verify all fail**

```bash
pytest tests/test_track_queue.py -v
```
Expected: all `FAILED` — `track_queue` module does not exist.

- [ ] **Step 3: Create `track_queue.py`**

```python
from __future__ import annotations
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models.content_job import ContentJob

_QUEUE_FILE = Path("output/track_queue.json")
_QUEUE_TMP = Path("output/track_queue.json.tmp")
_QUEUE_CORRUPT = Path("output/track_queue.json.corrupt")


def read_queue() -> list[dict]:
    if not _QUEUE_FILE.exists():
        return []
    try:
        data = json.loads(_QUEUE_FILE.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        try:
            _QUEUE_FILE.rename(_QUEUE_CORRUPT)
        except OSError:
            pass
        return []


def write_queue(entries: list[dict]) -> None:
    _QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _QUEUE_TMP.write_text(json.dumps(entries, indent=2))
    os.replace(_QUEUE_TMP, _QUEUE_FILE)


def enqueue_track_snapshots(
    job: ContentJob,
    offsets_hours: list[int] | None = None,
) -> None:
    if offsets_hours is None:
        offsets_hours = [24, 72]
    base = job.published_at if job.published_at is not None else datetime.now(timezone.utc)
    entries = read_queue()
    for offset in offsets_hours:
        track_at = base + timedelta(hours=offset)
        entries.append({
            "job_id": job.id,
            "page_name": job.pm.page_name,
            "track_at": track_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "attempt": 0,
        })
    write_queue(entries)
```

- [ ] **Step 4: Run to verify all pass**

```bash
pytest tests/test_track_queue.py -v
```
Expected: all `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add track_queue.py tests/test_track_queue.py
git commit -m "feat: add track_queue module for performance snapshot scheduling"
```

---

## Task 3: Update `PublishAgent` — set `published_at` and enqueue

**Files:**
- Modify: `agents/publish.py`
- Modify: `tests/test_publish.py`

**Context:** `published_at` must be set before `enqueue_track_snapshots` is called. For immediate posts, `published_at = datetime.now(UTC)`. For scheduled posts, `published_at = datetime.fromtimestamp(scheduled_time, UTC)`. Enqueue only fires on live (non-dry-run) publishes where at least one platform succeeded.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_publish.py`:

```python
def test_publish_sets_published_at_for_immediate_post(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from agents.publish import PublishAgent
    from config import Config
    config = Config(anthropic_api_key="x", brave_search_api_key="", openai_api_key="",
                    meta_access_token="tok", meta_page_id="pid", meta_ig_user_id="igid")
    agent = PublishAgent(config)
    job = _make_completed_job()  # use existing helper from test_publish.py
    job.dry_run = False
    mocker.patch.object(agent, "_post_facebook", return_value={"id": "fb1"})
    mocker.patch.object(agent, "_post_instagram", return_value={"id": "ig1"})
    mocker.patch("agents.publish.enqueue_track_snapshots")
    before = datetime.now(timezone.utc)
    agent.run_live(job)
    after = datetime.now(timezone.utc)
    assert job.published_at is not None
    assert before <= job.published_at <= after


def test_publish_sets_published_at_for_scheduled_post(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from agents.publish import PublishAgent
    from config import Config
    from datetime import timezone
    config = Config(anthropic_api_key="x", brave_search_api_key="", openai_api_key="",
                    meta_access_token="tok", meta_page_id="pid", meta_ig_user_id="igid")
    agent = PublishAgent(config)
    job = _make_completed_job()
    job.dry_run = False
    scheduled_ts = 1800000000  # fixed future Unix timestamp
    mocker.patch.object(agent, "_post_facebook", return_value={"id": "fb1"})
    mocker.patch.object(agent, "_queue_instagram", return_value={"status": "pending_queue"})
    mocker.patch("agents.publish.enqueue_track_snapshots")
    agent.run_live(job, schedule=True)
    expected = datetime.fromtimestamp(scheduled_ts, tz=timezone.utc)
    # published_at should equal the scheduled time (within a few seconds of Roxy's computed time)
    assert job.published_at is not None


def test_publish_enqueues_track_snapshots_after_live_publish(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from agents.publish import PublishAgent
    from config import Config
    config = Config(anthropic_api_key="x", brave_search_api_key="", openai_api_key="",
                    meta_access_token="tok", meta_page_id="pid", meta_ig_user_id="igid")
    agent = PublishAgent(config)
    job = _make_completed_job()
    job.dry_run = False
    mocker.patch.object(agent, "_post_facebook", return_value={"id": "fb1"})
    mocker.patch.object(agent, "_post_instagram", return_value={"id": "ig1"})
    mock_enqueue = mocker.patch("agents.publish.enqueue_track_snapshots")
    agent.run_live(job)
    mock_enqueue.assert_called_once_with(job)


def test_publish_dry_run_does_not_enqueue(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from agents.publish import PublishAgent
    from config import Config
    config = Config(anthropic_api_key="x", brave_search_api_key="", openai_api_key="")
    agent = PublishAgent(config)
    job = _make_completed_job()
    job.dry_run = True
    mock_enqueue = mocker.patch("agents.publish.enqueue_track_snapshots")
    agent.run_dry(job)
    mock_enqueue.assert_not_called()
```

- [ ] **Step 2: Run to verify failures**

```bash
pytest tests/test_publish.py::test_publish_sets_published_at_for_immediate_post tests/test_publish.py::test_publish_enqueues_track_snapshots_after_live_publish tests/test_publish.py::test_publish_dry_run_does_not_enqueue -v
```
Expected: all `FAILED`.

- [ ] **Step 3: Update `agents/publish.py`**

Add import at top of `agents/publish.py`:

```python
from datetime import datetime, timezone
from track_queue import enqueue_track_snapshots
```

In `run_live()`, after `job.publish_result = result` and before `job.stage = "publish_done"`:

```python
        job.publish_result = result
        job.stage = "publish_done"

        # Set published_at and enqueue tracking snapshots if at least one platform succeeded
        _published_statuses = {"published", "scheduled", "pending_queue"}
        any_published = any(
            isinstance(v, dict) and v.get("status") in _published_statuses
            for v in result.values()
        )
        if any_published:
            job.published_at = (
                datetime.fromtimestamp(scheduled_time, tz=timezone.utc)
                if scheduled_time else datetime.now(timezone.utc)
            )
            enqueue_track_snapshots(job)

        return job
```

- [ ] **Step 4: Run publish tests**

```bash
pytest tests/test_publish.py -v
```
Expected: all `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add agents/publish.py tests/test_publish.py
git commit -m "feat: set published_at and enqueue tracking snapshots after live publish"
```

---

## Task 4: Create `track_scheduler.py`

**Files:**
- Create: `track_scheduler.py`
- Create: `tests/test_track_scheduler.py`

**Context:** Same subprocess + logging pattern as `scheduler.py`. Reads the queue, processes overdue entries sequentially, retries up to 3× (attempt 0→1→2, removed on attempt 3). Uses `notifier.send_healthcheck_alert` for final-failure alerts. Subprocess timeout is 60s.

- [ ] **Step 1: Create `tests/test_track_scheduler.py` with all failing tests**

```python
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import sys
import pytest

_google = MagicMock()
sys.modules.setdefault("google", _google)
sys.modules.setdefault("google.genai", _google.genai)


def _past(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _future(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_empty_queue_returns_zero_and_runs_no_subprocess(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    mock_run = mocker.patch("track_scheduler.subprocess.run")
    from track_scheduler import run_track_scheduler
    result = run_track_scheduler(root=tmp_path)
    assert result == 0
    mock_run.assert_not_called()


def test_future_entries_are_skipped(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue
    write_queue([{"job_id": "abc", "page_name": "Test",
                  "track_at": _future(24), "attempt": 0}])
    mocker.patch("track_scheduler.subprocess.run")
    from track_scheduler import run_track_scheduler
    run_track_scheduler(root=tmp_path)
    from track_queue import read_queue
    assert len(read_queue()) == 1


def test_overdue_entry_fires_subprocess_with_correct_args(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue, read_queue
    write_queue([{"job_id": "job123", "page_name": "Test",
                  "track_at": _past(2), "attempt": 0}])
    mock_run = mocker.patch("track_scheduler.subprocess.run",
                            return_value=MagicMock(returncode=0))
    from track_scheduler import run_track_scheduler
    run_track_scheduler(root=tmp_path)
    cmd = mock_run.call_args[0][0]
    assert "--track" in cmd
    assert "job123" in cmd
    assert read_queue() == []


def test_failed_track_increments_attempt_and_stays_in_queue(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue, read_queue
    write_queue([{"job_id": "abc", "page_name": "Test",
                  "track_at": _past(), "attempt": 0}])
    mocker.patch("track_scheduler.subprocess.run",
                 return_value=MagicMock(returncode=1))
    from track_scheduler import run_track_scheduler
    run_track_scheduler(root=tmp_path)
    entries = read_queue()
    assert len(entries) == 1
    assert entries[0]["attempt"] == 1


def test_second_failure_increments_attempt_to_2(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue, read_queue
    write_queue([{"job_id": "abc", "page_name": "Test",
                  "track_at": _past(), "attempt": 1}])
    mocker.patch("track_scheduler.subprocess.run",
                 return_value=MagicMock(returncode=1))
    from track_scheduler import run_track_scheduler
    run_track_scheduler(root=tmp_path)
    entries = read_queue()
    assert entries[0]["attempt"] == 2


def test_third_failure_alerts_and_removes_entry(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue, read_queue
    write_queue([{"job_id": "abc", "page_name": "Test",
                  "track_at": _past(), "attempt": 2}])
    mocker.patch("track_scheduler.subprocess.run",
                 return_value=MagicMock(returncode=1))
    mock_alert = mocker.patch("track_scheduler.send_healthcheck_alert")
    from track_scheduler import run_track_scheduler
    run_track_scheduler(root=tmp_path)
    mock_alert.assert_called_once()
    assert "abc" in mock_alert.call_args[0][0]
    assert read_queue() == []


def test_timeout_counts_as_failure(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue, read_queue
    import subprocess
    write_queue([{"job_id": "abc", "page_name": "Test",
                  "track_at": _past(), "attempt": 0}])
    mock_run = mocker.patch("track_scheduler.subprocess.run",
                            side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=60))
    from track_scheduler import run_track_scheduler
    run_track_scheduler(root=tmp_path)
    entries = read_queue()
    assert entries[0]["attempt"] == 1


def test_dry_run_skips_subprocess(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue, read_queue
    write_queue([{"job_id": "abc", "page_name": "Test",
                  "track_at": _past(), "attempt": 0}])
    mock_run = mocker.patch("track_scheduler.subprocess.run")
    from track_scheduler import run_track_scheduler
    run_track_scheduler(dry_run=True, root=tmp_path)
    mock_run.assert_not_called()
    assert len(read_queue()) == 1


def test_corrupt_queue_resets_and_continues(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "track_queue.json").write_text("not json ][")
    mock_run = mocker.patch("track_scheduler.subprocess.run")
    from track_scheduler import run_track_scheduler
    result = run_track_scheduler(root=tmp_path)
    assert result == 0
    mock_run.assert_not_called()
```

- [ ] **Step 2: Run to verify all fail**

```bash
pytest tests/test_track_scheduler.py -v
```
Expected: all `FAILED` — `track_scheduler` module does not exist.

- [ ] **Step 3: Create `track_scheduler.py`**

```python
from __future__ import annotations
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from activity_logger import log_action
from notifier import send_healthcheck_alert
from track_queue import read_queue, write_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent
_MAX_ATTEMPTS = 3
_SUBPROCESS_TIMEOUT = 60


def run_track_scheduler(dry_run: bool = False, root: Path | None = None) -> int:
    _root = root if root is not None else _ROOT
    now = datetime.now(timezone.utc)
    entries = read_queue()

    if not entries:
        logger.info("Track queue is empty — nothing to do")
        return 0

    remaining: list[dict] = []

    for entry in entries:
        track_at_str = entry.get("track_at", "")
        try:
            track_at = datetime.strptime(track_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            logger.error("Invalid track_at=%r — dropping entry", track_at_str)
            continue

        if track_at > now:
            remaining.append(entry)
            continue

        job_id = entry["job_id"]
        page_name = entry.get("page_name", "unknown")
        attempt = entry.get("attempt", 0)

        logger.info("Tracking job=%s page=%s attempt=%d", job_id, page_name, attempt)
        log_action("track_scheduler_run", {"job_id": job_id, "attempt": attempt})

        if dry_run:
            logger.info("DRY-RUN: skipping subprocess for job=%s", job_id)
            remaining.append(entry)
            continue

        cmd = [sys.executable, str(_root / "main.py"), "--track", job_id]
        success = False
        try:
            result = subprocess.run(cmd, cwd=_root, timeout=_SUBPROCESS_TIMEOUT)
            success = result.returncode == 0
        except subprocess.TimeoutExpired as exc:
            if exc.process:
                exc.process.kill()
                exc.process.communicate()
            logger.error("TIMEOUT tracking job=%s", job_id)

        if success:
            logger.info("OK: tracked job=%s", job_id)
        else:
            attempt += 1
            if attempt >= _MAX_ATTEMPTS:
                msg = (
                    f":warning: Track scheduler: job {job_id} ({page_name}) "
                    f"failed {_MAX_ATTEMPTS}x — giving up. Check Meta API credentials."
                )
                logger.error(msg)
                send_healthcheck_alert(msg)
            else:
                logger.warning("FAILED: job=%s — attempt=%d, will retry next hour", job_id, attempt)
                remaining.append({**entry, "attempt": attempt})

    write_queue(remaining)
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NayzFreedom hourly track scheduler")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be tracked without running subprocess")
    args = parser.parse_args()
    sys.exit(run_track_scheduler(dry_run=args.dry_run))
```

- [ ] **Step 4: Run to verify all pass**

```bash
pytest tests/test_track_scheduler.py -v
```
Expected: all `PASSED`.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
pytest --tb=short
```
Expected: all `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add track_scheduler.py tests/test_track_scheduler.py
git commit -m "feat: add track_scheduler — hourly cron worker for performance snapshot queue"
```

---

## Task 5: Add deploy files and update `setup.sh`

**Files:**
- Create: `deploy/nayzfreedom-track-scheduler.service`
- Create: `deploy/nayzfreedom-track-scheduler.timer`
- Modify: `deploy/setup.sh`

**Context:** Follows the exact same pattern as existing `nayzfreedom-scheduler.service` / `.timer`. The timer uses `OnUnitActiveSec=1h` (every hour from last run) rather than `OnCalendar` (fixed clock time), so it self-paces even after a slow run.

- [ ] **Step 1: Create `deploy/nayzfreedom-track-scheduler.service`**

```ini
[Unit]
Description=NayzFreedom Track Scheduler — hourly performance snapshot worker
After=network.target

[Service]
Type=oneshot
User=nayzfreedom
WorkingDirectory=/opt/nayzfreedom
ExecStart=/opt/nayzfreedom/.venv/bin/python track_scheduler.py
StandardOutput=append:/var/log/nayzfreedom.log
StandardError=append:/var/log/nayzfreedom.log
```

- [ ] **Step 2: Create `deploy/nayzfreedom-track-scheduler.timer`**

```ini
[Unit]
Description=Run NayzFreedom Track Scheduler every hour
Requires=nayzfreedom-track-scheduler.service

[Timer]
OnBootSec=10min
OnUnitActiveSec=1h
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Add the new unit to `deploy/setup.sh`**

In the `for unit in \` block (lines 88–108), add before the closing `; do`:

```bash
    nayzfreedom-track-scheduler.service \
    nayzfreedom-track-scheduler.timer \
```

After `systemctl enable --now nayzfreedom-ops-report.timer`, add:

```bash
systemctl enable --now nayzfreedom-track-scheduler.timer
```

And update the "Timers scheduled:" echo block at the bottom to include:

```bash
echo "  Track:     every hour (on-demand)"
```

- [ ] **Step 4: Commit**

```bash
git add deploy/nayzfreedom-track-scheduler.service deploy/nayzfreedom-track-scheduler.timer deploy/setup.sh
git commit -m "feat: add systemd service/timer for track_scheduler hourly cron"
```

---

## Task 6: Show snapshot status on the dashboard job detail page

**Files:**
- Modify: `dashboard.py` (or `routes/jobs.py` if the dashboard has been split into route modules)

**Context:** The `/jobs/{job_id}` route already renders a job detail page. Read `track_queue.json` in the route handler and pass snapshot state into the template context. No new routes or templates needed — just enrich the existing context dict.

- [ ] **Step 1: Find the `/jobs/{job_id}` route handler**

```bash
grep -n "jobs/{job_id}\|def.*job_detail\|job_id.*route" dashboard.py
```

Note the line number. The handler reads `job` from `find_job(job_id)` and calls `templates.TemplateResponse(...)`.

- [ ] **Step 2: Add `track_queue` import at top of the file**

Add alongside existing imports:

```python
from track_queue import read_queue
```

- [ ] **Step 3: Add snapshot context to the job detail handler**

Inside the `/jobs/{job_id}` handler, before the `TemplateResponse` call, add:

```python
    # Snapshot tracking status
    queue = read_queue()
    job_queue_entries = [e for e in queue if e["job_id"] == job.id]
    snapshot_count = len(job.performance)
    if job_queue_entries:
        next_snapshot = min(job_queue_entries, key=lambda e: e["track_at"])
        snapshot_status = f"Next snapshot: {next_snapshot['track_at']} UTC"
    elif snapshot_count >= 2:
        snapshot_status = "24h ✓ — 72h ✓"
    elif snapshot_count == 1:
        snapshot_status = "24h tracked ✓ — 72h pending"
    else:
        snapshot_status = "No performance data yet"
```

Pass `snapshot_status=snapshot_status` into the template context dict.

- [ ] **Step 4: Add `snapshot_status` to the job detail template**

Find the job detail template file (check `templates/` directory):

```bash
ls /Users/nennayz/Documents/NayzFreedom/code/nayzfreedom-fleet/templates/
```

In the job detail template, add in the mission stats section:

```html
<p class="snapshot-status">{{ snapshot_status }}</p>
```

- [ ] **Step 5: Run dashboard tests**

```bash
pytest tests/test_dashboard.py -v --tb=short
```
Expected: all `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add dashboard.py templates/
git commit -m "feat: show performance snapshot status on job detail page"
```

---

## Final Verification

- [ ] **Run the full test suite**

```bash
cd /Users/nennayz/Documents/NayzFreedom/code/nayzfreedom-fleet
source .venv/bin/activate
pytest --tb=short
```
Expected: all `PASSED`, no new failures.

- [ ] **Dry-run the track scheduler manually**

```bash
python track_scheduler.py --dry-run
```
Expected: `Track queue is empty — nothing to do` (or lists pending entries if any exist).

- [ ] **End-to-end dry-run smoke test**

```bash
python main.py --project nayzfreedom_fleet --brief "test" --dry-run --unattended
```
After it completes, check that `output/track_queue.json` was **not** written (dry-run publish should not enqueue):

```bash
cat output/track_queue.json 2>/dev/null || echo "file not created — correct"
```

- [ ] **Final commit tag**

```bash
git tag auto-track-v1
```
