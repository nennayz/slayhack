from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from knowledge.object import ContentObject
from models.content_job import ContentJob, JobStatus

if TYPE_CHECKING:
    from knowledge.store import KnowledgeStore

logger = logging.getLogger(__name__)

_READY_STAGES = {"emma_done", "publish_done", "generation_completed", "publish_packaged", "publish_queued"}
_SOURCE = "social_packaging_v1"


@dataclass
class SocialPackagingResult:
    page_slug: str
    jobs_found: int = 0
    packages_created: int = 0
    queue_entries_created: int = 0
    jobs_skipped: int = 0
    jobs_failed: int = 0


def run_social_packaging(
    page_slug: str,
    store: "KnowledgeStore",
    root: Path | None = None,
    dry_run: bool = False,
    limit: int = 10,
) -> SocialPackagingResult:
    """Package produced content into KS objects and a locked local publish handoff queue.

    SP-6 intentionally records a dashboard/manual handoff, not a live external publish.
    The live auto-post API path remains behind `publish_control.ensure_auto_posting_enabled`.
    """
    base = root or Path(__file__).resolve().parent
    result = SocialPackagingResult(page_slug=page_slug)
    candidates = _candidate_jobs(base, page_slug)
    result.jobs_found = len(candidates)

    for job_path, job in candidates[:limit]:
        try:
            if _already_packaged(job):
                result.jobs_skipped += 1
                continue
            caption_obj, package_obj = _objects_for_job(job)
            if not dry_run:
                caption_obj = store.add(caption_obj)
                package_obj.parent_uids = [caption_obj.uid]
                package_obj = store.add(package_obj)
                _mark_job_queued(base, job_path, job, caption_obj.uid, package_obj.uid)
                if job.idea_uid:
                    try:
                        store.set_status(job.idea_uid, "done")
                    except Exception as exc:  # noqa: BLE001 - KS status is best-effort, job handoff is already durable
                        logger.warning("Social packaging: failed to mark idea %s done: %s", job.idea_uid, exc)
            result.packages_created += 1
            result.queue_entries_created += 1
        except Exception as exc:  # noqa: BLE001 - keep the daily loop moving across independent jobs
            logger.error("Social packaging failed for job=%s: %s", job.id, exc)
            result.jobs_failed += 1

    return result


def _candidate_jobs(root: Path, page_slug: str) -> list[tuple[Path, ContentJob]]:
    jobs: list[tuple[Path, ContentJob]] = []
    output = root / "output"
    if not output.exists():
        return jobs
    for path in output.glob("*/*/job.json"):
        try:
            job = ContentJob.model_validate_json(path.read_text())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Social packaging: skipping unreadable job %s: %s", path, exc)
            continue
        if job.project != page_slug:
            continue
        if not _ready_for_social_packaging(job):
            continue
        jobs.append((path, job))
    jobs.sort(key=lambda item: item[0].parent.name)
    return jobs


def _ready_for_social_packaging(job: ContentJob) -> bool:
    if job.stage not in _READY_STAGES:
        return False
    if job.growth_strategy is None:
        return False
    if not job.growth_strategy.caption.strip():
        return False
    return True


def _already_packaged(job: ContentJob) -> bool:
    package = job.publish_package if isinstance(job.publish_package, dict) else {}
    execution = job.publish_execution if isinstance(job.publish_execution, dict) else {}
    return package.get("source") == _SOURCE or execution.get("source") == _SOURCE


def _objects_for_job(job: ContentJob) -> tuple[ContentObject, ContentObject]:
    strategy = job.growth_strategy
    if strategy is None:
        raise ValueError("Job has no growth strategy")

    parent_uids = [job.idea_uid] if job.idea_uid else []
    caption = strategy.caption.strip()
    hashtags = [tag if tag.startswith("#") else f"#{tag}" for tag in strategy.hashtags]
    title = _title_for_job(job)
    created_at = datetime.now(timezone.utc)
    platform_text = ", ".join(job.platforms)
    hashtag_text = " ".join(hashtags)

    caption_obj = ContentObject(
        page=job.project,
        kind="caption",
        title=f"Caption: {title}",
        summary=caption[:240],
        body=f"{caption}\n\n{hashtag_text}\n",
        dedup_text=f"{caption}\n{hashtag_text}",
        status="done",
        parent_uids=parent_uids,
        tags=["sp6", "social-packaging", *job.platforms],
        created_at=created_at,
        asset_path=job.video_path or job.image_path,
    )
    package_obj = ContentObject(
        page=job.project,
        kind="publish_package",
        title=f"Publish package: {title}",
        summary=f"Locked social handoff for {platform_text}.",
        body=(
            f"# Publish Package\n\n"
            f"- Job: {job.id}\n"
            f"- Platforms: {platform_text}\n"
            f"- Live publish: locked/off\n"
            f"- Recommended UTC: {strategy.best_post_time_utc}\n"
            f"- Recommended Thai time: {strategy.best_post_time_thai}\n\n"
            f"## Caption\n{caption}\n\n"
            f"## Hashtags\n{hashtag_text}\n"
        ),
        dedup_text=f"{job.id}\n{platform_text}\n{caption}\n{hashtag_text}",
        status="new",
        parent_uids=[],
        tags=["sp6", "publish-queue", *job.platforms],
        created_at=created_at,
        asset_path=job.video_path or job.image_path,
    )
    return caption_obj, package_obj


def _mark_job_queued(root: Path, job_path: Path, job: ContentJob, caption_uid: str, package_uid: str) -> None:
    strategy = job.growth_strategy
    if strategy is None:
        raise ValueError("Job has no growth strategy")
    queued_at = datetime.now(timezone.utc).isoformat()
    hashtags = [tag if tag.startswith("#") else f"#{tag}" for tag in strategy.hashtags]
    package: dict[str, Any] = {
        "status": "completed",
        "source": _SOURCE,
        "owners": ["Roxy", "Emma"],
        "caption": strategy.caption.strip(),
        "hashtags": hashtags,
        "caption_uid": caption_uid,
        "package_uid": package_uid,
        "created_at": queued_at,
        "next_action": "Captain reviews the queued package before any separate live publish approval.",
    }
    execution: dict[str, Any] = {
        "status": "queued",
        "source": _SOURCE,
        "owners": ["Roxy", "Emma"],
        "platforms": list(job.platforms),
        "caption_uid": caption_uid,
        "package_uid": package_uid,
        "queued_at": queued_at,
        "live_publish": False,
        "next_action": "Local handoff only; no platform API was called.",
    }
    job.publish_package = package
    job.publish_execution = execution
    job.publish_result = {
        platform: {
            "status": "scheduled",
            "source": _SOURCE,
            "dry_run": True,
            "queued_at": queued_at,
            "reason": "SP-6 local publish queue handoff; live external publishing remains locked.",
        }
        for platform in job.platforms
    }
    job.stage = "publish_queued"
    job.status = JobStatus.AWAITING_APPROVAL
    job_path.write_text(job.model_dump_json(indent=2))

    queue_path = root / "output" / "publish_queue.jsonl"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.open("a", encoding="utf-8").write(
        json.dumps(
            {
                "job_id": job.id,
                "project": job.project,
                "page_name": job.pm.page_name,
                "caption_uid": caption_uid,
                "package_uid": package_uid,
                "platforms": job.platforms,
                "queued_at": queued_at,
                "live_publish": False,
            },
            ensure_ascii=False,
        )
        + "\n"
    )


def _title_for_job(job: ContentJob) -> str:
    if job.selected_idea is not None:
        return job.selected_idea.title
    return job.brief.strip()[:80] or job.id
