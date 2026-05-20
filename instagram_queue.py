from __future__ import annotations
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from agents.publish import PublishAgent, has_publish_failures, sanitize_error_text
from config import Config
from job_store import save_job
from models.content_job import ContentJob, JobStatus
from publish_control import auto_posting_disabled
from work_activity import write_work_activity

_IG_MAX_RETRIES = 3
_IG_RETRY_DELAY_SECONDS = 15 * 60
_IG_QUEUE_HISTORY = Path("logs") / "instagram_queue_history.jsonl"


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _history_path(root: Path) -> Path:
    return root / _IG_QUEUE_HISTORY


def _write_queue_history(root: Path, record: dict[str, object]) -> None:
    path = _history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def _write_queue_work_activity(root: Path, record: dict[str, object]) -> None:
    try:
        write_work_activity(
            root,
            "implementation_step",
            "Instagram queue run completed",
            actor="instagram_queue.py",
            command="instagram_queue.py --dry-run" if record.get("dry_run") else "instagram_queue.py",
            result=(
                f"processed={record['processed']} published={record['published']} "
                f"retrying={record['retrying']} failed={record['failed']}"
            ),
            metadata=record,
        )
    except Exception:
        # Queue execution should not fail because its observability log is unavailable.
        pass


def _pending_instagram_jobs(root: Path, now_ts: int) -> list[ContentJob]:
    jobs: list[ContentJob] = []
    output_dir = root / "output"
    for job_file in output_dir.glob("*/*/job.json"):
        try:
            job = ContentJob.model_validate_json(job_file.read_text())
        except (json.JSONDecodeError, ValueError, OSError):
            continue
        ig_result = (job.publish_result or {}).get("instagram", {})
        if not isinstance(ig_result, dict):
            continue
        status = ig_result.get("status")
        if status not in {"pending_queue", "retrying"}:
            continue
        due = int(ig_result.get("next_retry_unix") or ig_result.get("scheduled_publish_time") or 0)
        if due <= now_ts:
            jobs.append(job)
    return sorted(jobs, key=lambda job: job.id)


def _retry_instagram_result(previous: dict, failed_result: dict, now_ts: int) -> dict:
    retry_count = int(previous.get("retry_count") or 0) + 1
    if retry_count >= _IG_MAX_RETRIES:
        return {
            **failed_result,
            "status": "failed",
            "retry_count": retry_count,
            "error": sanitize_error_text(str(failed_result.get("error", "Instagram publish failed"))),
        }
    next_retry = datetime.fromtimestamp(now_ts, tz=timezone.utc) + timedelta(seconds=_IG_RETRY_DELAY_SECONDS)
    return {
        **failed_result,
        "status": "retrying",
        "retry_count": retry_count,
        "next_retry_unix": int(next_retry.timestamp()),
        "next_retry_at": next_retry.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "error": sanitize_error_text(str(failed_result.get("error", "Instagram publish failed"))),
    }


def process_instagram_queue(root: Path | None = None, dry_run: bool = False) -> int:
    root = root or Path(__file__).resolve().parent
    load_dotenv(root / ".env")
    if auto_posting_disabled() and not dry_run:
        record = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dry_run": False,
            "blocked": True,
            "reason": "NAYZ_AUTO_POSTING_DISABLED=1",
            "processed": 0,
            "published": 0,
            "retrying": 0,
            "failed": 0,
            "jobs": [],
        }
        _write_queue_history(root, record)
        _write_queue_work_activity(root, record)
        print("auto_posting_disabled=1")
        print("processed=0 failures=0")
        return 0
    config = Config.from_env()
    agent = PublishAgent(config)
    processed = 0
    failures = 0
    published = 0
    retrying = 0
    failed = 0
    processed_jobs: list[dict[str, str]] = []

    now_ts = _now_ts()
    for job in _pending_instagram_jobs(root, now_ts):
        processed += 1
        if dry_run:
            print(f"would_publish_instagram={job.id}")
            processed_jobs.append({"job_id": job.id, "status": "dry_run"})
            continue

        original_platforms = list(job.platforms)
        original_result = dict(job.publish_result or {})
        job.platforms = ["instagram"]
        job = agent.run(job, schedule=False)
        ig_result = (job.publish_result or {}).get("instagram")
        previous_ig = original_result.get("instagram", {}) if isinstance(original_result.get("instagram"), dict) else {}
        if isinstance(ig_result, dict) and ig_result.get("status") == "failed":
            ig_result = _retry_instagram_result(previous_ig, ig_result, now_ts)
        merged_result = {**original_result, "instagram": ig_result}
        job.publish_result = merged_result
        job.platforms = original_platforms
        if has_publish_failures(merged_result):
            failures += 1
            job.status = JobStatus.FAILED
        else:
            job.status = JobStatus.COMPLETED
        save_job(job)
        final_status = ig_result.get("status") if isinstance(ig_result, dict) else "unknown"
        if final_status == "published":
            published += 1
        elif final_status == "retrying":
            retrying += 1
        elif final_status == "failed":
            failed += 1
        processed_jobs.append({"job_id": job.id, "status": str(final_status)})
        print(f"published_instagram={job.id}:{final_status}")

    record = {
        "timestamp": datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": dry_run,
        "processed": processed,
        "published": published,
        "retrying": retrying,
        "failed": failed,
        "jobs": processed_jobs,
    }
    _write_queue_history(root, record)
    _write_queue_work_activity(root, record)
    print(f"processed={processed} failures={failures}")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish queued Instagram jobs when due.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    raise SystemExit(process_instagram_queue(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
