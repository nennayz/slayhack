from __future__ import annotations
import logging
from datetime import date
from pathlib import Path
from typing import cast

from models.content_job import ContentJob
from project_loader import normalize_job_identity
from reporter import PlatformStats, collect_week_data

logger = logging.getLogger(__name__)


def list_all_jobs(root: Path) -> list[ContentJob]:
    output_dir = root / "output"
    if not output_dir.exists():
        return []
    jobs: list[ContentJob] = []
    for job_file in output_dir.glob("*/*/job.json"):
        try:
            job = ContentJob.model_validate_json(job_file.read_text())
            jobs.append(normalize_job_identity(job, root=root))
        except Exception as exc:
            logger.warning("Skipping corrupt job file %s: %s", job_file, exc)
    return sorted(jobs, key=lambda j: j.id, reverse=True)


def load_performance_all(root: Path) -> dict[str, dict[str, PlatformStats]]:
    return collect_week_data(root, date.today())


def summarize_jobs(jobs: list[ContentJob]) -> dict[str, int]:
    return {
        "total": len(jobs),
        "completed": sum(job.status == "completed" for job in jobs),
        "running": sum(job.status == "running" for job in jobs),
        "failed": sum(job.status == "failed" for job in jobs),
        "awaiting_approval": sum(job.status == "awaiting_approval" for job in jobs),
    }


def command_brief(jobs: list[ContentJob]) -> dict[str, str]:
    summary = summarize_jobs(jobs)
    manual_closeout_count = sum(1 for job in jobs if _needs_manual_closeout(job))
    if summary["failed"]:
        return {
            "state": "Needs Captain",
            "action": "Review failed missions before launching new work.",
            "detail": f"{summary['failed']} mission{'s' if summary['failed'] != 1 else ''} failed.",
        }
    if summary["awaiting_approval"]:
        return {
            "state": "Needs Captain",
            "action": "Approve or redirect waiting missions.",
            "detail": f"{summary['awaiting_approval']} mission{'s' if summary['awaiting_approval'] != 1 else ''} awaiting approval.",
        }
    if manual_closeout_count:
        return {
            "state": "Needs Captain",
            "action": "Close manual posting lessons before launching more manual handoffs.",
            "detail": f"{manual_closeout_count} manual post{'s' if manual_closeout_count != 1 else ''} ready for closeout.",
        }
    if summary["running"]:
        return {
            "state": "In Motion",
            "action": "Monitor active missions; no blockers are flagged.",
            "detail": f"{summary['running']} mission{'s' if summary['running'] != 1 else ''} currently running.",
        }
    if summary["total"]:
        return {
            "state": "Clear",
            "action": "Launch the next Aurora mission when the brief is ready.",
            "detail": "No active blockers or running missions.",
        }
    return {
        "state": "Ready",
        "action": "Launch the first Aurora mission when the brief is ready.",
        "detail": "No missions have been logged yet.",
    }


def fleet_status(jobs: list[ContentJob]) -> list[dict[str, str]]:
    summary = summarize_jobs(jobs)
    brief = command_brief(jobs)
    aurora_state = brief["state"]
    if aurora_state == "Needs Captain":
        aurora_detail = f"{summary['failed']} failed · {summary['awaiting_approval']} awaiting approval"
    elif aurora_state == "In Motion":
        aurora_detail = f"{summary['running']} active · {summary['completed']} completed"
    elif summary["total"]:
        aurora_detail = f"{summary['total']} total · ready for next mission"
    else:
        aurora_detail = "Ready for first mission"

    return [
        {
            "name": "The Aurora",
            "href": "/aurora",
            "css_class": "aurora-card",
            "kicker": "Work ship",
            "description": "Brands, missions, publishing, and external impact.",
            "state": aurora_state,
            "detail": aurora_detail,
        },
        {
            "name": "The Freedom",
            "href": "/freedom",
            "css_class": "freedom-card",
            "kicker": "Personal ship",
            "description": "Freedom Five, personal systems, and the Horizon Atlas.",
            "state": "Planned",
            "detail": "Nami comes after privacy and memory boundaries are clear",
        },
        {
            "name": "The Lyra",
            "href": "/lyra",
            "css_class": "lyra-card",
            "kicker": "Music ship",
            "description": "Songs, releases, and the artistic catalog guided by Genie.",
            "state": "Planned",
            "detail": "Genie comes after the Fleet shell is stable",
        },
    ]


def _needs_manual_closeout(job: ContentJob) -> bool:
    kit = cast(dict[str, object], job.manual_post_kit) if isinstance(job.manual_post_kit, dict) else {}
    manual_post_raw = kit.get("manual_post")
    closeout_raw = kit.get("closeout")
    manual_post = cast(dict[str, object], manual_post_raw) if isinstance(manual_post_raw, dict) else {}
    closeout = cast(dict[str, object], closeout_raw) if isinstance(closeout_raw, dict) else {}
    has_manual_post = any(
        isinstance(value, dict) and value.get("status") == "posted" and str(value.get("post_url") or "").strip()
        for value in manual_post.values()
    )
    return has_manual_post and len(job.performance) >= 2 and closeout.get("status") != "closed"


def attention_jobs(jobs: list[ContentJob], limit: int = 5) -> list[ContentJob]:
    priority = {"failed": 0, "awaiting_approval": 1}
    items = [
        job for job in jobs
        if getattr(job.status, "value", str(job.status)) in priority or _needs_manual_closeout(job)
    ]

    def _priority(job: ContentJob) -> int:
        status_value = getattr(job.status, "value", str(job.status))
        if status_value in priority:
            return priority[status_value]
        return 2

    return sorted(
        items,
        key=lambda job: (_priority(job), job.id),
        reverse=False,
    )[:limit]


def active_jobs(jobs: list[ContentJob], limit: int = 5) -> list[ContentJob]:
    return [
        job for job in jobs
        if getattr(job.status, "value", str(job.status)) == "running"
    ][:limit]
