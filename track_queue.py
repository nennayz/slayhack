from __future__ import annotations
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models.content_job import ContentJob

_QUEUE_RELATIVE = Path("output/track_queue.json")
_QUEUE_TMP_RELATIVE = Path("output/track_queue.json.tmp")
_QUEUE_CORRUPT_RELATIVE = Path("output/track_queue.json.corrupt")


def _path(root: Path | None, relative: Path) -> Path:
    return (root / relative) if root is not None else relative


def queue_file(root: Path | None = None) -> Path:
    return _path(root, _QUEUE_RELATIVE)


def _queue_tmp(root: Path | None = None) -> Path:
    return _path(root, _QUEUE_TMP_RELATIVE)


def _queue_corrupt(root: Path | None = None) -> Path:
    return _path(root, _QUEUE_CORRUPT_RELATIVE)


def read_queue(root: Path | None = None) -> list[dict]:
    path = queue_file(root)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        try:
            path.rename(_queue_corrupt(root))
        except OSError:
            pass
        return []


def write_queue(entries: list[dict], root: Path | None = None) -> None:
    path = queue_file(root)
    tmp_path = _queue_tmp(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.write_text(json.dumps(entries, indent=2))
    os.replace(tmp_path, path)


def enqueue_track_snapshots(
    job: ContentJob,
    offsets_hours: list[int] | None = None,
    root: Path | None = None,
) -> None:
    if offsets_hours is None:
        offsets_hours = [24, 72]
    base = job.published_at if job.published_at is not None else datetime.now(timezone.utc)
    entries = read_queue(root)
    for offset in offsets_hours:
        track_at = base + timedelta(hours=offset)
        entries.append({
            "job_id": job.id,
            "page_name": job.pm.page_name,
            "track_at": track_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "attempt": 0,
        })
    write_queue(entries, root)


def parse_track_at(value: object) -> datetime | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _distance(target: datetime | None, now: datetime) -> str:
    if target is None:
        return "unknown"
    delta = target - now
    total_seconds = int(delta.total_seconds())
    suffix = "from now" if total_seconds >= 0 else "ago"
    seconds = abs(total_seconds)
    if seconds < 60:
        amount = f"{seconds}s"
    elif seconds < 3600:
        amount = f"{seconds // 60}m"
    elif seconds < 86400:
        amount = f"{seconds // 3600}h"
    else:
        amount = f"{seconds // 86400}d"
    return f"{amount} {suffix}"


def summarize_track_queue(
    entries: list[dict] | None = None,
    *,
    now: datetime | None = None,
    limit: int = 12,
) -> dict[str, object]:
    now = now or datetime.now(timezone.utc)
    entries = list(entries if entries is not None else read_queue())
    overdue_after = timedelta(hours=1)
    counts = {
        "total": len(entries),
        "due_now": 0,
        "overdue": 0,
        "future": 0,
        "retrying": 0,
        "invalid": 0,
    }
    rows: list[dict[str, object]] = []
    for entry in entries:
        track_at = parse_track_at(entry.get("track_at"))
        attempt = int(entry.get("attempt") or 0)
        if attempt > 0:
            counts["retrying"] += 1
        if track_at is None:
            counts["invalid"] += 1
            status = "invalid"
            state = "Failed"
            sort_at = datetime.max.replace(tzinfo=timezone.utc)
        elif track_at <= now - overdue_after:
            counts["overdue"] += 1
            counts["due_now"] += 1
            status = "overdue"
            state = "Failed"
            sort_at = track_at
        elif track_at <= now:
            counts["due_now"] += 1
            status = "due now"
            state = "Missing"
            sort_at = track_at
        else:
            counts["future"] += 1
            status = "future"
            state = "Ready"
            sort_at = track_at
        rows.append({
            "job_id": str(entry.get("job_id", "")),
            "page_name": str(entry.get("page_name", "")),
            "track_at": str(entry.get("track_at", "")),
            "attempt": attempt,
            "status": status,
            "state": state,
            "distance": _distance(track_at, now),
            "_sort_at": sort_at,
        })
    order = {"overdue": 0, "invalid": 1, "due now": 2, "retrying": 3, "future": 4}
    rows = sorted(rows, key=lambda item: (order.get(str(item["status"]), 9), item["_sort_at"]))
    for row in rows:
        row.pop("_sort_at", None)
    return {"counts": counts, "rows": rows[:limit]}


def job_tracking_summary(job: ContentJob, entries: list[dict], now: datetime | None = None) -> dict[str, object]:
    now = now or datetime.now(timezone.utc)
    job_entries = [entry for entry in entries if entry.get("job_id") == job.id]
    queue = summarize_track_queue(job_entries, now=now, limit=4)
    snapshots = sorted(
        job.performance,
        key=lambda item: item.recorded_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    if job_entries:
        status = "Queued"
        state = "Missing" if queue["counts"]["due_now"] else "Ready"
        detail = f"{len(job_entries)} queued snapshot checks"
    elif snapshots:
        status = "Tracked"
        state = "Ready"
        detail = f"{len(snapshots)} performance snapshots recorded"
    elif job.published_at is not None:
        status = "Waiting"
        state = "Missing"
        detail = "Published, but no snapshot has been queued or recorded yet"
    else:
        status = "No data"
        state = "Missing"
        detail = "No performance data yet"
    latest = snapshots[0] if snapshots else None
    return {
        "status": status,
        "state": state,
        "detail": detail,
        "queue": queue,
        "latest": latest,
        "snapshot_count": len(snapshots),
    }
