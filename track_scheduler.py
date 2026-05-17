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
