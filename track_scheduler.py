from __future__ import annotations
import logging
import json
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
_HISTORY_RELATIVE = Path("logs/track_scheduler_history.jsonl")


def _history_path(root: Path) -> Path:
    return root / _HISTORY_RELATIVE


def _write_history(root: Path, record: dict[str, object]) -> None:
    path = _history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def recent_track_scheduler_history(root: Path, limit: int = 5) -> list[dict[str, object]]:
    path = _history_path(root)
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append({
            "timestamp": str(item.get("timestamp", "")),
            "state": str(item.get("state", "Unknown")),
            "processed": int(item.get("processed") or 0),
            "succeeded": int(item.get("succeeded") or 0),
            "retrying": int(item.get("retrying") or 0),
            "failed": int(item.get("failed") or 0),
            "remaining": int(item.get("remaining") or 0),
            "dry_run": bool(item.get("dry_run")),
            "jobs": item.get("jobs", []) if isinstance(item.get("jobs"), list) else [],
        })
    return list(reversed(rows))


def run_track_scheduler(dry_run: bool = False, root: Path | None = None) -> int:
    _root = root if root is not None else _ROOT
    now = datetime.now(timezone.utc)
    entries = read_queue(_root)

    if not entries:
        logger.info("Track queue is empty — nothing to do")
        _write_history(_root, {
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "state": "Ready",
            "processed": 0,
            "succeeded": 0,
            "retrying": 0,
            "failed": 0,
            "remaining": 0,
            "dry_run": dry_run,
            "jobs": [],
        })
        return 0

    remaining: list[dict] = []
    processed = 0
    succeeded = 0
    retrying = 0
    failed = 0
    jobs: list[dict[str, object]] = []

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
        processed += 1

        logger.info("Tracking job=%s page=%s attempt=%d", job_id, page_name, attempt)
        log_action("track_scheduler_run", {"job_id": job_id, "attempt": attempt})

        if dry_run:
            logger.info("DRY-RUN: skipping subprocess for job=%s", job_id)
            remaining.append(entry)
            jobs.append({"job_id": job_id, "state": "dry_run", "attempt": attempt})
            continue

        cmd = [sys.executable, str(_root / "main.py"), "--track", job_id]
        success = False
        try:
            result = subprocess.run(cmd, cwd=_root, timeout=_SUBPROCESS_TIMEOUT)
            success = result.returncode == 0
        except subprocess.TimeoutExpired as exc:
            try:
                proc = getattr(exc, "process", None)
                if proc:
                    proc.kill()
                    proc.communicate()
            except Exception:
                pass
            logger.error("TIMEOUT tracking job=%s", job_id)

        if success:
            logger.info("OK: tracked job=%s", job_id)
            succeeded += 1
            jobs.append({"job_id": job_id, "state": "succeeded", "attempt": attempt})
        else:
            attempt += 1
            if attempt >= _MAX_ATTEMPTS:
                failed += 1
                msg = (
                    f":warning: Track scheduler: job {job_id} ({page_name}) "
                    f"failed {_MAX_ATTEMPTS}x — giving up. Check Meta API credentials."
                )
                logger.error(msg)
                send_healthcheck_alert(msg)
                jobs.append({"job_id": job_id, "state": "failed", "attempt": attempt})
            else:
                retrying += 1
                logger.warning("FAILED: job=%s — attempt=%d, will retry next hour", job_id, attempt)
                remaining.append({**entry, "attempt": attempt})
                jobs.append({"job_id": job_id, "state": "retrying", "attempt": attempt})

    write_queue(remaining, _root)
    state = "Failed" if failed else "Missing" if retrying else "Ready"
    _write_history(_root, {
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "state": state,
        "processed": processed,
        "succeeded": succeeded,
        "retrying": retrying,
        "failed": failed,
        "remaining": len(remaining),
        "dry_run": dry_run,
        "jobs": jobs,
    })
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NayzFreedom hourly track scheduler")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be tracked without running subprocess")
    args = parser.parse_args()
    sys.exit(run_track_scheduler(dry_run=args.dry_run))
