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
