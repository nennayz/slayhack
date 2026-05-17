"""All dashboard helper functions — shared by route modules and re-exported by dashboard.py."""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import struct
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
import yaml
from fastapi import HTTPException, Request
from crew_registry import CREW, WORKFLOW_STEPS, get_crew_member
from dashboard_store import (
    active_jobs,
    attention_jobs,
    command_brief,
    fleet_status,
    list_all_jobs,
    load_performance_all,
    summarize_jobs,
)
from job_store import find_job, save_job
from models.aurora_workflow import (
    CalendarSlate,
    CrossTeamRequest,
    MissionType,
    PerformanceBucket,
    PerformanceReview,
    ProductionTicket,
    ProductionTicketType,
    VideoPackageScene,
    VideoProductionPackage,
    StoryboardScene,
)
from models.content_job import ContentJob, ContentType, GrowthStrategy, JobStatus, PostPerformance, QAResult
from project_loader import (
    list_project_slugs,
    load_project,
    load_project_page_name,
    project_slug_matches,
    resolve_project_slug,
)
from work_activity import read_recent_work_activity, work_activity_status, write_work_activity
from track_queue import parse_track_at, read_queue, summarize_track_queue
from track_scheduler import recent_track_scheduler_history


OPS_PUBLIC_BASE_URL = os.environ.get("OPS_PUBLIC_BASE_URL", "https://fleet.nayzfreedom.cloud").rstrip("/")
OPS_UNITS = [
    "nayzfreedom-dashboard.service",
    "nayzfreedom-bot.service",
    "nayzfreedom-scheduler.timer",
    "nayzfreedom-reporter.timer",
    "nayzfreedom-instagram-queue.timer",
    "nayzfreedom-backup.timer",
    "nayzfreedom-healthcheck.timer",
    "nayzfreedom-production-summary.timer",
    "nayzfreedom-log-retention.timer",
    "nayzfreedom-ops-report.timer",
    "nayzfreedom-track-scheduler.timer",
]
OPS_ACTIONS = {
    "backup": {
        "label": "Run backup now",
        "unit": "nayzfreedom-backup.service",
        "verb": "start",
    },
    "instagram_queue": {
        "label": "Run due Instagram queue now",
        "unit": "nayzfreedom-instagram-queue.service",
        "verb": "start",
    },
    "production_summary": {
        "label": "Run production summary now",
        "unit": "nayzfreedom-production-summary.service",
        "verb": "start",
    },
    "ops_report": {
        "label": "Send Ops report now",
        "unit": "nayzfreedom-ops-report.service",
        "verb": "start",
    },
    "track_scheduler": {
        "label": "Run tracking queue now",
        "unit": "nayzfreedom-track-scheduler.service",
        "verb": "start",
    },
    "restart_dashboard": {
        "label": "Restart dashboard",
        "unit": "nayzfreedom-dashboard.service",
        "verb": "restart",
        "delayed": True,
    },
}

def _status_label(value: object) -> str:
    raw = getattr(value, "value", str(value))
    return raw.replace("_", " ").title()




def _publish_status_items(job) -> list[dict[str, str]]:
    result = job.publish_result or {}
    if not isinstance(result, dict):
        return []
    items = []
    for platform in ("facebook", "instagram", "tiktok", "youtube"):
        value = result.get(platform)
        if not isinstance(value, dict):
            continue
        status = value.get("status", "unknown")
        if status == "scheduled" and value.get("dry_run") is True:
            label = f"{platform.title()} handoff"
        elif platform == "facebook" and status == "scheduled":
            label = "Facebook scheduled"
        elif platform == "instagram" and status == "published":
            label = "Instagram published"
        elif platform == "instagram" and status == "pending_queue":
            label = "Instagram pending queue"
        elif platform == "instagram" and status == "retrying":
            label = "Instagram retrying"
        else:
            label = f"{platform.title()} {str(status).replace('_', ' ')}"
        items.append({"platform": platform, "status": str(status), "label": label})
    return items




def _publish_history_items(job) -> list[dict[str, str]]:
    items = []
    for item in _publish_status_items(job):
        value = (job.publish_result or {}).get(item["platform"], {})
        if not isinstance(value, dict):
            continue
        detail = value.get("due_at") or value.get("id") or value.get("reason") or value.get("error") or ""
        items.append({**item, "detail": str(detail)})
    return items




def _publish_result_reason(job) -> str:
    result = job.publish_result or {}
    if not isinstance(result, dict):
        return "No dashboard handoff result is recorded yet."
    for platform in ("instagram", "facebook", "tiktok", "youtube"):
        value = result.get(platform)
        if isinstance(value, dict) and value.get("reason"):
            return str(value["reason"])
    return "Dashboard handoff status is recorded without a reason."


def _filter_jobs(jobs, selected: str):
    if selected == "running":
        return [job for job in jobs if getattr(job.status, "value", str(job.status)) == "running"]
    if selected == "failed":
        return [job for job in jobs if getattr(job.status, "value", str(job.status)) == "failed"]
    if selected == "ready_to_publish":
        return [job for job in jobs if _publish_execution_status(job) == "ready_to_publish"]
    if selected == "publish_failed":
        return [job for job in jobs if _publish_execution_status(job) == "failed"]
    if selected in {"scheduled", "queued", "published"}:
        targets = {"scheduled": {"scheduled"}, "queued": {"pending_queue", "retrying"}, "published": {"published"}}[selected]
        return [
            job for job in jobs
            if any(item["status"] in targets for item in _publish_status_items(job))
            or (selected == "scheduled" and _publish_execution_status(job) == "scheduled")
        ]
    return jobs


VALID_CONTENT_TYPES = {"video", "article", "image", "infographic"}
MAX_BRIEF_LEN = 2000
MISSION_FILTER_KEYS = {"all", "running", "failed", "ready_to_publish", "scheduled", "queued", "published", "publish_failed"}


def _mission_filters(jobs, selected: str) -> list[dict[str, object]]:
    filters = [
        ("all", "All"),
        ("running", "Running"),
        ("failed", "Failed"),
        ("ready_to_publish", "Ready to publish"),
        ("scheduled", "Handoffs"),
        ("queued", "Queued"),
        ("published", "Published"),
        ("publish_failed", "Publish failed"),
    ]
    return [
        {
            "key": key,
            "label": label,
            "active": key == selected,
            "count": len(_filter_jobs(jobs, key)),
        }
        for key, label in filters
    ]


def _run_command(args: list[str], timeout: int = 8) -> dict[str, str]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {"state": "unavailable", "detail": f"{args[0]} is not installed here."}
    except subprocess.TimeoutExpired:
        return {"state": "failed", "detail": f"{args[0]} timed out."}
    output = (result.stdout or result.stderr or "").strip()
    return {
        "state": "ok" if result.returncode == 0 else "failed",
        "detail": output[:500] if output else f"exit={result.returncode}",
    }


def _sanitize_ops_detail(detail: object) -> str:
    text = str(detail or "")
    for secret_value in (
        os.environ.get("META_ACCESS_TOKEN", ""),
        os.environ.get("META_APP_SECRET", ""),
        os.environ.get("DASHBOARD_PASSWORD", ""),
        os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    ):
        if secret_value:
            text = text.replace(secret_value, "<redacted>")
    return text[:500]


def _ops_log_path(root: Path) -> Path:
    return root / "logs" / "ops_actions.jsonl"


def _ops_incident_path(root: Path) -> Path:
    return root / "logs" / "ops_incidents.jsonl"


def _ops_report_path(root: Path) -> Path:
    return root / "logs" / "ops_reports.jsonl"


def _instagram_queue_history_path(root: Path) -> Path:
    return root / "logs" / "instagram_queue_history.jsonl"


def _write_ops_audit(root: Path, user: str, action: str, result: dict[str, str]) -> None:
    path = _ops_log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "user": user,
        "action": action,
        "result_state": str(result.get("state", "unknown")),
        "result_name": str(result.get("name", action)),
        "detail": _sanitize_ops_detail(result.get("detail", "")),
    }
    with path.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def _write_work_event(
    root: Path,
    event_type: str,
    summary: str,
    *,
    actor: str = "dashboard",
    command: str | None = None,
    result: str | None = None,
    next_action: str | None = None,
    files: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    try:
        write_work_activity(
            root,
            event_type,
            summary,
            actor=actor,
            command=command,
            files=files,
            result=result,
            next_action=next_action,
            metadata=metadata,
        )
    except Exception:
        # Work activity logging should never block the dashboard action itself.
        pass


def _recent_ops_audit(root: Path, limit: int = 8) -> list[dict[str, str]]:
    path = _ops_log_path(root)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines()[-limit:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append({
            "timestamp": str(item.get("timestamp", "")),
            "user": str(item.get("user", "")),
            "action": str(item.get("action", "")),
            "state": str(item.get("result_state", "unknown")),
            "name": str(item.get("result_name", "")),
            "detail": _sanitize_ops_detail(item.get("detail", "")),
        })
    return list(reversed(rows))


def _write_ops_incident(root: Path, user: str, title: str, severity: str, note: str) -> dict[str, str]:
    title = _sanitize_ops_detail(title).strip()[:120]
    note = _sanitize_ops_detail(note).strip()[:1000]
    severity = severity if severity in {"info", "warning", "critical"} else "info"
    if not title:
        raise ValueError("Incident title is required")
    if not note:
        raise ValueError("Incident note is required")

    path = _ops_incident_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    incident_id = hashlib.sha256(f"{timestamp}:{user}:{title}".encode()).hexdigest()[:12]
    record = {
        "id": incident_id,
        "timestamp": timestamp,
        "user": user,
        "title": title,
        "severity": severity,
        "status": "open",
        "note": note,
    }
    with path.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def _load_ops_incidents(root: Path) -> list[dict[str, str]]:
    path = _ops_incident_path(root)
    if not path.exists():
        return []
    rows = []
    for index, line in enumerate(path.read_text().splitlines()):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        incident_id = str(item.get("id") or hashlib.sha256(f"legacy:{index}:{line}".encode()).hexdigest()[:12])
        rows.append({
            "id": incident_id,
            "timestamp": str(item.get("timestamp", "")),
            "user": str(item.get("user", "")),
            "title": str(item.get("title", "")),
            "severity": str(item.get("severity", "info")),
            "status": str(item.get("status", "open")),
            "note": _sanitize_ops_detail(item.get("note", "")),
        })
    return rows


def _recent_ops_incidents(root: Path, limit: int = 6) -> list[dict[str, str]]:
    rows = _load_ops_incidents(root)[-limit:]
    return list(reversed(rows))


def _recent_ops_reports(root: Path, limit: int = 5) -> list[dict[str, str]]:
    path = _ops_report_path(root)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines()[-limit:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append({
            "timestamp": str(item.get("timestamp", "")),
            "title": _sanitize_ops_detail(item.get("title", "Slayhack weekly Ops report")),
            "line_count": str(item.get("line_count", "")),
            "report": _sanitize_ops_report_summary(item.get("report", "")),
        })
    return list(reversed(rows))


def _recent_instagram_queue_history(root: Path, limit: int = 5) -> list[dict[str, object]]:
    path = _instagram_queue_history_path(root)
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
            "state": "Failed" if int(item.get("failed") or 0) else "Missing" if int(item.get("retrying") or 0) else "Ready",
            "processed": int(item.get("processed") or 0),
            "published": int(item.get("published") or 0),
            "retrying": int(item.get("retrying") or 0),
            "failed": int(item.get("failed") or 0),
            "dry_run": bool(item.get("dry_run")),
            "jobs": item.get("jobs", []) if isinstance(item.get("jobs"), list) else [],
        })
    return list(reversed(rows))


def _track_queue_summary(root: Path) -> dict[str, object]:
    return summarize_track_queue(read_queue(root))


def _recent_track_queue_history(root: Path, limit: int = 5) -> list[dict[str, object]]:
    return recent_track_scheduler_history(root, limit=limit)


def _metric_value(perf: PostPerformance, name: str) -> int:
    value = getattr(perf, name)
    return int(value) if value is not None else 0


def _performance_bucket(perf: PostPerformance) -> PerformanceBucket:
    reach = _metric_value(perf, "reach")
    likes = _metric_value(perf, "likes")
    saves = _metric_value(perf, "saves")
    shares = _metric_value(perf, "shares")
    if reach >= 1000 or likes >= 100 or saves >= 20 or shares >= 10:
        return PerformanceBucket.SCALE
    if (perf.reach is not None and reach < 100) or (perf.likes is not None and likes < 10):
        return PerformanceBucket.REPAIR
    return PerformanceBucket.LESSON_LEARNED


def _performance_signal_state(bucket: PerformanceBucket) -> str:
    if bucket == PerformanceBucket.SCALE:
        return "Ready"
    if bucket == PerformanceBucket.REPAIR:
        return "Failed"
    return "Missing"


def _performance_signal_action(bucket: PerformanceBucket, job: ContentJob, perf: PostPerformance) -> str:
    if bucket == PerformanceBucket.SCALE:
        return "Scale this angle: reuse the hook, format, and platform timing in the next slate."
    if bucket == PerformanceBucket.REPAIR:
        return "Repair before repeating: adjust hook, creative, platform fit, or publish setup."
    return "Capture the lesson, then wait for another signal before scaling."


def _performance_metrics_text(perf: PostPerformance) -> str:
    parts = []
    for label, value in (
        ("reach", perf.reach),
        ("likes", perf.likes),
        ("saves", perf.saves),
        ("shares", perf.shares),
    ):
        if value is not None:
            parts.append(f"{label}={value}")
    return " ".join(parts) if parts else "metrics recorded"


def _latest_performance_signals(jobs, limit: int = 6) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    for job in jobs:
        for perf in job.performance:
            bucket = _performance_bucket(perf)
            recorded_at = perf.recorded_at or epoch
            if recorded_at.tzinfo is None:
                recorded_at = recorded_at.replace(tzinfo=timezone.utc)
            rows.append({
                "job_id": job.id,
                "page_name": job.pm.page_name,
                "platform": perf.platform,
                "bucket": bucket.value.replace("_", " "),
                "state": _performance_signal_state(bucket),
                "summary": f"{job.brief[:90]} - {_performance_metrics_text(perf)}",
                "next_action": _performance_signal_action(bucket, job, perf),
                "recorded_at": recorded_at.isoformat() if perf.recorded_at else "",
                "_recorded_at": recorded_at,
            })
    rows = sorted(rows, key=lambda item: item["_recorded_at"], reverse=True)
    for row in rows:
        row.pop("_recorded_at", None)
    return rows[:limit]


def _tracking_failure_rows(root: Path, limit: int = 8) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for run in recent_track_scheduler_history(root, limit=20):
        for job in run.get("jobs", []):
            if not isinstance(job, dict):
                continue
            state = str(job.get("state", ""))
            if state not in {"failed", "retrying"}:
                continue
            rows.append({
                "job_id": str(job.get("job_id", "")),
                "state": "Failed" if state == "failed" else "Missing",
                "status": state,
                "attempt": int(job.get("attempt") or 0),
                "timestamp": str(run.get("timestamp", "")),
                "detail": _sanitize_ops_detail(job.get("detail", "No tracker error detail recorded.")),
            })
            if len(rows) >= limit:
                return rows
    return rows


def _published_platform_names(job: ContentJob) -> list[str]:
    result = job.publish_result or {}
    if not isinstance(result, dict):
        return []
    return [
        str(platform)
        for platform, value in result.items()
        if isinstance(value, dict) and value.get("status") == "published"
    ]


def _handoff_platform_names(job: ContentJob) -> list[str]:
    result = job.publish_result or {}
    if not isinstance(result, dict):
        return []
    return [
        str(platform)
        for platform, value in result.items()
        if isinstance(value, dict) and value.get("status") in {"scheduled", "pending_queue", "retrying"}
    ]


def _tracking_readiness_rows(root: Path, jobs, limit: int = 10) -> list[dict[str, object]]:
    queue_entries = read_queue(root)
    queued_by_job: dict[str, list[dict]] = {}
    for entry in queue_entries:
        queued_by_job.setdefault(str(entry.get("job_id", "")), []).append(entry)
    rows: list[dict[str, object]] = []
    for job in jobs:
        queued = queued_by_job.get(job.id, [])
        published_platforms = _published_platform_names(job)
        handoff_platforms = _handoff_platform_names(job)
        if job.performance:
            state = "Ready"
            status = "learning ready"
            detail = f"{len(job.performance)} snapshot{'s' if len(job.performance) != 1 else ''} recorded."
            next_action = "Use this result in Daily Slate learning decisions."
        elif queued:
            state = "Missing"
            status = "queued"
            detail = f"{len(queued)} snapshot check{'s' if len(queued) != 1 else ''} queued."
            next_action = "Wait for the hourly tracker or use Check performance now after the due time."
        elif job.stage == "publish_done" and published_platforms:
            state = "Missing"
            status = "ready now"
            detail = f"Published on {', '.join(published_platforms)} with no metrics recorded yet."
            next_action = "Open the mission and use Check performance now."
        elif handoff_platforms:
            state = "Missing"
            status = "waiting publish"
            detail = f"Handoff exists for {', '.join(handoff_platforms)}; live publish is still separate."
            next_action = "Only after explicit live publish approval, watch for queued snapshots."
        else:
            continue
        rows.append({
            "job_id": job.id,
            "page_name": job.pm.page_name,
            "state": state,
            "status": status,
            "detail": detail,
            "next_action": next_action,
            "brief": job.brief[:90],
        })
    order = {"ready now": 0, "queued": 1, "waiting publish": 2, "learning ready": 3}
    return sorted(rows, key=lambda item: (order.get(str(item["status"]), 9), str(item["job_id"])), reverse=False)[:limit]


def _safe_console_action(row: dict[str, object]) -> dict[str, object]:
    method = str(row.get("action_method", "get"))
    status = str(row.get("status", ""))
    action_label = str(row.get("action_label", "Open"))
    risk_label = str(row.get("risk_label", ""))
    if status == "Scheduled handoff":
        return {
            "label": "Open locked live gate",
            "url": str(row.get("action_url", row.get("detail_url", "#"))),
            "method": "get",
            "enabled": True,
        }
    if action_label == "Run generation dry-run":
        action_label = "Run dry-run only"
    elif action_label == "Create publish job":
        action_label = "Create publish job (locked)"
    elif action_label == "Mark ready":
        action_label = "Mark ready for generation"
    if method in {"post", "get"}:
        return {
            "label": action_label,
            "url": str(row.get("action_url", row.get("detail_url", "#"))),
            "method": method,
            "enabled": True,
        }
    if "live publish" in risk_label:
        action_label = "Open locked live gate"
    return {
        "label": action_label if action_label != "Open" else "Open mission",
        "url": str(row.get("detail_url", "#")),
        "method": "get",
        "enabled": True,
    }


def _station_count_label(count: int) -> str:
    if count == 0:
        return "Clear"
    if count == 1:
        return "1 waiting"
    return f"{count} waiting"


CONSOLE_HISTORY_KEYWORDS = (
    "captain",
    "console",
    "mission",
    "generation",
    "dry-run",
    "publish",
    "tracking",
    "track",
    "approval",
    "handoff",
    "slate",
    "calendar",
    "package",
    "performance",
)

CONSOLE_HISTORY_STATIONS = (
    ("route-map", "Route Map", ("slate", "calendar", "route", "ticket")),
    ("shipyard", "Shipyard", ("generation", "dry-run", "nora", "video", "shipyard")),
    ("harbor-gate", "Harbor Gate", ("publish", "package", "approval", "handoff", "live")),
    ("captain-log", "Captain Log", ("tracking", "track", "performance", "learning", "smoke", "deploy")),
)


def _console_history_text(item: dict[str, object]) -> str:
    return " ".join(
        str(item.get(key, ""))
        for key in ("summary", "result", "next_action", "command", "event_type", "actor")
    ).lower()


def _console_history_station(item: dict[str, object]) -> dict[str, str]:
    haystack = _console_history_text(item)
    if "approval" in haystack or "handoff" in haystack or "live publish" in haystack:
        return {"key": "harbor-gate", "label": "Harbor Gate"}
    for key, label, keywords in CONSOLE_HISTORY_STATIONS:
        if any(keyword in haystack for keyword in keywords):
            return {"key": key, "label": label}
    return {"key": "captain-log", "label": "Captain Log"}


def _console_history_needs_captain(item: dict[str, object]) -> bool:
    haystack = _console_history_text(item)
    return str(item.get("event_type", "")) in {"blocker", "next_recommendation"} or any(
        phrase in haystack
        for phrase in (
            "captain",
            "approval",
            "handoff",
            "blocked",
            "failed",
            "live publish",
            "next action",
            "waiting",
            "needs",
        )
    )


def _console_history(
    root: Path,
    limit: int = 6,
    *,
    station: str = "all",
    actor: str = "all",
    mission: str = "",
    needs_captain: bool = False,
) -> dict[str, object]:
    valid_stations = {"all", *(key for key, _, _ in CONSOLE_HISTORY_STATIONS)}
    selected_station = station if station in valid_stations else "all"
    selected_actor = str(actor or "all").strip() or "all"
    mission_query = str(mission or "").strip()[:80].lower()
    relevant_rows: list[dict[str, object]] = []

    for item in read_recent_work_activity(root, limit=80):
        haystack = " ".join(
            str(item.get(key, ""))
            for key in ("summary", "result", "next_action", "command", "event_type")
        ).lower()
        if not any(keyword in haystack for keyword in CONSOLE_HISTORY_KEYWORDS):
            continue
        station_detail = _console_history_station(item)
        relevant_rows.append(
            {
                "timestamp": item.get("timestamp", ""),
                "actor": item.get("actor", ""),
                "event_type": str(item.get("event_type", "")).replace("_", " "),
                "summary": item.get("summary", ""),
                "result": item.get("result", ""),
                "station": station_detail["label"],
                "station_key": station_detail["key"],
                "needs_captain": _console_history_needs_captain(item),
                "search_text": _console_history_text(item),
            }
        )

    actor_options = sorted({str(row["actor"]) for row in relevant_rows if str(row.get("actor", "")).strip()})
    if selected_actor != "all" and selected_actor not in actor_options:
        selected_actor = "all"

    filtered_rows = []
    for row in relevant_rows:
        if selected_station != "all" and row["station_key"] != selected_station:
            continue
        if selected_actor != "all" and row["actor"] != selected_actor:
            continue
        if mission_query and mission_query not in str(row["search_text"]):
            continue
        if needs_captain and not row["needs_captain"]:
            continue
        clean_row = dict(row)
        clean_row.pop("search_text", None)
        filtered_rows.append(clean_row)

    return {
        "rows": filtered_rows[:limit],
        "total_count": len(relevant_rows),
        "filtered_count": len(filtered_rows),
        "filters": {
            "station": selected_station,
            "actor": selected_actor,
            "mission": mission_query,
            "needs_captain": needs_captain,
        },
        "station_options": [{"key": "all", "label": "All stations"}]
        + [{"key": key, "label": label} for key, label, _ in CONSOLE_HISTORY_STATIONS],
        "actor_options": actor_options,
    }


def _captain_action_console(root: Path, jobs) -> list[dict[str, object]]:
    slate_cards = _daily_slate_cards(root)
    approval_rows = _approval_queue_rows(root)
    tracking_rows = _tracking_readiness_rows(root, jobs, limit=6)
    actions: list[dict[str, object]] = []
    route_count = sum(
        1
        for card in slate_cards
        for ticket in card.get("tickets", [])
        if isinstance(ticket, dict) and not ticket.get("has_mission")
    )
    shipyard_rows = [
        row
        for row in approval_rows
        if row.get("lane_key") in {"nora", "generation"}
        and row.get("action_method") in {"post", "get", "generation_result"}
    ]
    harbor_rows = [
        row
        for row in approval_rows
        if row.get("lane_key") in {"packaging", "captain", "handoff", "revision"}
    ]
    tracking_count = sum(1 for row in tracking_rows if row.get("status") != "learning ready")

    next_ticket = next(
        (
            (card, card.get("next_ticket"))
            for card in slate_cards
            if isinstance(card.get("next_ticket"), dict) and not card["next_ticket"].get("has_mission")
        ),
        None,
    )
    if next_ticket:
        card, ticket = next_ticket
        actions.append(
            {
                "station": "Route Map",
                "station_key": "route-map",
                "state": "missing",
                "risk_label": "safe mission create",
                "count": route_count,
                "count_label": _station_count_label(route_count),
                "urgency": "Needs route" if route_count else "Clear",
                "title": f"{card['page_name']} next course",
                "detail": (
                    f"{ticket.get('title')} - {ticket.get('owner')} owns - "
                    f"{ticket.get('decision_owner')} decides"
                ),
                "action": {
                    "label": "Create safe mission",
                    "url": str(ticket.get("create_mission_url")),
                    "method": "post",
                    "enabled": True,
                },
                "secondary_label": "Open slate",
                "secondary_url": f"/aurora/daily-slate?project={card['project']}",
            }
        )
    else:
        actions.append(
            {
                "station": "Route Map",
                "station_key": "route-map",
                "state": "ready",
                "risk_label": "read only",
                "count": route_count,
                "count_label": _station_count_label(route_count),
                "urgency": "Clear",
                "title": "Daily Slate",
                "detail": "No unlaunched slate tickets are waiting at the top of the route map.",
                "action": {"label": "Open Daily Slate", "url": "/aurora/daily-slate", "method": "get", "enabled": True},
                "secondary_label": "",
                "secondary_url": "",
            }
        )

    shipyard_row = next(iter(shipyard_rows), None)
    if shipyard_row:
        actions.append(
            {
                "station": "Shipyard",
                "station_key": "shipyard",
                "state": str(shipyard_row.get("state", "missing")),
                "risk_label": str(shipyard_row.get("risk_label", "review gate")),
                "count": len(shipyard_rows),
                "count_label": _station_count_label(len(shipyard_rows)),
                "urgency": "Generation waiting",
                "title": str(shipyard_row.get("status")),
                "detail": f"{shipyard_row.get('page_name')} - {shipyard_row.get('next_action')}",
                "action": _safe_console_action(shipyard_row),
                "secondary_label": "Open mission",
                "secondary_url": str(shipyard_row.get("detail_url", "")),
            }
        )
    else:
        actions.append(
            {
                "station": "Shipyard",
                "station_key": "shipyard",
                "state": "ready",
                "risk_label": "read only",
                "count": len(shipyard_rows),
                "count_label": _station_count_label(len(shipyard_rows)),
                "urgency": "Clear",
                "title": "Generation clear",
                "detail": "No generation package is waiting for Nora, dry-run, or manual video intake.",
                "action": {"label": "Open Shipyard", "url": "/aurora/generation", "method": "get", "enabled": True},
                "secondary_label": "",
                "secondary_url": "",
            }
        )

    harbor_row = next(iter(harbor_rows), None)
    if harbor_row:
        actions.append(
            {
                "station": "Harbor Gate",
                "station_key": "harbor-gate",
                "state": str(harbor_row.get("state", "missing")),
                "risk_label": (
                    "live publish locked"
                    if harbor_row.get("status") == "Scheduled handoff"
                    else str(harbor_row.get("risk_label", "locked live publish"))
                ),
                "count": len(harbor_rows),
                "count_label": _station_count_label(len(harbor_rows)),
                "urgency": "Gate waiting",
                "title": str(harbor_row.get("status")),
                "detail": f"{harbor_row.get('page_name')} - {harbor_row.get('next_action')}",
                "action": _safe_console_action(harbor_row),
                "secondary_label": "Open mission",
                "secondary_url": str(harbor_row.get("detail_url", "")),
            }
        )
    else:
        actions.append(
            {
                "station": "Harbor Gate",
                "station_key": "harbor-gate",
                "state": "ready",
                "risk_label": "live publish locked",
                "count": len(harbor_rows),
                "count_label": _station_count_label(len(harbor_rows)),
                "urgency": "Clear",
                "title": "No package at gate",
                "detail": "No Roxy/Emma package, Captain approval, or handoff is waiting right now.",
                "action": {"label": "Open Approval Queue", "url": "/aurora/approval-queue", "method": "get", "enabled": True},
                "secondary_label": "",
                "secondary_url": "",
            }
        )

    tracking_row = next(iter(tracking_rows), None)
    if tracking_row:
        is_ready_now = tracking_row.get("status") == "ready now"
        actions.append(
            {
                "station": "Captain Log",
                "station_key": "captain-log",
                "state": str(tracking_row.get("state", "missing")).lower(),
                "risk_label": str(tracking_row.get("status", "tracking")),
                "count": tracking_count,
                "count_label": _station_count_label(tracking_count),
                "urgency": "Tracking waiting" if tracking_count else "Learning ready",
                "title": f"{tracking_row.get('page_name')} tracking",
                "detail": str(tracking_row.get("detail")),
                "action": {
                    "label": "Check performance now" if is_ready_now else "Open tracking proof",
                    "url": f"/jobs/{tracking_row.get('job_id')}/track-now" if is_ready_now else f"/jobs/{tracking_row.get('job_id')}",
                    "method": "post" if is_ready_now else "get",
                    "enabled": True,
                },
                "secondary_label": "Open Ops",
                "secondary_url": "/ops",
            }
        )
    else:
        actions.append(
            {
                "station": "Captain Log",
                "station_key": "captain-log",
                "state": "ready",
                "risk_label": "read only",
                "count": tracking_count,
                "count_label": _station_count_label(tracking_count),
                "urgency": "Clear",
                "title": "Learning clear",
                "detail": "No published mission is waiting for tracking proof right now.",
                "action": {"label": "Open Learning", "url": "/aurora/learning", "method": "get", "enabled": True},
                "secondary_label": "",
                "secondary_url": "",
            }
        )

    return actions


def _sanitize_ops_report_summary(report: object) -> str:
    lines = []
    for line in _sanitize_ops_detail(report).splitlines():
        if line.startswith("recent_failed_jobs="):
            continue
        lines.append(line)
    return "\n".join(lines[:6])


def _incident_summary(root: Path) -> dict[str, int]:
    rows = _load_ops_incidents(root)
    return {
        "open": sum(row["status"] == "open" for row in rows),
        "investigating": sum(row["status"] == "investigating" for row in rows),
        "resolved": sum(row["status"] == "resolved" for row in rows),
    }


def _update_ops_incident_status(root: Path, incident_id: str, status: str, user: str) -> dict[str, str]:
    if status not in {"open", "investigating", "resolved"}:
        raise ValueError("Invalid incident status")
    path = _ops_incident_path(root)
    rows = _load_ops_incidents(root)
    found = None
    for row in rows:
        if row["id"] == incident_id:
            row["status"] = status
            row["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            row["updated_by"] = user
            found = row
            break
    if found is None:
        raise ValueError("Incident not found")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    return found


def _ops_log_status(root: Path) -> dict[str, object]:
    path = _ops_log_path(root)
    archive_dir = root / "logs" / "archive"
    if not path.exists():
        return {
            "state": "Missing",
            "detail": "ops_actions.jsonl not created yet",
            "size_bytes": 0,
            "line_count": 0,
            "archive_count": len(list(archive_dir.glob("ops_actions-*.jsonl"))) if archive_dir.exists() else 0,
        }
    try:
        line_count = len(path.read_text().splitlines())
        archive_count = len(list(archive_dir.glob("ops_actions-*.jsonl"))) if archive_dir.exists() else 0
        size = path.stat().st_size
    except OSError as exc:
        return {"state": "Failed", "detail": str(exc), "size_bytes": 0, "line_count": 0, "archive_count": 0}
    size_kb = size / 1024
    return {
        "state": "Ready",
        "detail": f"{line_count} entries - {size_kb:.1f} KB - {archive_count} archives",
        "size_bytes": size,
        "line_count": line_count,
        "archive_count": archive_count,
    }


def _job_state_write_health(root: Path, limit: int = 8) -> dict[str, object]:
    output_root = root / "output"
    if not output_root.exists():
        return {
            "state": "Ready",
            "detail": "No output directory yet.",
            "attention_count": 0,
            "scanned": 0,
            "rows": [],
        }

    rows: list[dict[str, str]] = []
    attention_count = 0
    scanned = 0
    try:
        job_paths = sorted(output_root.rglob("job.json"))
    except OSError as exc:
        return {
            "state": "Failed",
            "detail": f"Cannot scan output job state: {exc}",
            "attention_count": 1,
            "scanned": 0,
            "rows": [],
        }

    for path in job_paths:
        scanned += 1
        issues = []
        try:
            if not os.access(path, os.W_OK):
                issues.append("job.json not writable")
            if not os.access(path.parent, os.W_OK):
                issues.append("job folder not writable")
        except OSError as exc:
            issues.append(str(exc))
        if not issues:
            continue
        attention_count += 1
        if len(rows) < limit:
            rows.append({
                "state": "Failed",
                "name": str(path.relative_to(root)),
                "detail": ", ".join(issues),
            })

    if attention_count:
        return {
            "state": "Failed",
            "detail": f"{attention_count} job state files need ownership attention; scanned {scanned}.",
            "attention_count": attention_count,
            "scanned": scanned,
            "rows": rows,
        }
    return {
        "state": "Ready",
        "detail": f"{scanned} job state files writable.",
        "attention_count": 0,
        "scanned": scanned,
        "rows": [],
    }


def _systemctl_args(verb: str, unit: str) -> list[str]:
    return ["sudo", "-n", "systemctl", verb, unit]


def _ops_action_buttons() -> list[dict[str, str]]:
    return [
        {"key": key, "label": str(config["label"])}
        for key, config in OPS_ACTIONS.items()
    ]


def _run_ops_action(action: str) -> dict[str, str]:
    config = OPS_ACTIONS.get(action)
    if config is None:
        return {"name": action, "state": "Failed", "detail": "Unknown Ops action."}

    label = str(config["label"])
    unit = str(config["unit"])
    verb = str(config["verb"])

    if config.get("delayed"):
        code = (
            "import subprocess,time;"
            "time.sleep(1);"
            f"subprocess.run({json.dumps(_systemctl_args(verb, unit))})"
        )
        try:
            subprocess.Popen([sys.executable, "-c", code], cwd=str(_ROOT))
        except Exception as exc:  # noqa: BLE001
            return {"name": label, "state": "Failed", "detail": str(exc)[:300]}
        return {"name": label, "state": "Ready", "detail": f"Queued {verb} for {unit}."}

    result = _run_command(_systemctl_args(verb, unit), timeout=30)
    state = "Ready" if result["state"] == "ok" else "Failed"
    detail = result["detail"]
    if result["state"] == "failed" and "password" in detail.lower():
        detail = "sudo permission missing for this Ops action."
    return {"name": label, "state": state, "detail": detail}


def _ops_unit_status() -> list[dict[str, str]]:
    rows = []
    for unit in OPS_UNITS:
        result = _run_command(["systemctl", "is-active", unit], timeout=4)
        active = result["state"] == "ok" and result["detail"] == "active"
        rows.append({
            "name": unit,
            "state": "Ready" if active else "Missing" if result["state"] == "unavailable" else "Failed",
            "detail": result["detail"],
        })
    return rows


def _latest_backup_status() -> dict[str, str]:
    backup_root = Path(os.environ.get("BACKUP_ROOT", "/opt/nayzfreedom-backups"))
    if not backup_root.exists():
        return {"state": "Missing", "detail": f"{backup_root} not found"}
    try:
        backups = sorted([path for path in backup_root.iterdir() if path.is_dir()], reverse=True)
    except PermissionError:
        return {"state": "Failed", "detail": f"Permission denied: {backup_root}"}
    if not backups:
        return {"state": "Missing", "detail": "No backup folders found."}
    latest = backups[0]
    archive = latest / "state.tgz"
    checksum = latest / "state.tgz.sha256"
    if archive.exists() and checksum.exists():
        size_mb = archive.stat().st_size / (1024 * 1024)
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
        state = "Ready" if age <= timedelta(hours=36) else "Missing"
        return {"state": state, "detail": f"{latest.name} - {size_mb:.1f} MB - age {int(age.total_seconds() // 3600)}h"}
    return {"state": "Failed", "detail": f"{latest.name} is missing archive or checksum."}


def _backup_history(limit: int = 5) -> list[dict[str, str]]:
    backup_root = Path(os.environ.get("BACKUP_ROOT", "/opt/nayzfreedom-backups"))
    if not backup_root.exists():
        return []
    try:
        backups = sorted([path for path in backup_root.iterdir() if path.is_dir()], reverse=True)[:limit]
    except PermissionError:
        return [{"state": "Failed", "name": "Backup history", "detail": f"Permission denied: {backup_root}"}]
    rows = []
    now = datetime.now(timezone.utc)
    for path in backups:
        archive = path / "state.tgz"
        checksum = path / "state.tgz.sha256"
        age = now - datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if archive.exists() and checksum.exists():
            size_mb = archive.stat().st_size / (1024 * 1024)
            state = "Ready" if age <= timedelta(hours=36) else "Missing"
            detail = f"{size_mb:.1f} MB - age {int(age.total_seconds() // 3600)}h"
        else:
            state = "Failed"
            detail = "missing archive or checksum"
        rows.append({"state": state, "name": path.name, "detail": detail})
    return rows


def _restore_smoke_history(root: Path, limit: int = 5) -> list[dict[str, str]]:
    path = root / "logs" / "restore_smoke.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines()[-limit:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append({
            "state": str(item.get("state", "Missing")),
            "name": str(item.get("archive", "restore smoke")),
            "detail": str(item.get("timestamp", "")),
        })
    return list(reversed(rows))


def _system_resources(root: Path) -> list[dict[str, str]]:
    usage = shutil.disk_usage(root)
    disk_percent = int((usage.used / usage.total) * 100) if usage.total else 0
    rows = [{
        "state": "Failed" if disk_percent >= 85 else "Missing" if disk_percent >= 75 else "Ready",
        "name": "Disk",
        "detail": f"{disk_percent}% used at {root}",
    }]
    try:
        load_1, load_5, load_15 = os.getloadavg()
        rows.append({
            "state": "Ready",
            "name": "Load average",
            "detail": f"{load_1:.2f} / {load_5:.2f} / {load_15:.2f}",
        })
    except OSError:
        rows.append({"state": "Missing", "name": "Load average", "detail": "Not available on this host."})

    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        values: dict[str, int] = {}
        for line in meminfo.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].rstrip(":") in {"MemTotal", "MemAvailable"}:
                values[parts[0].rstrip(":")] = int(parts[1])
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", 0)
        used_percent = int(((total - available) / total) * 100) if total else 0
        rows.append({
            "state": "Failed" if used_percent >= 90 else "Missing" if used_percent >= 80 else "Ready",
            "name": "Memory",
            "detail": f"{used_percent}% used",
        })
    else:
        rows.append({"state": "Missing", "name": "Memory", "detail": "Linux meminfo not available here."})
    return rows


def _service_event_history(limit: int = 8) -> list[dict[str, str]]:
    units = [
        "nayzfreedom-dashboard.service",
        "nayzfreedom-bot.service",
        "nayzfreedom-instagram-queue.service",
        "nayzfreedom-healthcheck.service",
    ]
    events = []
    for unit in units:
        result = _run_command(["journalctl", "-u", unit, "--since", "24 hours ago", "-n", "20", "--no-pager"], timeout=6)
        if result["state"] != "ok":
            continue
        for line in result["detail"].splitlines():
            if any(marker in line for marker in ("Started ", "Stopped ", "Failed ", "Traceback", "ERROR", "CRITICAL")):
                state = "Failed" if any(marker in line for marker in ("Failed ", "Traceback", "ERROR", "CRITICAL")) else "Ready"
                events.append({"state": state, "name": unit, "detail": _sanitize_ops_detail(line)})
    return list(reversed(events[-limit:]))


def _ops_publish_errors(jobs, limit: int = 6) -> list[dict[str, str]]:
    rows = []
    for job in jobs:
        for platform, value in (job.publish_result or {}).items():
            if not isinstance(value, dict) or value.get("status") != "failed":
                continue
            error = str(value.get("error") or value.get("reason") or "failed")
            meta_token = os.environ.get("META_ACCESS_TOKEN", "")
            if meta_token:
                error = error.replace(meta_token, "<redacted>")
            rows.append({
                "job_id": job.id,
                "platform": str(platform),
                "detail": error[:220],
            })
    return rows[:limit]


def _publish_failure_category(platform: str, error: str) -> str:
    text = f"{platform} {error}".lower()
    if "media file not found" in text or "no media file" in text or "video_path is none" in text:
        return "media missing"
    if "access token" in text or "token" in text or "oauth" in text or "permission" in text or "unauthorized" in text:
        return "auth or permission"
    if "quota" in text or "rate limit" in text or "too many requests" in text:
        return "quota or rate limit"
    if "400 client error" in text or "bad request" in text or "graph.facebook.com" in text:
        return "meta bad request"
    return "unknown"


def _content_type_value(job) -> str:
    return str(getattr(job.content_type, "value", job.content_type) or "unknown")


def _media_readiness(root: Path, job) -> dict[str, str]:
    content_type = _content_type_value(job)
    if content_type == "article":
        return {
            "state": "Ready",
            "label": "Media not required",
            "detail": "Facebook feed article uses message-only payload.",
        }
    media_field = "video_path" if content_type == "video" else "image_path"
    media = getattr(job, media_field, None)
    if not media:
        return {
            "state": "Failed",
            "label": "Media missing",
            "detail": f"{media_field} is empty for {content_type}.",
        }
    media_path = Path(str(media))
    resolved = media_path if media_path.is_absolute() else root / media_path
    if not resolved.exists():
        return {
            "state": "Failed",
            "label": "Media file missing",
            "detail": str(media)[:180],
        }
    size = resolved.stat().st_size
    if size <= 0:
        return {
            "state": "Failed",
            "label": "Media empty",
            "detail": str(media)[:180],
        }
    return {
        "state": "Ready",
        "label": "Media ready",
        "detail": f"{size / 1024 / 1024:.1f} MB - {str(media)[:150]}",
    }


def _public_media_path(root: Path, job_id: str, filename: str) -> Path:
    safe_name = Path(filename).name
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov"}
    if Path(safe_name).suffix.lower() not in allowed:
        raise FileNotFoundError("unsupported public media type")
    output_root = (root / "output").resolve()
    for path in output_root.rglob(safe_name):
        if path.parent.name != job_id:
            continue
        resolved = path.resolve()
        if output_root in resolved.parents:
            return resolved
    raise FileNotFoundError(f"public media not found for {job_id}/{safe_name}")


def _public_media_url(job) -> str:
    media = job.video_path if _content_type_value(job) == "video" else job.image_path
    if not media:
        return ""
    return f"{OPS_PUBLIC_BASE_URL}/media/public/{quote(job.id)}/{quote(Path(str(media)).name)}"


def _public_url_readiness(root: Path, job, media: dict[str, str]) -> dict[str, str]:
    content_type = _content_type_value(job)
    if content_type == "article":
        return {
            "state": "Ready",
            "label": "Public URL not required",
            "detail": "Article feed posts do not upload media.",
        }
    if media["state"] != "Ready":
        return {
            "state": "Failed",
            "label": "Public URL blocked",
            "detail": "Fix local media before exposing public URL.",
        }
    url = _public_media_url(job)
    if not url:
        return {
            "state": "Missing",
            "label": "Public URL missing",
            "detail": "OPS_PUBLIC_BASE_URL is not configured.",
        }
    return {"state": "Ready", "label": "Public URL ready", "detail": url}


def _failed_publish_platforms(job) -> list[str]:
    result = job.publish_result or {}
    if not isinstance(result, dict):
        return []
    return [
        str(platform)
        for platform, value in result.items()
        if isinstance(value, dict) and value.get("status") == "failed"
    ]


def _caption_readiness(job) -> dict[str, str]:
    strategy = job.growth_strategy
    caption = getattr(strategy, "caption", "") if strategy else ""
    best_time = getattr(strategy, "best_post_time_utc", "") if strategy else ""
    if not str(caption).strip():
        return {
            "state": "Failed",
            "label": "Caption missing",
            "detail": "growth_strategy.caption is empty.",
        }
    detail = f"{len(str(caption).strip())} chars"
    if best_time:
        detail = f"{detail} - best time {best_time}"
    return {"state": "Ready", "label": "Caption ready", "detail": detail}


def _retry_recommendation(
    job,
    platform: str,
    category: str,
    media: dict[str, str],
    caption: dict[str, str],
    public_url: dict[str, str],
) -> str:
    content_type = _content_type_value(job)
    if media["state"] != "Ready":
        return "Fix media path before retry."
    if caption["state"] != "Ready":
        return "Add caption before retry."
    if platform == "instagram" and content_type != "video" and public_url["state"] != "Ready":
        return "Public image URL is required before IG image_url fallback can work."
    if platform == "instagram" and content_type != "video" and category == "meta bad request":
        return "Payload is locally ready; retry can use public image_url fallback if source upload is rejected."
    if platform == "facebook" and content_type == "article" and category == "meta bad request":
        return "Payload is locally ready; inspect Meta body, page permission, or scheduled feed constraints."
    if category == "auth or permission":
        return "Check token scope, page role, and connected account before retry."
    return "Payload is locally ready; retry only after checking external API cause."


def _ops_publish_failure_triage(root: Path, jobs, limit: int = 12) -> dict[str, object]:
    rows: list[dict[str, str]] = []
    groups: dict[str, dict[str, object]] = {}
    safe_instagram_retry_rows: list[dict[str, str]] = []
    for job in jobs:
        result = job.publish_result or {}
        if not isinstance(result, dict):
            continue
        for platform, value in result.items():
            if not isinstance(value, dict) or value.get("status") != "failed":
                continue
            error = _sanitize_ops_detail(value.get("error") or value.get("reason") or "failed")
            meta_error = value.get("meta_error") if isinstance(value.get("meta_error"), dict) else {}
            meta_error_detail = ""
            if meta_error:
                meta_error_detail = " ".join(
                    f"{key}={_sanitize_ops_detail(meta_error.get(key))}"
                    for key in ("code", "error_subcode", "type", "message")
                    if meta_error.get(key) not in (None, "")
                )
            category = _publish_failure_category(str(platform), error)
            media = _media_readiness(root, job)
            caption = _caption_readiness(job)
            public_url = _public_url_readiness(root, job, media)
            key = f"{platform}:{category}"
            group = groups.setdefault(
                key,
                {
                    "platform": str(platform),
                    "category": category,
                    "count": 0,
                    "state": "Failed",
                    "sample": error[:160],
                },
            )
            group["count"] = int(group["count"]) + 1
            row = {
                "job_id": job.id,
                "platform": str(platform),
                "category": category,
                "detail": error[:240],
                "meta_error": meta_error_detail[:300],
                "media": media,
                "caption": caption,
                "public_url": public_url,
                "recommendation": _retry_recommendation(job, str(platform), category, media, caption, public_url),
                "retry_path": f"/ops/publish-failures/{job.id}/{platform}/retry",
            }
            rows.append(row)
            if (
                str(platform) == "instagram"
                and media["state"] == "Ready"
                and caption["state"] == "Ready"
                and public_url["state"] == "Ready"
            ):
                safe_instagram_retry_rows.append(row)
    sorted_groups = sorted(
        groups.values(),
        key=lambda item: (str(item["platform"]), str(item["category"])),
    )
    return {
        "rows": rows[:limit],
        "groups": sorted_groups,
        "safe_instagram_retry_rows": safe_instagram_retry_rows,
        "safe_instagram_retry_count": len(safe_instagram_retry_rows),
    }


def _ops_now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ops_time(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text), tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _instagram_due_time(instagram: dict[str, object]) -> datetime | None:
    if instagram.get("status") == "retrying":
        return _parse_ops_time(instagram.get("next_retry_unix")) or _parse_ops_time(instagram.get("next_retry_at"))
    return _parse_ops_time(instagram.get("scheduled_publish_time")) or _parse_ops_time(instagram.get("due_at"))


def _ops_time_distance(due_at: datetime | None, now: datetime) -> str:
    if due_at is None:
        return "due time unknown"
    seconds = int((due_at - now).total_seconds())
    magnitude = abs(seconds)
    if magnitude < 60:
        return "due now" if seconds <= 0 else "in less than 1m"
    minutes = magnitude // 60
    if minutes < 60:
        label = f"{minutes}m"
    else:
        hours = minutes // 60
        remaining_minutes = minutes % 60
        label = f"{hours}h" if not remaining_minutes else f"{hours}h {remaining_minutes}m"
    return f"in {label}" if seconds > 0 else f"{label} overdue"


def _caption_preview(job) -> str:
    growth = getattr(job, "growth_strategy", None)
    caption = getattr(growth, "caption", "") if growth else ""
    if not caption and isinstance(growth, dict):
        caption = str(growth.get("caption", ""))
    if not caption:
        bella = getattr(job, "bella_output", None)
        caption = getattr(bella, "caption", "") if bella else ""
    return _sanitize_ops_detail(caption or job.brief)[:140]


def _ops_publish_summary(jobs) -> dict[str, object]:
    counts = {
        "facebook_scheduled": 0,
        "instagram_pending": 0,
        "instagram_due_now": 0,
        "instagram_future": 0,
        "instagram_stale": 0,
        "instagram_retrying": 0,
        "instagram_failed": 0,
        "instagram_published": 0,
    }
    queue_rows = []
    now = _ops_now_utc()
    stale_after = timedelta(minutes=15)
    for job in jobs:
        result = job.publish_result or {}
        facebook = result.get("facebook") if isinstance(result, dict) else None
        instagram = result.get("instagram") if isinstance(result, dict) else None
        if isinstance(facebook, dict) and facebook.get("status") == "scheduled":
            counts["facebook_scheduled"] += 1
        if not isinstance(instagram, dict):
            continue
        status = str(instagram.get("status", "unknown"))
        if status == "pending_queue":
            counts["instagram_pending"] += 1
            due_at_dt = _instagram_due_time(instagram)
            if due_at_dt and now - due_at_dt > stale_after:
                row_status = "stale"
                row_state = "Failed"
                counts["instagram_stale"] += 1
            elif due_at_dt and due_at_dt <= now:
                row_status = "due now"
                row_state = "Missing"
                counts["instagram_due_now"] += 1
            else:
                row_status = "future"
                row_state = "Ready"
                counts["instagram_future"] += 1
        elif status == "retrying":
            counts["instagram_retrying"] += 1
            due_at_dt = _instagram_due_time(instagram)
            row_status = "retrying"
            row_state = "Missing"
        elif status == "failed":
            counts["instagram_failed"] += 1
            due_at_dt = _instagram_due_time(instagram)
            row_status = "failed"
            row_state = "Failed"
        elif status == "published":
            counts["instagram_published"] += 1
            due_at_dt = _instagram_due_time(instagram) or _parse_ops_time(instagram.get("published_at"))
            row_status = "published"
            row_state = "Ready"
        else:
            continue
        if status in {"pending_queue", "retrying", "failed", "published"}:
            due_at_text = due_at_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if due_at_dt else ""
            retry_count = int(instagram.get("retry_count") or 0)
            queue_rows.append({
                "job_id": job.id,
                "status": row_status,
                "raw_status": status,
                "state": row_state,
                "due_at": due_at_text,
                "time_remaining": _ops_time_distance(due_at_dt, now),
                "retry_count": retry_count,
                "caption": _caption_preview(job),
                "detail": _sanitize_ops_detail(instagram.get("error") or instagram.get("reason") or ""),
            })
    order = {"failed": 0, "stale": 1, "due now": 2, "retrying": 3, "future": 4, "published": 5}
    queue_rows = sorted(queue_rows, key=lambda item: (order.get(str(item["status"]), 9), str(item.get("due_at") or "")))
    return {"counts": counts, "queue": queue_rows[:12]}


def _workflow_owner_summary(jobs) -> list[dict[str, str]]:
    rows = []
    for job in jobs[:8]:
        voyage_steps = _build_voyage_steps(job)
        command = _mission_command(job, voyage_steps, sum(1 for item in voyage_steps if item["state"] == "done"))
        badge_state = "Failed" if command["state"] == "Needs Captain" else "Missing" if command["state"] == "In Motion" else "Ready"
        rows.append({
            "job_id": job.id,
            "state": badge_state,
            "owner": command["owner"],
            "stage": command["stage_label"],
            "detail": job.brief[:120],
        })
    return rows


def _security_hygiene_checks(root: Path) -> list[dict[str, str]]:
    gitignore = root / ".gitignore"
    gitignore_text = gitignore.read_text() if gitignore.exists() else ""
    env_ignored = any(line.strip() in {".env", ".env.*"} for line in gitignore_text.splitlines())
    return [
        {
            "state": "Ready" if (root / ".env").exists() else "Missing",
            "name": "Production secrets",
            "detail": ".env exists locally on this host." if (root / ".env").exists() else ".env is not present on this host.",
        },
        {
            "state": "Ready" if env_ignored else "Failed",
            "name": "Git ignore",
            "detail": ".env patterns are ignored." if env_ignored else ".env ignore rule is missing.",
        },
        {
            "state": "Ready",
            "name": "Token hygiene",
            "detail": "Keep GitHub, Meta, Google, and Telegram token rotation in the external runbook.",
        },
    ]


def _ops_daily_summary(
    jobs,
    units: list[dict[str, str]],
    backup: dict[str, str],
    incident_summary: dict[str, int],
    publish_summary: dict[str, object],
    track_summary: dict[str, object],
    ops_reports: list[dict[str, str]],
) -> list[dict[str, str]]:
    summary = summarize_jobs(jobs)
    unit_failures = sum(item["state"] != "Ready" for item in units)
    publish_counts = publish_summary["counts"]
    track_counts = track_summary["counts"]
    ig_attention = publish_counts["instagram_failed"] + publish_counts["instagram_retrying"]
    track_attention = track_counts["overdue"] + track_counts["invalid"]
    if summary["failed"] or incident_summary["open"] or unit_failures or backup["state"] == "Failed" or publish_counts["instagram_failed"] or track_attention:
        state = "Failed"
        action = "Review failed missions, open incidents, service state, publish failures, or overdue tracking."
    elif backup["state"] != "Ready" or publish_counts["instagram_retrying"] or track_counts["retrying"] or track_counts["due_now"]:
        state = "Missing"
        action = "Check stale backup, queued Instagram retry, or due tracking before launching more work."
    else:
        state = "Ready"
        action = "Production is clear for the next mission."
    latest_report = ops_reports[0]["timestamp"] if ops_reports else "none"
    return [
        {"state": state, "name": "Ops state", "detail": action},
        {
            "state": "Failed" if summary["failed"] or incident_summary["open"] else "Ready",
            "name": "Mission attention",
            "detail": f"{summary['failed']} failed jobs - {incident_summary['open']} open incidents",
        },
        {
            "state": "Failed" if ig_attention else "Ready",
            "name": "Publish queue",
            "detail": f"IG pending={publish_counts['instagram_pending']} retrying={publish_counts['instagram_retrying']} failed={publish_counts['instagram_failed']}",
        },
        {
            "state": "Failed" if track_attention else "Missing" if track_counts["due_now"] or track_counts["retrying"] else "Ready",
            "name": "Tracking queue",
            "detail": f"queued={track_counts['total']} due={track_counts['due_now']} overdue={track_counts['overdue']} retrying={track_counts['retrying']}",
        },
        {"state": str(backup["state"]), "name": "Backup", "detail": str(backup["detail"])},
        {"state": "Ready" if latest_report != "none" else "Missing", "name": "Latest Ops report", "detail": latest_report},
    ]


def _signed_request_for_smoke() -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"user_id": "ops-smoke"}).encode()).decode().rstrip("=")
    app_secret = os.environ.get("META_APP_SECRET", "")
    if not app_secret:
        return f"unused.{payload}"
    sig = hmac.new(app_secret.encode("utf-8"), msg=payload.encode("utf-8"), digestmod=hashlib.sha256).digest()
    encoded_sig = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{encoded_sig}.{payload}"


def _http_smoke(name: str, method: str, url: str, **kwargs) -> dict[str, str]:
    try:
        response = requests.request(method, url, timeout=8, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "state": "Failed", "detail": str(exc)[:240]}
    ok = 200 <= response.status_code < 300
    detail = f"HTTP {response.status_code}"
    if name == "Data deletion callback" and ok:
        try:
            detail = f"confirmation={response.json().get('confirmation_code', 'missing')}"
        except ValueError:
            detail = "JSON parse failed"
            ok = False
    return {"name": name, "state": "Ready" if ok else "Failed", "detail": detail}


def _ops_smoke_results(root: Path) -> list[dict[str, str]]:
    signed_request = _signed_request_for_smoke()
    results = [
        _http_smoke("Health URL", "GET", f"{OPS_PUBLIC_BASE_URL}/healthz"),
        _http_smoke("Privacy HEAD", "HEAD", f"{OPS_PUBLIC_BASE_URL}/privacy"),
        _http_smoke("Data deletion HTML", "GET", f"{OPS_PUBLIC_BASE_URL}/data_deletion.html"),
        _http_smoke(
            "Data deletion callback",
            "POST",
            f"{OPS_PUBLIC_BASE_URL}/data-deletion-callback",
            data={"signed_request": signed_request},
        ),
    ]
    restore_script = root / "deploy" / "restore_smoke.sh"
    if restore_script.exists():
        restore = _run_command([str(restore_script)], timeout=20)
        results.append({
            "name": "Backup restore smoke",
            "state": "Ready" if restore["state"] == "ok" else "Failed",
            "detail": restore["detail"],
        })
    else:
        results.append({"name": "Backup restore smoke", "state": "Missing", "detail": "restore_smoke.sh not found"})
    return results


def _ops_snapshot(root: Path, smoke_results: list[dict[str, str]] | None = None) -> dict[str, object]:
    jobs = list_all_jobs(root)
    summary = summarize_jobs(jobs)
    units = _ops_unit_status()
    backup = _latest_backup_status()
    incident_summary = _incident_summary(root)
    ops_reports = _recent_ops_reports(root)
    publish_summary = _ops_publish_summary(jobs)
    track_summary = _track_queue_summary(root)
    job_state_health = _job_state_write_health(root)
    performance_signals = _latest_performance_signals(jobs)
    tracking_readiness = _tracking_readiness_rows(root, jobs)
    return {
        "units": units,
        "backup": backup,
        "backup_history": _backup_history(),
        "restore_smoke_history": _restore_smoke_history(root),
        "system_resources": _system_resources(root),
        "service_events": _service_event_history(),
        "summary": summary,
        "latest_jobs": jobs[:5],
        "publish_errors": _ops_publish_errors(jobs),
        "publish_failure_triage": _ops_publish_failure_triage(root, jobs),
        "publish_summary": publish_summary,
        "instagram_queue_history": _recent_instagram_queue_history(root),
        "track_summary": track_summary,
        "track_scheduler_history": _recent_track_queue_history(root),
        "tracking_failures": _tracking_failure_rows(root),
        "performance_signals": performance_signals,
        "tracking_readiness": tracking_readiness,
        "smoke_results": smoke_results,
        "action_buttons": _ops_action_buttons(),
        "action_result": None,
        "ops_audit": _recent_ops_audit(root),
        "ops_log": _ops_log_status(root),
        "work_activity": read_recent_work_activity(root),
        "work_activity_log": work_activity_status(root),
        "job_state_health": job_state_health,
        "ops_incidents": _recent_ops_incidents(root),
        "ops_reports": ops_reports,
        "incident_summary": incident_summary,
        "incident_result": None,
        "ops_daily_summary": _ops_daily_summary(jobs, units, backup, incident_summary, publish_summary, track_summary, ops_reports),
        "workflow_owners": _workflow_owner_summary(jobs),
        "security_hygiene": _security_hygiene_checks(root),
    }


def _project_options(root: Path) -> list[dict]:
    options = []
    for slug in list_project_slugs(root):
        options.append({"slug": slug, "label": load_project_page_name(slug, root=root)})
    return options


def _read_review_note(root: Path) -> dict | None:
    review_root = root / "review"
    if not review_root.exists():
        return None
    notes = sorted(
        review_root.glob("crew_final_style_v*/review_notes.md"),
        key=lambda path: (path.stat().st_mtime, str(path)),
        reverse=True,
    )
    if not notes:
        return None
    path = notes[0]
    title = path.parent.name.replace("_", " ").title()
    return {
        "title": title,
        "path": str(path.relative_to(root)),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        "body": path.read_text(encoding="utf-8"),
    }


def _read_asset_audit_note(root: Path) -> dict | None:
    review_root = root / "review"
    if not review_root.exists():
        return None
    notes = sorted(
        review_root.glob("crew_static_production_*/asset_audit.md"),
        key=lambda path: (path.stat().st_mtime, str(path)),
        reverse=True,
    )
    if not notes:
        return None
    path = notes[0]
    return {
        "title": path.parent.name.replace("_", " ").title(),
        "path": str(path.relative_to(root)),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        "body": path.read_text(encoding="utf-8"),
    }


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or not header.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return struct.unpack(">II", header[16:24])


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _crew_asset_audit(root: Path) -> dict[str, object]:
    static_root = root / "static" / "crew"
    review_root = root / "review" / "crew_final_style_v7"
    rows = []
    matched_review = 0
    concept_files = {"nami.png", "genie.png"}
    if not static_root.exists():
        return {
            "status": "Missing",
            "total": 0,
            "matched_review": 0,
            "rows": rows,
            "summary": "No production crew asset folder found.",
        }
    for path in sorted(static_root.glob("*.png")):
        dimensions = _png_dimensions(path)
        review_path = review_root / path.name
        static_hash = _sha256(path)
        review_hash = _sha256(review_path) if review_path.exists() else None
        matches_review = bool(static_hash and review_hash and static_hash == review_hash)
        matched_review += 1 if matches_review else 0
        status = "Approved concept portrait" if path.name in concept_files else "Approved production portrait"
        rows.append(
            {
                "file": path.name,
                "path": str(path.relative_to(root)),
                "dimensions": f"{dimensions[0]} x {dimensions[1]}" if dimensions else "unknown",
                "status": status,
                "source": "Matches v7 review" if matches_review else "Manual/static production asset",
            }
        )
    return {
        "status": "Production canon" if rows else "Missing",
        "total": len(rows),
        "matched_review": matched_review,
        "rows": rows,
        "summary": (
            f"{len(rows)} PNG production assets; {matched_review} match the v7 review folder by hash. "
            "Future replacements need a new review folder and explicit approval."
        ),
    }


def _latest_learning_brief(root: Path) -> dict | None:
    daily_dir = root / "docs" / "learning" / "daily"
    if not daily_dir.exists():
        return None
    briefs = sorted(daily_dir.glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not briefs:
        return None
    path = briefs[0]
    text = path.read_text(encoding="utf-8")
    _, body = _split_front_matter(text)
    return {
        "title": path.stem.replace("-", " ").title(),
        "path": str(path.relative_to(root)),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        "body": body,
    }


def _manual_closeout_learning_rows(root: Path, limit: int = 8) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for job in list_all_jobs(root):
        kit = job.manual_post_kit if isinstance(job.manual_post_kit, dict) else {}
        closeout = kit.get("closeout") if isinstance(kit.get("closeout"), dict) else {}
        if closeout.get("status") != "closed":
            continue
        manual_post = kit.get("manual_post") if isinstance(kit.get("manual_post"), dict) else {}
        proof = closeout.get("proof_summary") if isinstance(closeout.get("proof_summary"), dict) else {}
        platforms = sorted(
            str(platform)
            for platform, value in manual_post.items()
            if isinstance(value, dict) and value.get("status") == "posted"
        )
        post_url = ""
        posted_at = ""
        for value in manual_post.values():
            if isinstance(value, dict) and not post_url:
                post_url = str(value.get("post_url") or "")
                posted_at = str(value.get("posted_at") or "")
        rows.append(
            {
                "job_id": job.id,
                "page_name": job.pm.page_name,
                "brief": job.brief,
                "detail_url": f"/jobs/{job.id}",
                "platforms": platforms,
                "post_url": post_url,
                "posted_at": posted_at,
                "closed_at": str(closeout.get("closed_at") or ""),
                "closed_by": str(closeout.get("closed_by") or ""),
                "learning_note": str(closeout.get("learning_note") or ""),
                "proof_summary": {
                    "drive_synced": bool(proof.get("drive_synced")),
                    "post_url_present": bool(proof.get("post_url_present")),
                    "snapshot_24h_present": bool(proof.get("snapshot_24h_present")),
                    "snapshot_72h_present": bool(proof.get("snapshot_72h_present")),
                    "learning_note_captured": bool(proof.get("learning_note_captured")),
                },
            }
        )
    return sorted(rows, key=lambda item: (str(item["closed_at"]), str(item["job_id"])), reverse=True)[:limit]


def _manual_closeout_learning_brief_intake(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "No closed manual posting lessons are ready for the daily brief yet."
    lines = ["## Manual Posting Lessons", ""]
    for row in rows:
        platforms = ", ".join(str(platform) for platform in row.get("platforms", [])) or "manual platform"
        lines.extend(
            [
                f"- {row['page_name']} / {platforms}: {row['brief']}",
                f"  - Source job: {row['job_id']}",
                f"  - Lesson: {row['learning_note']}",
                f"  - Proof: post URL={row['proof_summary']['post_url_present']}, 24h={row['proof_summary']['snapshot_24h_present']}, 72h={row['proof_summary']['snapshot_72h_present']}",
            ]
        )
    return "\n".join(lines)


def _manual_closeout_learning_draft_body(rows: list[dict[str, object]], today: date | None = None) -> str:
    today = today or date.today()
    intake = _manual_closeout_learning_brief_intake(rows)
    source_ids = ", ".join(str(row["job_id"]) for row in rows) if rows else "none"
    return "\n".join(
        [
            f"# Daily Learning Brief - {today.isoformat()}",
            "",
            "## Captain Intent",
            "",
            "- Main goal: Turn closed manual posting lessons into the next Aurora operating decisions.",
            "- Active ship/page/project: NayzFreedom Fleet / Aurora / SlayHack",
            "- Today's mode: learn",
            "- Do not touch: live publish APIs or existing daily learning files.",
            "",
            "## What Nayz Asked For",
            "",
            "- Create a durable draft from manual posting closeout lessons.",
            "",
            intake,
            "",
            "## System Lessons",
            "",
            "- Manual posting closeout should preserve source job IDs, proof state, and the Captain learning note.",
            "",
            "## Operational Lessons",
            "",
            "- Source job IDs: " + source_ids,
            "",
            "## What Sage Should Store",
            "",
            "- Store the manual posting lesson notes only after Captain review.",
            "",
            "## What Iris Should Check Later",
            "",
            "- Compare future post performance against the closed manual lessons listed above.",
            "",
            "## What Should Stay Private Or Unstored",
            "",
            "- Do not store credentials, unpublished drafts, or platform tokens.",
            "",
            "## Tomorrow's Suggested Route",
            "",
            "1. Review the manual posting lessons.",
            "2. Apply the strongest lesson to the next Daily Slate item.",
            "3. Keep live publishing locked unless Captain Nayz explicitly opens it.",
            "",
        ]
    )


def _manual_closeout_learning_draft_front_matter(
    rows: list[dict[str, object]],
    *,
    status: str = "draft",
    created_by: str = "dashboard",
) -> dict[str, object]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "status": status,
        "source": "manual_posting_closeout",
        "source_job_ids": [str(row["job_id"]) for row in rows],
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }


def _front_matter_text(data: dict[str, object]) -> str:
    return "---\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip() + "\n---\n\n"


def _split_front_matter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return {}, text
    body = text[end + len("\n---\n"):]
    if body.startswith("\n"):
        body = body[1:]
    return data if isinstance(data, dict) else {}, body


def _manual_closeout_learning_draft_path(root: Path, today: date | None = None) -> Path:
    today = today or date.today()
    daily_dir = root / "docs" / "learning" / "daily"
    stem = f"{today.isoformat()}-manual-posting-lessons"
    candidate = daily_dir / f"{stem}.md"
    index = 2
    while candidate.exists():
        candidate = daily_dir / f"{stem}-{index}.md"
        index += 1
    return candidate


def _write_manual_closeout_learning_draft(
    root: Path,
    rows: list[dict[str, object]],
    *,
    created_by: str = "dashboard",
) -> dict[str, object]:
    path = _manual_closeout_learning_draft_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = _manual_closeout_learning_draft_body(rows)
    front_matter = _manual_closeout_learning_draft_front_matter(rows, created_by=created_by)
    path.write_text(_front_matter_text(front_matter) + body, encoding="utf-8")
    return {
        "path": str(path.relative_to(root)),
        "body": body,
        "source_job_ids": [str(row["job_id"]) for row in rows],
    }


def _daily_brief_draft_registry(root: Path) -> dict[str, object]:
    daily_dir = root / "docs" / "learning" / "daily"
    rows: list[dict[str, object]] = []
    if daily_dir.exists():
        for path in sorted(daily_dir.glob("*manual-posting-lessons*.md"), reverse=True):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            front_matter, body = _split_front_matter(text)
            source_job_ids = front_matter.get("source_job_ids")
            if not isinstance(source_job_ids, list):
                source_job_ids = []
            status = str(front_matter.get("status") or "legacy")
            rows.append(
                {
                    "path": str(path.relative_to(root)),
                    "status": status,
                    "state": "ready" if status == "accepted" else "failed" if status == "needs_edits" else "missing",
                    "source": str(front_matter.get("source") or "unknown"),
                    "source_job_ids": [str(item) for item in source_job_ids],
                    "created_by": str(front_matter.get("created_by") or ""),
                    "created_at": str(front_matter.get("created_at") or ""),
                    "updated_at": str(front_matter.get("updated_at") or ""),
                    "body_preview": body[:220],
                    "body": body,
                }
            )
    groups = [
        {
            "key": "draft",
            "label": "Drafts waiting review",
            "rows": [row for row in rows if row["status"] in {"draft", "reviewed", "legacy"}],
        },
        {
            "key": "accepted",
            "label": "Accepted learning artifacts",
            "rows": [row for row in rows if row["status"] == "accepted"],
        },
        {
            "key": "needs_edits",
            "label": "Needs edits",
            "rows": [row for row in rows if row["status"] == "needs_edits"],
        },
    ]
    return {"rows": rows, "groups": groups}


def _learning_category(note: str) -> str:
    lowered = note.lower()
    if any(token in lowered for token in ("cta", "comment", "save", "share")):
        return "CTA"
    if any(token in lowered for token in ("time", "timing", "hour", "morning", "night", "posted")):
        return "Timing"
    if any(token in lowered for token in ("instagram", "facebook", "tiktok", "youtube", "reel")):
        return "Platform"
    if any(token in lowered for token in ("snapshot", "24h", "72h", "reach", "like", "metric")):
        return "Tracking note"
    return "Content angle"


def _accepted_learning_intake(root: Path, limit: int = 4) -> dict[str, object]:
    registry = _daily_brief_draft_registry(root)
    accepted = [row for row in registry["rows"] if row.get("status") == "accepted"]
    lessons = []
    for artifact in accepted[:limit]:
        body = str(artifact.get("body") or "")
        source_job_ids = [str(item) for item in artifact.get("source_job_ids", [])]
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped.startswith("- Lesson:"):
                continue
            note = stripped.removeprefix("- Lesson:").strip()
            if not note:
                continue
            lessons.append(
                {
                    "category": _learning_category(note),
                    "note": note,
                    "artifact_path": artifact["path"],
                    "source_job_ids": source_job_ids,
                }
            )
    return {
        "artifacts": accepted[:limit],
        "lessons": lessons,
        "source_job_ids": sorted({job_id for row in accepted[:limit] for job_id in row.get("source_job_ids", [])}),
    }


def _update_daily_brief_draft_status(
    root: Path,
    relative_path: str,
    status: str,
    *,
    actor: str,
) -> dict[str, object]:
    if status not in {"reviewed", "needs_edits", "accepted"}:
        raise ValueError("Unsupported draft status")
    path = (root / relative_path).resolve()
    daily_dir = (root / "docs" / "learning" / "daily").resolve()
    try:
        path.relative_to(daily_dir)
    except ValueError as exc:
        raise ValueError("Draft path must stay under docs/learning/daily") from exc
    if not path.name.endswith(".md") or "manual-posting-lessons" not in path.name:
        raise ValueError("Draft path is not a manual posting lesson draft")
    if not path.exists():
        raise FileNotFoundError(relative_path)
    text = path.read_text(encoding="utf-8")
    front_matter, body = _split_front_matter(text)
    source_job_ids = front_matter.get("source_job_ids")
    if status == "accepted" and not (isinstance(source_job_ids, list) and source_job_ids):
        raise ValueError("Source job IDs are required before accepting a draft")
    if not front_matter:
        front_matter = {
            "source": "manual_posting_closeout",
            "source_job_ids": source_job_ids if isinstance(source_job_ids, list) else [],
            "created_by": actor,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    front_matter["status"] = status
    front_matter["reviewed_by"] = actor
    front_matter["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    front_matter["updated_at"] = front_matter["reviewed_at"]
    path.write_text(_front_matter_text(front_matter) + body, encoding="utf-8")
    return {
        "path": str(path.relative_to(root)),
        "status": status,
        "source_job_ids": front_matter.get("source_job_ids", []),
    }


def _apply_accepted_learning_to_next_mission(
    root: Path,
    project_slug: str,
    *,
    actor: str,
) -> dict[str, object]:
    intake = _accepted_learning_intake(root)
    if not intake["artifacts"]:
        raise ValueError("No accepted learning artifacts are ready to apply")
    resolved = resolve_project_slug(project_slug, root=root)
    cards = [card for card in _daily_slate_cards(root) if card["project"] == resolved]
    if not cards or not cards[0].get("next_ticket"):
        raise ValueError(f"No Daily Slate ticket is ready for project {resolved!r}")
    ticket = cards[0]["next_ticket"]
    mission = ticket.get("mission") if isinstance(ticket.get("mission"), dict) else None
    if mission:
        job = _find_job_at_root(root, str(mission["job_id"]))
        created = False
    else:
        job = _create_slate_ticket_mission(root, resolved, str(ticket["ticket_id"]))
        created = True

    applied_at = datetime.now(timezone.utc).isoformat()
    learning_payload = {
        "status": "applied",
        "applied_by": actor,
        "applied_at": applied_at,
        "source_artifacts": [row["path"] for row in intake["artifacts"]],
        "source_job_ids": intake["source_job_ids"],
        "lessons": intake["lessons"],
        "next_action": "Use these accepted manual posting lessons while shaping this mission. Live publish stays locked.",
    }
    if isinstance(job.production_ticket, dict):
        job.production_ticket["accepted_learning"] = learning_payload
    elif isinstance(job.video_package, dict):
        job.video_package["accepted_learning"] = learning_payload
    else:
        job.production_ticket = {"accepted_learning": learning_payload}
    _save_job_at_root(root, job)

    applied_sources = []
    for source_job_id in intake["source_job_ids"]:
        try:
            source_job = _find_job_at_root(root, source_job_id)
        except FileNotFoundError:
            continue
        kit = dict(source_job.manual_post_kit or {})
        closeout = dict(kit.get("closeout") or {})
        if closeout.get("status") != "closed":
            continue
        closeout["learning_applied"] = {
            "status": "applied",
            "applied_to_job_id": job.id,
            "applied_to_project": resolved,
            "applied_at": applied_at,
            "applied_by": actor,
        }
        kit["closeout"] = closeout
        source_job.manual_post_kit = kit
        _save_job_at_root(root, source_job)
        applied_sources.append(source_job_id)

    return {
        "job_id": job.id,
        "project": resolved,
        "ticket_id": ticket["ticket_id"],
        "created": created,
        "source_job_ids": intake["source_job_ids"],
        "applied_source_job_ids": applied_sources,
    }


def _accepted_learning_for_job(job: ContentJob) -> dict[str, object]:
    for source in (getattr(job, "production_ticket", None), getattr(job, "video_package", None)):
        if isinstance(source, dict) and isinstance(source.get("accepted_learning"), dict):
            learning = dict(source["accepted_learning"])
            lessons = learning.get("lessons") if isinstance(learning.get("lessons"), list) else []
            source_artifacts = (
                learning.get("source_artifacts") if isinstance(learning.get("source_artifacts"), list) else []
            )
            source_job_ids = learning.get("source_job_ids") if isinstance(learning.get("source_job_ids"), list) else []
            confirmed = bool(learning.get("learning_confirmed_at"))
            return {
                "present": True,
                "status": "Learning ready for execution" if confirmed else "Needs planning confirmation",
                "state": "ready" if confirmed else "missing",
                "source_artifacts": [str(item) for item in source_artifacts],
                "source_job_ids": [str(item) for item in source_job_ids],
                "lessons": lessons,
                "confirmed": confirmed,
                "learning_confirmed_at": str(learning.get("learning_confirmed_at") or ""),
                "learning_confirmed_by": str(learning.get("learning_confirmed_by") or ""),
                "next_action": (
                    "Learning has been confirmed for this mission's execution plan."
                    if confirmed
                    else "Confirm the accepted learning was used in the plan before generation starts."
                ),
            }
    return {"present": False, "confirmed": True, "lessons": [], "source_artifacts": [], "source_job_ids": []}


def _learning_blocks_generation(job: ContentJob) -> bool:
    learning = _accepted_learning_for_job(job)
    return bool(learning.get("present")) and not bool(learning.get("confirmed"))


def _confirm_mission_learning(root: Path, job: ContentJob, *, actor: str) -> dict[str, object]:
    if not _accepted_learning_for_job(job).get("present"):
        raise ValueError("No accepted learning is attached to this mission")
    confirmed_at = datetime.now(timezone.utc).isoformat()
    updated = False
    for field_name in ("production_ticket", "video_package"):
        source = getattr(job, field_name, None)
        if isinstance(source, dict) and isinstance(source.get("accepted_learning"), dict):
            source["accepted_learning"]["status"] = "confirmed"
            source["accepted_learning"]["learning_confirmed_by"] = actor
            source["accepted_learning"]["learning_confirmed_at"] = confirmed_at
            source["accepted_learning"]["next_action"] = (
                "Learning confirmed; crew can use this plan in safe generation execution."
            )
            setattr(job, field_name, source)
            updated = True
    if not updated:
        raise ValueError("No accepted learning is attached to this mission")
    _save_job_at_root(root, job)
    return {
        "job_id": job.id,
        "learning_confirmed_by": actor,
        "learning_confirmed_at": confirmed_at,
    }


_RUNBOOK_PROOF_EVENTS = (
    ("Accepted daily learning draft from runbook", "accept", "Accepted draft"),
    ("Applied accepted learning from runbook", "apply", "Applied lesson"),
    ("Confirmed accepted learning from runbook", "confirm", "Confirmed mission"),
)


def _runbook_proof_action(summary: str) -> tuple[str, str] | None:
    for prefix, action, label in _RUNBOOK_PROOF_EVENTS:
        if summary.startswith(prefix):
            return action, label
    return None


def _captain_learning_runbook_proof(root: Path, runbook: dict[str, object]) -> dict[str, object]:
    for item in read_recent_work_activity(root, limit=120):
        summary = str(item.get("summary", ""))
        matched = _runbook_proof_action(summary)
        if not matched:
            continue
        action, label = matched
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        source_job_ids = metadata.get("source_job_ids") if isinstance(metadata.get("source_job_ids"), list) else []
        target_mission = str(metadata.get("job_id") or metadata.get("target_job_id") or "")
        next_step = runbook.get("next_step") if isinstance(runbook.get("next_step"), dict) else None
        next_missing = str(next_step.get("label")) if next_step else "None"
        loop_state = str(runbook.get("state") or "")
        return {
            "present": True,
            "action": action,
            "action_label": label,
            "summary": f"Loop clear after {label}" if not next_step else f"Last action: {label}",
            "loop_state": loop_state,
            "next_missing": next_missing,
            "timestamp": str(item.get("timestamp") or ""),
            "actor": str(item.get("actor") or ""),
            "source_artifact": str(item.get("result") or ""),
            "source_job_ids": [str(source_id) for source_id in source_job_ids],
            "target_mission": target_mission,
            "next_action": str(item.get("next_action") or ""),
        }
    next_step = runbook.get("next_step") if isinstance(runbook.get("next_step"), dict) else None
    return {
        "present": False,
        "summary": "No runbook proof recorded yet.",
        "loop_state": str(runbook.get("state") or ""),
        "next_missing": str(next_step.get("label")) if next_step else "None",
    }


def _captain_learning_runbook(root: Path, jobs: list[ContentJob] | None = None) -> dict[str, object]:
    jobs = jobs if jobs is not None else list_all_jobs(root)
    manual_rows = _manual_posting_queue_rows(root)
    closeout_rows = [row for row in manual_rows if row.get("can_closeout")]
    registry = _daily_brief_draft_registry(root)
    draft_rows = [
        row
        for row in registry["rows"]
        if row.get("status") in {"draft", "reviewed", "legacy", "needs_edits"}
    ]
    actionable_draft = next(
        (row for row in draft_rows if row.get("status") in {"draft", "reviewed", "legacy"} and row.get("source_job_ids")),
        None,
    )
    accepted_intake = _accepted_learning_intake(root)
    slate_cards = _daily_slate_cards(root)
    apply_target = next((card for card in slate_cards if card.get("next_ticket")), None)
    accepted_source_ids = set(str(item) for item in accepted_intake.get("source_job_ids", []))
    applied_jobs = []
    unconfirmed_jobs = []
    for job in jobs:
        learning = _accepted_learning_for_job(job)
        if not learning.get("present"):
            continue
        source_ids = set(str(item) for item in learning.get("source_job_ids", []))
        if not accepted_source_ids or source_ids & accepted_source_ids:
            applied_jobs.append({"job_id": job.id, "brief": job.brief, "url": f"/jobs/{job.id}", "learning": learning})
        if not learning.get("confirmed"):
            unconfirmed_jobs.append({"job_id": job.id, "brief": job.brief, "url": f"/jobs/{job.id}", "learning": learning})

    accepted_waiting_apply = bool(accepted_intake.get("artifacts")) and not applied_jobs
    steps = [
        {
            "key": "capture_closeout",
            "label": "Capture closeout lesson",
            "status": "needs_action" if closeout_rows else "clear",
            "count": len(closeout_rows),
            "detail": (
                f"{len(closeout_rows)} manual post needs closeout learning."
                if closeout_rows
                else "No tracking-complete manual post is waiting for closeout."
            ),
            "action_label": "Open manual closeout",
            "action_url": "/aurora/manual-posting?lane=tracking_complete",
            "action_method": "get",
            "action_payload": {},
        },
        {
            "key": "accept_draft",
            "label": "Accept daily learning draft",
            "status": "needs_action" if draft_rows else "clear",
            "count": len(draft_rows),
            "detail": (
                f"{len(draft_rows)} daily learning draft needs review."
                if draft_rows
                else "No daily learning draft is waiting for Captain review."
            ),
            "action_label": "Accept daily learning draft" if actionable_draft else "Open learning desk",
            "action_url": "/learning-runbook/accept-draft" if actionable_draft else "/aurora/learning",
            "action_method": "post" if actionable_draft else "get",
            "action_payload": {"draft_path": actionable_draft["path"]} if actionable_draft else {},
        },
        {
            "key": "apply_learning",
            "label": "Apply learning to next mission",
            "status": "needs_action" if accepted_waiting_apply else "clear",
            "count": len(accepted_intake.get("artifacts", [])),
            "detail": (
                "Accepted learning is ready to apply to the next Daily Slate mission."
                if accepted_waiting_apply
                else "No accepted learning artifact is waiting for mission application."
            ),
            "action_label": "Apply learning to next mission" if accepted_waiting_apply and apply_target else "Open Daily Slate",
            "action_url": "/learning-runbook/apply-learning" if accepted_waiting_apply and apply_target else "/aurora/daily-slate",
            "action_method": "post" if accepted_waiting_apply and apply_target else "get",
            "action_payload": {"project_slug": apply_target["project"]} if accepted_waiting_apply and apply_target else {},
        },
        {
            "key": "confirm_learning",
            "label": "Confirm learning before generation",
            "status": "needs_action" if unconfirmed_jobs else "clear",
            "count": len(unconfirmed_jobs),
            "detail": (
                f"{len(unconfirmed_jobs)} mission has applied learning waiting for planning confirmation."
                if len(unconfirmed_jobs) == 1
                else f"{len(unconfirmed_jobs)} missions have applied learning waiting for planning confirmation."
                if unconfirmed_jobs
                else "No mission is blocked by unconfirmed learning."
            ),
            "action_label": "Confirm learning used in plan" if unconfirmed_jobs else "Open mission",
            "action_url": "/learning-runbook/confirm-learning" if unconfirmed_jobs else "/aurora/generation",
            "action_method": "post" if unconfirmed_jobs else "get",
            "action_payload": {"job_id": unconfirmed_jobs[0]["job_id"]} if unconfirmed_jobs else {},
            "secondary_label": "Open mission" if unconfirmed_jobs else "",
            "secondary_url": unconfirmed_jobs[0]["url"] if unconfirmed_jobs else "",
        },
    ]

    next_step = next((step for step in steps if step["status"] == "needs_action"), None)
    runbook = {
        "state": "Needs Captain" if next_step else "Learning loop clear",
        "summary": next_step["detail"] if next_step else "Closeout, draft review, apply, and confirmation gates are clear.",
        "next_step": next_step,
        "steps": steps,
        "applied_jobs": applied_jobs,
    }
    runbook["proof"] = _captain_learning_runbook_proof(root, runbook)
    return runbook


def _build_voyage_steps(job) -> list[dict]:
    order = [step.stage for step in WORKFLOW_STEPS]
    current_index = order.index(job.stage) if job.stage in order else 0
    status_value = getattr(job.status, "value", str(job.status))
    steps = []
    for index, step in enumerate(WORKFLOW_STEPS):
        member = get_crew_member(step.crew_slug) if step.crew_slug else None
        if index < current_index:
            state = "done"
        elif index == current_index:
            if status_value == "failed":
                state = "blocked"
            elif status_value == "completed" or step.stage == "publish_done":
                state = "done"
            else:
                state = "current"
        else:
            state = "upcoming"
        steps.append({"step": step, "member": member, "state": state})
    return steps


def _mission_command(job, voyage_steps: list[dict], completed_count: int) -> dict:
    status_value = getattr(job.status, "value", str(job.status))
    current = next(
        (item for item in voyage_steps if item["state"] in {"current", "blocked"}),
        voyage_steps[-1] if voyage_steps else None,
    )
    step = current["step"] if current else None
    member = current["member"] if current else None
    owner = member.name if member else step.owner_name if step else "Mission crew"

    if status_value == "failed":
        state = "Needs Captain"
        action = "Review the failure and decide whether to rerun, redirect, or close the mission."
    elif status_value == "awaiting_approval":
        state = "Needs Captain"
        action = "Approve or redirect the waiting checkpoint before the workflow continues."
    elif status_value == "completed":
        state = "Complete"
        action = "Review the publish result and record performance when results arrive."
    elif status_value == "running":
        state = "In Motion"
        action = f"{owner} is holding the current stage."
    else:
        state = "Ready"
        action = "Start or resume the mission workflow."

    return {
        "state": state,
        "action": action,
        "stage_label": step.label if step else "Not started",
        "owner": owner,
        "station": step.station if step else "Mission deck",
        "progress": f"{completed_count}/{len(voyage_steps)}",
    }


def _mission_outputs(job, faq_content: str | None) -> list[dict[str, str]]:
    content_ready = job.bella_output is not None
    visual_ready = bool(job.visual_prompt or job.image_path or job.video_path)
    content_type = getattr(job.content_type, "value", job.content_type)
    visual_required = content_type != "article"
    video_package = getattr(job, "video_package", None) or {}
    generation_request = getattr(job, "generation_request", None) or {}
    generation_result = getattr(job, "generation_result", None) or {}
    video_package_ready = bool(video_package)
    generation_status = str(generation_request.get("status", "")) if isinstance(generation_request, dict) else ""
    generation_result_status = str(generation_result.get("status", "")) if isinstance(generation_result, dict) else ""
    generation_ready = generation_status in {"dry_run_completed", "completed"} or generation_result_status in {"dry_run_completed", "completed"}
    real_video_ready = generation_status == "completed" and generation_result_status == "completed" and bool(job.video_path)
    package_ready = _publish_package_completed(job)
    growth_ready = job.growth_strategy is not None
    community_ready = bool(faq_content)
    publish_ready = job.publish_result is not None
    learning_gate = _accepted_learning_for_job(job)

    outputs = [
        {
            "label": "Applied learning",
            "state": "Ready" if learning_gate.get("confirmed") else "Waiting" if learning_gate.get("present") else "Not needed",
            "detail": str(
                learning_gate.get("next_action")
                if learning_gate.get("present")
                else "No accepted learning artifact is attached to this mission."
            ),
        },
        {
            "label": "Content",
            "state": "Ready" if content_ready else "Waiting",
            "detail": "Bella output is available." if content_ready else "Waiting for written content.",
        },
        {
            "label": "Visual",
            "state": "Ready" if visual_ready else "Not needed" if not visual_required else "Waiting",
            "detail": "Visual direction is available." if visual_ready else "Article mission can skip visual direction." if not visual_required else "Waiting for visual direction.",
        },
        {
            "label": "Video package",
            "state": "Ready" if video_package_ready else "Not needed" if content_type != "video" else "Waiting",
            "detail": "Scene timing, prompts, and assets are attached." if video_package_ready else "Non-video mission can skip the Video Producer package." if content_type != "video" else "Waiting for Video Producer package.",
        },
        {
            "label": "Nora QA",
            "state": "Waiting" if _learning_blocks_generation(job) else "Ready" if generation_status in {"ready_for_generation", "dry_run_completed", "completed"} else "Waiting" if video_package_ready else "Not needed",
            "detail": "Needs planning confirmation before Nora marks generation ready." if _learning_blocks_generation(job) else "Nora approved the package for generation." if generation_status in {"ready_for_generation", "dry_run_completed", "completed"} else "Waiting for Nora to mark ready for generation." if video_package_ready else "No video generation gate is needed yet.",
        },
        {
            "label": "Generation",
            "state": "Ready" if generation_ready else "Waiting" if video_package_ready else "Not needed",
            "detail": "Generation dry-run artifact is saved." if generation_result_status == "dry_run_completed" else "Generated video artifact is recorded." if generation_ready else "Waiting for the generation runner.",
        },
        {
            "label": "Publish packaging",
            "state": "Ready" if package_ready else "Waiting" if real_video_ready else "Not needed" if not video_package_ready else "Waiting",
            "detail": "Publish package is recorded for Roxy and Emma." if package_ready else "Roxy and Emma can package caption, hashtags, FAQ, and publish prep." if real_video_ready else "Waiting for the real generated video attachment.",
        },
        {
            "label": "Growth",
            "state": "Ready" if growth_ready else "Waiting",
            "detail": "Caption, hashtags, and timing are available." if growth_ready else "Waiting for Roxy's strategy.",
        },
        {
            "label": "Community",
            "state": "Ready" if community_ready else "Waiting",
            "detail": "FAQ is available." if community_ready else "Waiting for Emma's FAQ.",
        },
        {
            "label": "Publish",
            "state": "Ready" if publish_ready else "Waiting",
            "detail": "Publish result is recorded." if publish_ready else "Waiting for launch result.",
        },
    ]
    return outputs


def _readiness_checks(root: Path) -> list[dict[str, str]]:
    deploy_dir = root / "deploy"
    required_deploy_files = [
        "nayzfreedom-dashboard.service",
        "nayzfreedom-bot.service",
        "nayzfreedom-scheduler.service",
        "nayzfreedom-scheduler.timer",
        "nayzfreedom-reporter.service",
        "nayzfreedom-reporter.timer",
        "setup.sh",
        "update.sh",
    ]
    missing_deploy = [name for name in required_deploy_files if not (deploy_dir / name).exists()]
    projects = list_project_slugs(root)
    output_dir = root / "output"
    static_required = [
        root / "static" / "style.css",
        root / "static" / "htmx.min.js",
        root / "static" / "ships" / "aurora-hero.png",
    ]
    missing_static = [path.name for path in static_required if not path.exists()]

    return [
        {
            "label": "Dashboard auth",
            "state": "Ready" if os.environ.get("DASHBOARD_USER") and os.environ.get("DASHBOARD_PASSWORD") else "Missing",
            "detail": "Basic Auth environment variables are configured.",
        },
        {
            "label": "Project config",
            "state": "Ready" if projects else "Missing",
            "detail": f"{len(projects)} project profile{'s' if len(projects) != 1 else ''} configured.",
        },
        {
            "label": "Mission output",
            "state": "Ready" if output_dir.exists() else "Waiting",
            "detail": "Output directory exists." if output_dir.exists() else "No output directory yet; first mission will create it.",
        },
        {
            "label": "Static assets",
            "state": "Ready" if not missing_static else "Missing",
            "detail": "Dashboard CSS, HTMX, and Aurora hero assets are present." if not missing_static else f"Missing: {', '.join(missing_static)}.",
        },
        {
            "label": "Deploy files",
            "state": "Ready" if not missing_deploy else "Missing",
            "detail": "Systemd services, timers, setup, and update scripts are present." if not missing_deploy else f"Missing: {', '.join(missing_deploy)}.",
        },
        {
            "label": "Privacy boundary",
            "state": "Planned",
            "detail": "Keep The Freedom private until stronger auth and memory boundaries are implemented.",
        },
    ]


def _ticket_type_from_calendar_key(key: str) -> ProductionTicketType:
    if key.startswith("article"):
        return ProductionTicketType.ARTICLE
    if key.startswith("infographic"):
        return ProductionTicketType.INFOGRAPHIC
    if key.startswith("long_video"):
        return ProductionTicketType.LONG_VIDEO
    if key.startswith("short_video"):
        return ProductionTicketType.SHORT_VIDEO
    return ProductionTicketType.COMMUNITY_POST


def _content_type_for_ticket(ticket_type: ProductionTicketType) -> ContentType:
    if ticket_type == ProductionTicketType.ARTICLE:
        return ContentType.ARTICLE
    if ticket_type == ProductionTicketType.INFOGRAPHIC:
        return ContentType.INFOGRAPHIC
    return ContentType.VIDEO if ticket_type in {ProductionTicketType.SHORT_VIDEO, ProductionTicketType.LONG_VIDEO} else ContentType.ARTICLE


def _platforms_for_ticket(ticket_type: ProductionTicketType) -> list[str]:
    if ticket_type == ProductionTicketType.ARTICLE:
        return ["facebook"]
    if ticket_type == ProductionTicketType.INFOGRAPHIC:
        return ["instagram", "facebook"]
    if ticket_type == ProductionTicketType.SHORT_VIDEO:
        return ["tiktok", "instagram"]
    if ticket_type == ProductionTicketType.LONG_VIDEO:
        return ["youtube", "facebook", "tiktok"]
    return ["facebook"]


def _owner_for_ticket(ticket_type: ProductionTicketType, pm_name: str) -> str:
    return {
        ProductionTicketType.ARTICLE: "Bella",
        ProductionTicketType.INFOGRAPHIC: "Lila",
        ProductionTicketType.SHORT_VIDEO: "Vera Reel",
        ProductionTicketType.LONG_VIDEO: "Vera Reel",
        ProductionTicketType.COMMUNITY_POST: "Emma",
        ProductionTicketType.DISTRIBUTION_PACK: "Roxy",
    }.get(ticket_type, pm_name)


def _acceptance_criteria_for_ticket(ticket_type: ProductionTicketType) -> list[str]:
    criteria = {
        ProductionTicketType.ARTICLE: [
            "Headline, body, and CTA are ready for Facebook.",
            "The angle is not a duplicate of a recent Slay Hack post.",
        ],
        ProductionTicketType.INFOGRAPHIC: [
            "4:5 visual structure, copy blocks, and prompt direction are ready.",
            "The save/share value is clear before QA.",
        ],
        ProductionTicketType.SHORT_VIDEO: [
            "15-40 second scene plan has hook, payoff, CTA, and primary platform.",
            "Bella/Lila handoff needs are clear before generation.",
        ],
        ProductionTicketType.LONG_VIDEO: [
            "60-180 second storyboard is complete before generation.",
            "Scene timing, tool hint, asset list, and CTA are ready for QA.",
        ],
        ProductionTicketType.COMMUNITY_POST: [
            "Prompt and moderation angle are ready.",
        ],
        ProductionTicketType.DISTRIBUTION_PACK: [
            "Caption, hashtag, timing, and platform CTA are ready.",
        ],
    }
    return criteria.get(ticket_type, [])


def _asset_requirements_for_ticket(ticket_type: ProductionTicketType) -> list[str]:
    if ticket_type == ProductionTicketType.LONG_VIDEO:
        return [
            "Storyboard scenes",
            "Veo3 prompt package",
            "Hero object reference",
            "Scene 8 infographic card",
        ]
    if ticket_type == ProductionTicketType.SHORT_VIDEO:
        return ["Short-form scene beats", "Hero object reference", "Visual prompt package"]
    if ticket_type == ProductionTicketType.INFOGRAPHIC:
        return ["4:5 layout brief", "Copy blocks", "Visual prompt package"]
    return []


def _storyboard_for_long_video(title: str) -> list[StoryboardScene]:
    purposes = [
        "hook",
        "problem",
        "setup",
        "step one",
        "step two",
        "step three",
        "proof",
        "saveable recap",
        "cta",
    ]
    return [
        StoryboardScene(
            number=index,
            duration_seconds=8,
            purpose=purpose,
            visual_direction=f"{title} - {purpose}",
            tool_hint="veo3",
        )
        for index, purpose in enumerate(purposes, start=1)
    ]


def _storyboard_for_short_video(title: str) -> list[StoryboardScene]:
    scene_plan = [
        (1, 5, "hook", "Open on the relatable problem with fast motion and a clean visual contrast."),
        (2, 12, "payoff", "Show the fix in one clear sequence with the hero object centered."),
        (3, 6, "cta", "Loop back to the starting frame and invite saves, shares, or comments."),
    ]
    return [
        StoryboardScene(
            number=number,
            duration_seconds=duration,
            purpose=purpose,
            visual_direction=f"{title} - {direction}",
            tool_hint="veo3",
        )
        for number, duration, purpose, direction in scene_plan
    ]


def _video_package_for_ticket(ticket: ProductionTicket) -> VideoProductionPackage | None:
    if ticket.ticket_type not in {ProductionTicketType.SHORT_VIDEO, ProductionTicketType.LONG_VIDEO}:
        return None
    storyboard = ticket.storyboard or _storyboard_for_short_video(ticket.title)
    scenes = []
    cursor = 0
    for scene in storyboard:
        end_second = cursor + scene.duration_seconds
        prompt = (
            f"{ticket.title}: {scene.purpose}. "
            f"Visual direction: {scene.visual_direction}. "
            f"Primary platform: {ticket.platform_primary or 'platform TBD'}. "
            "Keep pacing clear, character-led, and ready for generation."
        )
        scenes.append(
            VideoPackageScene(
                number=scene.number,
                start_second=cursor,
                end_second=end_second,
                purpose=scene.purpose,
                visual_direction=scene.visual_direction,
                prompt=prompt,
                tool_hint=scene.tool_hint or "veo3",
            )
        )
        cursor = end_second
    format_name = ticket.format_name or (
        "Short-form Veo3 package"
        if ticket.ticket_type == ProductionTicketType.SHORT_VIDEO
        else "Veo3 storyboard package"
    )
    asset_checklist = ticket.asset_requirements or _asset_requirements_for_ticket(ticket.ticket_type)
    return VideoProductionPackage(
        ticket_id=ticket.ticket_id,
        title=ticket.title,
        owner=ticket.owner,
        platform_primary=ticket.platform_primary,
        format_name=format_name,
        total_duration_seconds=cursor,
        scenes=scenes,
        prompt_package=[scene.prompt for scene in scenes],
        asset_checklist=asset_checklist,
        acceptance_criteria=ticket.acceptance_criteria,
        handoff_notes=[
            "Bella confirms the spoken hook and CTA before generation.",
            "Lila confirms the hero object, frame language, and visual references.",
            "Nora checks timing, platform fit, and asset completeness before publish packaging.",
        ],
    )


def _video_package_rows(slate: CalendarSlate | None) -> list[dict[str, object]]:
    if slate is None:
        return []
    packages = []
    for ticket in slate.tickets:
        package = _video_package_for_ticket(ticket)
        if package is None:
            continue
        packages.append(
            {
                "ticket_id": package.ticket_id,
                "title": package.title,
                "owner": package.owner,
                "platform_primary": package.platform_primary,
                "format_name": package.format_name,
                "total_duration_seconds": package.total_duration_seconds,
                "scene_count": len(package.scenes),
                "asset_count": len(package.asset_checklist),
                "acceptance_count": len(package.acceptance_criteria),
                "scenes": package.scenes,
                "asset_checklist": package.asset_checklist,
                "handoff_notes": package.handoff_notes,
                "create_mission_url": f"/aurora/workflow/video-packages/{package.ticket_id}/create-mission",
            }
        )
    return packages


def _daily_slate_video_package_rows(slate: CalendarSlate | None) -> list[dict[str, object]]:
    packages = _video_package_rows(slate)
    if slate is None:
        return packages
    for package in packages:
        package["daily_create_mission_url"] = (
            f"/aurora/daily-slate/{slate.project}/video-packages/{package['ticket_id']}/create-mission"
        )
    return packages


def _find_video_ticket(slate: CalendarSlate | None, ticket_id: str) -> ProductionTicket | None:
    if slate is None:
        return None
    for ticket in slate.tickets:
        if ticket.ticket_id == ticket_id:
            return ticket
    return None


def _find_slate_ticket(slate: CalendarSlate | None, ticket_id: str) -> ProductionTicket | None:
    if slate is None:
        return None
    for ticket in slate.tickets:
        if ticket.ticket_id == ticket_id:
            return ticket
    return None


def _ticket_payload(ticket: ProductionTicket) -> dict[str, object]:
    return ticket.model_dump(mode="json")


def _video_package_payload(package: VideoProductionPackage) -> dict[str, object]:
    return package.model_dump(mode="json")


def _generation_request_for_package(package: VideoProductionPackage) -> dict[str, object]:
    return {
        "status": "nora_review",
        "tool": "video_generation",
        "tool_hint": "veo3",
        "next_action": "Nora reviews scene timing, prompt package, and asset checklist before generation.",
        "ready_action": "Mark ready for generation",
        "scene_count": len(package.scenes),
        "total_duration_seconds": package.total_duration_seconds,
        "prompt_count": len(package.prompt_package),
        "asset_count": len(package.asset_checklist),
    }


def _generation_status_label(value: str) -> str:
    labels = {
        "nora_review": "Nora review",
        "ready_for_generation": "Ready",
        "dry_run_completed": "Dry-run complete",
        "completed": "Complete",
        "failed": "Failed",
    }
    return labels.get(value, value.replace("_", " ").title() if value else "Unknown")


def _generation_state(value: str) -> str:
    if value in {"ready_for_generation", "dry_run_completed", "completed"}:
        return "ready"
    if value == "failed":
        return "failed"
    return "missing"


def _waiting_for_real_video(job: ContentJob) -> bool:
    request = getattr(job, "generation_request", None) or {}
    result = getattr(job, "generation_result", None) or {}
    request_status = str(request.get("status", "")) if isinstance(request, dict) else ""
    result_status = str(result.get("status", "")) if isinstance(result, dict) else ""
    return request_status == "dry_run_completed" and result_status == "dry_run_completed" and not bool(job.video_path)


def _real_generation_completed(job: ContentJob) -> bool:
    request = getattr(job, "generation_request", None) or {}
    result = getattr(job, "generation_result", None) or {}
    request_status = str(request.get("status", "")) if isinstance(request, dict) else ""
    result_status = str(result.get("status", "")) if isinstance(result, dict) else ""
    return request_status == "completed" and result_status == "completed" and bool(job.video_path)


def _publish_package_completed(job: ContentJob) -> bool:
    package = getattr(job, "publish_package", None)
    return isinstance(package, dict) and package.get("status") == "completed"


def _publish_execution_status(job: ContentJob) -> str:
    execution = getattr(job, "publish_execution", None)
    if isinstance(execution, dict):
        return str(execution.get("status", ""))
    return ""


def _publish_execution_label(job: ContentJob) -> str:
    status = _publish_execution_status(job)
    labels = {
        "ready_to_publish": "Ready to publish",
        "captain_hold": "Captain hold",
        "needs_edits": "Needs edits",
        "scheduled": "Scheduled handoff",
        "published": "Published",
        "failed": "Publish failed",
    }
    return labels.get(status, "Create publish job" if _publish_package_completed(job) else "Not ready")


def _publish_execution_state(job: ContentJob) -> str:
    status = _publish_execution_status(job)
    if status in {"scheduled", "published"}:
        return "ready"
    if status in {"ready_to_publish", "captain_hold", "needs_edits"}:
        return "missing"
    if status == "failed":
        return "failed"
    return "unavailable"


def _clean_generation_text(value: str | None, field: str, max_length: int = 500) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{field} is required")
    if len(cleaned) > max_length:
        raise ValueError(f"{field} must be {max_length} characters or fewer")
    return cleaned


def _generation_artifact_path(root: Path, job: ContentJob) -> Path:
    return root / "output" / job.pm.page_name / job.id / "video_generation_dry_run.json"


def _generation_artifact_display_path(job: ContentJob) -> str:
    return f"output/{job.pm.page_name}/{job.id}/video_generation_dry_run.json"


def _publish_packaging_label(job: ContentJob) -> str:
    if _publish_package_completed(job):
        return "Publish package complete"
    if _real_generation_completed(job):
        return "Ready for publish packaging"
    if _waiting_for_real_video(job):
        return "Waiting real video"
    return "Not ready"


def _publish_packaging_state(job: ContentJob) -> str:
    if _publish_package_completed(job):
        return "ready"
    if _real_generation_completed(job):
        return "missing"
    return "unavailable"


def _publish_execution_summary(job: ContentJob) -> dict[str, object]:
    return {
        "status": _publish_execution_status(job),
        "label": _publish_execution_label(job),
        "state": _publish_execution_state(job),
        "can_create": _publish_package_completed(job),
        "can_schedule": _publish_execution_status(job) == "ready_to_publish",
    }


def _path_readiness(root: Path, value: object) -> dict[str, object]:
    raw = str(value or "").strip()
    if not raw:
        return {"path": "", "exists": False, "label": "Missing", "state": "missing"}
    path = Path(raw)
    resolved = path if path.is_absolute() else root / path
    exists = resolved.exists()
    return {
        "path": raw,
        "exists": exists,
        "label": "Verified on disk" if exists else "Recorded path; file check needed",
        "state": "ready" if exists else "missing",
    }


def _live_publish_gate_summary(root: Path, job: ContentJob) -> dict[str, object]:
    execution = dict(job.publish_execution or {})
    package = dict(job.publish_package or {})
    publish_result = job.publish_result or {}
    platforms = []
    for platform in execution.get("platforms") or job.platforms:
        result = publish_result.get(str(platform), {}) if isinstance(publish_result, dict) else {}
        result = result if isinstance(result, dict) else {}
        platforms.append(
            {
                "name": str(platform),
                "handoff_status": str(result.get("status", "missing")),
                "dry_run": result.get("dry_run") is True,
                "reason": str(result.get("reason", "No dashboard handoff reason recorded.")),
            }
        )
    return {
        "status": "Locked",
        "status_detail": "No real platform publisher API is called from this page.",
        "media": _path_readiness(root, execution.get("video_path") or job.video_path),
        "caption_ready": bool(str(execution.get("caption") or package.get("caption") or "").strip()),
        "hashtags_ready": bool(execution.get("hashtags") or package.get("hashtags")),
        "platforms": platforms,
        "approval_status": str(execution.get("live_publish_approval", {}).get("status", "not_requested"))
        if isinstance(execution.get("live_publish_approval"), dict)
        else "not_requested",
        "next_action": "Use this gate for final inspection only. Add a separate live publisher action only after explicit Captain approval.",
    }


GENERATION_FILTERS = (
    ("all", "All"),
    ("waiting_real_video", "Waiting real video"),
    ("ready_packaging", "Ready packaging"),
    ("package_complete", "Package complete"),
    ("ready_to_publish", "Ready to publish"),
    ("scheduled", "Scheduled handoff"),
    ("publish_failed", "Publish failed"),
)


def _generation_row_matches_filter(item: dict[str, object], selected: str) -> bool:
    if selected == "all":
        return True
    if selected == "waiting_real_video":
        return bool(item["waiting_for_real_video"])
    if selected == "ready_packaging":
        return bool(item["can_package"]) and item["packaging_label"] != "Publish package complete"
    if selected == "package_complete":
        return item["packaging_label"] == "Publish package complete"
    if selected == "ready_to_publish":
        return item["publish_execution"]["status"] == "ready_to_publish"
    if selected == "scheduled":
        return item["publish_execution"]["status"] == "scheduled"
    if selected == "publish_failed":
        return item["publish_execution"]["status"] == "failed"
    return True


def _generation_filter_cards(rows: list[dict[str, object]], selected: str) -> list[dict[str, object]]:
    return [
        {
            "key": key,
            "label": label,
            "active": key == selected,
            "count": sum(1 for item in rows if _generation_row_matches_filter(item, key)),
        }
        for key, label in GENERATION_FILTERS
    ]


def _generation_queue(root: Path) -> list[dict[str, object]]:
    rows = []
    for job in list_all_jobs(root):
        request = getattr(job, "generation_request", None)
        if not isinstance(request, dict):
            continue
        status = str(request.get("status", ""))
        result = getattr(job, "generation_result", None)
        learning_blocked = _learning_blocks_generation(job)
        rows.append(
            {
                "job": job,
                "status": status,
                "status_label": "Needs planning confirmation" if learning_blocked else _generation_status_label(status),
                "state": "missing" if learning_blocked else _generation_state(status),
                "tool_hint": request.get("tool_hint", "generation"),
                "scene_count": request.get("scene_count", 0),
                "asset_count": request.get("asset_count", 0),
                "attempt": request.get("attempt", 0),
                "next_action": (
                    "Confirm accepted learning on the mission before generation starts."
                    if learning_blocked
                    else request.get("next_action", "Review generation package.")
                ),
                "result": result if isinstance(result, dict) else None,
                "can_run": not learning_blocked and status in {"ready_for_generation", "failed", "dry_run_completed"},
                "can_record": not learning_blocked and status in {"ready_for_generation", "dry_run_completed", "failed"},
                "waiting_for_real_video": _waiting_for_real_video(job),
                "can_package": _real_generation_completed(job),
                "packaging_label": _publish_packaging_label(job),
                "packaging_state": _publish_packaging_state(job),
                "publish_execution": _publish_execution_summary(job),
            }
        )
    order = {"ready_for_generation": 0, "dry_run_completed": 1, "failed": 2, "nora_review": 3, "completed": 4}
    rows.sort(key=lambda item: (order.get(str(item["status"]), 9), not item["waiting_for_real_video"], str(item["job"].id)), reverse=False)
    return rows


def _run_generation_dry_run(root: Path, job: ContentJob) -> ContentJob:
    package = getattr(job, "video_package", None)
    if not isinstance(package, dict):
        raise ValueError("No video package is attached to this mission")
    prompts = package.get("prompt_package") or []
    scenes = package.get("scenes") or []
    if not prompts or not scenes:
        raise ValueError("Video package needs scenes and prompts before generation")
    generation_request = dict(job.generation_request or {})
    status = str(generation_request.get("status", ""))
    if status not in {"ready_for_generation", "failed", "dry_run_completed"}:
        raise ValueError("Generation is not ready to run yet")

    attempt = int(generation_request.get("attempt", 0) or 0) + 1
    created_at = datetime.now(timezone.utc).isoformat()
    artifact_payload = {
        "job_id": job.id,
        "mode": "dry_run",
        "status": "dry_run_completed",
        "tool": generation_request.get("tool", "video_generation"),
        "tool_hint": generation_request.get("tool_hint", "veo3"),
        "attempt": attempt,
        "scene_count": len(scenes),
        "prompt_count": len(prompts),
        "asset_count": len(package.get("asset_checklist") or []),
        "total_duration_seconds": package.get("total_duration_seconds"),
        "prompts": prompts,
        "created_at": created_at,
        "message": "Dry run only; no external generation API was called.",
    }
    artifact_path = _generation_artifact_path(root, job)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact_payload, indent=2))

    generation_request.update(
        {
            "status": "dry_run_completed",
            "attempt": attempt,
            "last_run_at": created_at,
            "next_action": "Roxy and Emma can package caption, hashtags, FAQ, and publish prep after the real video is attached.",
        }
    )
    job.generation_request = generation_request
    job.generation_result = {
        "status": "dry_run_completed",
        "mode": "dry_run",
        "tool": generation_request.get("tool", "video_generation"),
        "tool_hint": generation_request.get("tool_hint", "veo3"),
        "attempt": attempt,
        "scene_count": len(scenes),
        "prompt_count": len(prompts),
        "asset_count": len(package.get("asset_checklist") or []),
        "output_path": _generation_artifact_display_path(job),
        "created_at": created_at,
        "message": "Dry run only; no external generation API was called.",
    }
    job.stage = "generation_dry_run"
    job.status = JobStatus.AWAITING_APPROVAL
    _save_job_at_root(root, job)
    return job


def _split_hashtags(value: str) -> list[str]:
    tags = []
    for raw in value.replace("\n", ",").split(","):
        tag = raw.strip()
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = f"#{tag}"
        tags.append(tag)
    return tags


def _record_publish_package(
    root: Path,
    job: ContentJob,
    caption: str,
    hashtags: str,
    faq: str,
    publish_notes: str | None = None,
) -> ContentJob:
    if not _real_generation_completed(job):
        raise ValueError("Real generated video must be attached before publish packaging")

    cleaned_caption = _clean_generation_text(caption, "Caption", max_length=2200)
    cleaned_faq = _clean_generation_text(faq, "FAQ", max_length=4000)
    cleaned_notes = (publish_notes or "").strip()[:1000] or None
    tag_list = _split_hashtags(hashtags)
    if not tag_list:
        raise ValueError("At least one hashtag is required")

    recorded_at = datetime.now(timezone.utc).isoformat()
    faq_path = root / "output" / job.pm.page_name / job.id / "faq.md"
    faq_path.parent.mkdir(parents=True, exist_ok=True)
    faq_path.write_text(cleaned_faq)

    job.growth_strategy = GrowthStrategy(
        hashtags=tag_list,
        caption=cleaned_caption,
        best_post_time_utc="TBD",
        best_post_time_thai="TBD",
        editorial_guidance={
            "source": "publish_packaging_lane",
            "roxy_owner": "caption, hashtags, timing notes",
            "emma_owner": "FAQ and community response prep",
        },
    )
    job.community_faq_path = f"output/{job.pm.page_name}/{job.id}/faq.md"
    job.publish_package = {
        "status": "completed",
        "owners": ["Roxy", "Emma"],
        "caption": cleaned_caption,
        "hashtags": tag_list,
        "faq_path": job.community_faq_path,
        "publish_notes": cleaned_notes,
        "created_at": recorded_at,
        "next_action": "Publish package is ready for Captain review before dashboard handoff.",
    }
    job.stage = "publish_packaged"
    job.status = JobStatus.AWAITING_APPROVAL
    _save_job_at_root(root, job)
    return job


def _create_publish_execution(root: Path, job: ContentJob) -> ContentJob:
    if not _publish_package_completed(job):
        raise ValueError("Publish package must be complete before creating a publish job")
    package = job.publish_package or {}
    created_at = datetime.now(timezone.utc).isoformat()
    job.publish_execution = {
        "status": "ready_to_publish",
        "owners": ["Roxy", "Emma"],
        "platforms": list(job.platforms),
        "caption": package.get("caption"),
        "hashtags": package.get("hashtags", []),
        "faq_path": package.get("faq_path"),
        "video_path": job.video_path,
        "created_at": created_at,
        "next_action": "Captain review required before dashboard handoff. Live publishing remains locked.",
    }
    job.stage = "ready_to_publish"
    job.status = JobStatus.AWAITING_APPROVAL
    _save_job_at_root(root, job)
    return job


def _record_captain_review(root: Path, job: ContentJob, decision: str, note: str | None = None) -> ContentJob:
    execution = dict(job.publish_execution or {})
    if execution.get("status") not in {"ready_to_publish", "captain_hold", "needs_edits"}:
        raise ValueError("Publish job must be ready for Captain review")

    cleaned_note = (note or "").strip()[:1000] or None
    reviewed_at = datetime.now(timezone.utc).isoformat()
    review = {
        "decision": decision,
        "reviewed_at": reviewed_at,
        "reviewed_by": "Captain Nayz",
        "note": cleaned_note,
    }
    history = list(execution.get("captain_review_history") or [])
    history.append(review)
    execution["captain_review_history"] = history
    execution["captain_review"] = review

    if decision == "approve_schedule_handoff":
        execution["status"] = "ready_to_publish"
        execution["next_action"] = "Captain approved dashboard schedule handoff."
        job.publish_execution = execution
        return _schedule_publish_execution(root, job)
    if decision == "hold":
        execution.update(
            {
                "status": "captain_hold",
                "next_action": "Captain hold is active. Do not schedule until the hold is cleared.",
            }
        )
        job.stage = "captain_hold"
    elif decision == "needs_edits":
        execution.update(
            {
                "status": "needs_edits",
                "next_action": "Package needs edits before Captain approval. Send back to PM, Roxy, Emma, or Nora.",
            }
        )
        job.stage = "publish_needs_edits"
    else:
        raise ValueError("Unknown Captain review decision")

    job.publish_execution = execution
    job.status = JobStatus.AWAITING_APPROVAL
    _save_job_at_root(root, job)
    return job


def _schedule_publish_execution(root: Path, job: ContentJob) -> ContentJob:
    execution = dict(job.publish_execution or {})
    if execution.get("status") != "ready_to_publish":
        raise ValueError("Publish job must be ready before scheduling")
    scheduled_at = datetime.now(timezone.utc).isoformat()
    execution.update(
        {
            "status": "scheduled",
            "scheduled_at": scheduled_at,
            "next_action": "Dashboard handoff is recorded. Live publishing remains locked until explicit approval.",
        }
    )
    job.publish_execution = execution
    platform_result = {
        str(platform): {
            "status": "scheduled",
            "source": "publish_execution_lane",
            "scheduled_at": scheduled_at,
            "dry_run": True,
            "reason": "Dashboard schedule handoff only; no external platform API was called.",
        }
        for platform in job.platforms
    }
    job.publish_result = platform_result
    job.stage = "publish_scheduled"
    job.status = JobStatus.AWAITING_APPROVAL
    _save_job_at_root(root, job)
    return job


def _record_generation_result(
    root: Path,
    job: ContentJob,
    video_path: str,
    provider: str,
    provider_request_id: str | None = None,
    note: str | None = None,
) -> ContentJob:
    if not isinstance(getattr(job, "video_package", None), dict):
        raise ValueError("No video package is attached to this mission")
    generation_request = dict(job.generation_request or {})
    status = str(generation_request.get("status", ""))
    if status not in {"ready_for_generation", "dry_run_completed", "failed", "completed"}:
        raise ValueError("Generation is not ready to record a real result yet")

    recorded_at = datetime.now(timezone.utc).isoformat()
    cleaned_video_path = _clean_generation_text(video_path, "Video path")
    cleaned_provider = _clean_generation_text(provider, "Provider", max_length=80)
    cleaned_request_id = (provider_request_id or "").strip()[:120] or None
    cleaned_note = (note or "").strip()[:500] or None

    generation_request.update(
        {
            "status": "completed",
            "provider": cleaned_provider,
            "provider_request_id": cleaned_request_id,
            "completed_at": recorded_at,
            "next_action": "Generated video is attached. Roxy and Emma can package caption, hashtags, FAQ, and publish prep.",
        }
    )
    job.video_path = cleaned_video_path
    job.generation_request = generation_request
    job.generation_result = {
        "status": "completed",
        "mode": "real",
        "provider": cleaned_provider,
        "provider_request_id": cleaned_request_id,
        "output_path": cleaned_video_path,
        "created_at": recorded_at,
        "message": "Real generated video is attached to this mission.",
        "publish_packaging": {
            "status": "ready",
            "owners": ["Roxy", "Emma"],
            "next_action": "Prepare caption, hashtags, FAQ, and publish schedule.",
        },
    }
    if cleaned_note:
        job.generation_result["note"] = cleaned_note
    job.stage = "generation_completed"
    job.status = JobStatus.AWAITING_APPROVAL
    _save_job_at_root(root, job)
    return job


def _safe_job_suffix(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value).strip("_").lower()


def _save_job_at_root(root: Path, job: ContentJob) -> Path:
    out_dir = root / "output" / job.pm.page_name / job.id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "job.json"
    path.write_text(job.model_dump_json(indent=2))
    return path


def _find_job_at_root(root: Path, job_id: str) -> ContentJob:
    for path in (root / "output").rglob(f"{job_id}/job.json"):
        return ContentJob.model_validate_json(path.read_text())
    raise FileNotFoundError(f"Job ID '{job_id}' not found in {root / 'output'}")


def _video_package_job(root: Path, ticket: ProductionTicket, package: VideoProductionPackage) -> ContentJob:
    pm = load_project(ticket.project, root=root)
    suffix = _safe_job_suffix(ticket.ticket_id)
    job = ContentJob(
        id=f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{suffix}",
        project=ticket.project,
        pm=pm,
        brief=f"Video package mission: {ticket.title}",
        platforms=ticket.platforms,
        stage="video_package_ready",
        status=JobStatus.RUNNING,
        dry_run=True,
        content_type=ContentType.VIDEO,
        visual_prompt="\n".join(scene.prompt for scene in package.scenes),
        video_package=_video_package_payload(package),
        generation_request=_generation_request_for_package(package),
    )
    return job


def _slate_ticket_job(root: Path, ticket: ProductionTicket) -> ContentJob:
    pm = load_project(ticket.project, root=root)
    suffix = _safe_job_suffix(ticket.ticket_id)
    content_label = ticket.ticket_type.value.replace("_", " ")
    job = ContentJob(
        id=f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{suffix}",
        project=ticket.project,
        pm=pm,
        brief=f"Daily slate {content_label} mission: {ticket.title}",
        platforms=ticket.platforms,
        stage="slate_ticket_ready",
        status=JobStatus.RUNNING,
        dry_run=True,
        content_type=ticket.content_type,
        production_ticket=_ticket_payload(ticket),
    )
    return job


def _create_video_package_mission(root: Path, project_slug: str, ticket_id: str) -> ContentJob:
    slate = _calendar_slate(root, project_slug)
    ticket = _find_video_ticket(slate, ticket_id)
    if ticket is None:
        raise ValueError(f"Video package ticket {ticket_id!r} not found")
    package = _video_package_for_ticket(ticket)
    if package is None:
        raise ValueError(f"Ticket {ticket_id!r} is not a video package")
    job = _video_package_job(root, ticket, package)
    _save_job_at_root(root, job)
    return job


def _create_slate_ticket_mission(root: Path, project_slug: str, ticket_id: str) -> ContentJob:
    slate = _calendar_slate(root, project_slug)
    ticket = _find_slate_ticket(slate, ticket_id)
    if ticket is None:
        raise ValueError(f"Production ticket {ticket_id!r} not found")
    if ticket.ticket_type in {ProductionTicketType.SHORT_VIDEO, ProductionTicketType.LONG_VIDEO}:
        return _create_video_package_mission(root, project_slug, ticket_id)
    job = _slate_ticket_job(root, ticket)
    _save_job_at_root(root, job)
    return job


def _weekly_calendar(root: Path, project_slug: str) -> dict[str, dict[str, str]]:
    resolved = resolve_project_slug(project_slug, root=root)
    path = root / "projects" / resolved / "weekly_calendar.yaml"
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return {}
    return {str(day): dict(items or {}) for day, items in data.items()}


def _calendar_slate(root: Path, project_slug: str = "slay_hack") -> CalendarSlate | None:
    try:
        pm = load_project(project_slug, root=root)
    except Exception:
        return None
    calendar = _weekly_calendar(root, project_slug)
    day_key = datetime.now(timezone.utc).strftime("%A").lower()
    day_items = calendar.get(day_key) or next(iter(calendar.values()), {})
    tickets = []
    for key, title in day_items.items():
        ticket_type = _ticket_type_from_calendar_key(str(key))
        platforms = _platforms_for_ticket(ticket_type)
        if ticket_type == ProductionTicketType.LONG_VIDEO:
            storyboard = _storyboard_for_long_video(str(title))
        elif ticket_type == ProductionTicketType.SHORT_VIDEO:
            storyboard = _storyboard_for_short_video(str(title))
        else:
            storyboard = []
        tickets.append(
            ProductionTicket(
                ticket_id=f"{day_key}-{str(key).replace('_', '-')}",
                project=resolve_project_slug(project_slug, root=root),
                page_name=pm.page_name,
                ticket_type=ticket_type,
                content_type=_content_type_for_ticket(ticket_type),
                title=str(title),
                objective="daily content floor",
                owner=_owner_for_ticket(ticket_type, pm.name),
                platforms=platforms,
                platform_primary=platforms[0],
                decision_owner=pm.name,
                acceptance_criteria=_acceptance_criteria_for_ticket(ticket_type),
                asset_requirements=_asset_requirements_for_ticket(ticket_type),
                due_date=date.today(),
                format_name="Veo3 storyboard package" if ticket_type == ProductionTicketType.LONG_VIDEO else None,
                storyboard=storyboard,
            )
        )
    return CalendarSlate(
        project=resolve_project_slug(project_slug, root=root),
        page_name=pm.page_name,
        pm_name=pm.name,
        slate_date=date.today(),
        tickets=tickets,
        notes=f"{pm.page_name} daily operating slate from weekly_calendar.yaml",
    )


def _mission_type_cards() -> list[dict[str, str]]:
    return [
        {
            "key": MissionType.NEW_PROJECT_DISCOVERY.value,
            "label": "New project discovery",
            "detail": "Find page concepts with audience, monetization, and viral potential.",
        },
        {
            "key": MissionType.CONTENT_CALENDAR_PLAN.value,
            "label": "Content calendar plan",
            "detail": "Turn PM goals and signals into a daily or weekly production slate.",
        },
        {
            "key": MissionType.PRODUCTION_BATCH.value,
            "label": "Production batch",
            "detail": "Move article, infographic, short video, and long video tickets in parallel.",
        },
        {
            "key": MissionType.PERFORMANCE_REVIEW.value,
            "label": "Performance review",
            "detail": "Bucket results into scale, repair, or lesson learned.",
        },
    ]


def _workflow_lanes() -> list[dict[str, object]]:
    return [
        {
            "label": "Discovery",
            "mission_type": MissionType.NEW_PROJECT_DISCOVERY.value,
            "owner": "Robin",
            "steps": [
                "Mia scans signals",
                "Market & Monetization validates business potential",
                "Sage Ledger checks duplicates",
                "Nora reviews feasibility",
            ],
        },
        {
            "label": "Planning",
            "mission_type": MissionType.CONTENT_CALENDAR_PLAN.value,
            "owner": "Slay",
            "steps": [
                "Slay sets daily goals",
                "Zoe proposes angles",
                "Robin creates tickets",
                "Nora checks coverage",
            ],
        },
        {
            "label": "Production",
            "mission_type": MissionType.PRODUCTION_BATCH.value,
            "owner": "Vera Reel",
            "steps": [
                "Bella writes words",
                "Lila builds visual direction",
                "Vera Reel prepares scene timing and Veo3 package",
                "Roxy and Emma package release support",
            ],
        },
        {
            "label": "Learning",
            "mission_type": MissionType.PERFORMANCE_REVIEW.value,
            "owner": "Iris Gauge",
            "steps": [
                "Iris Gauge reads metrics",
                "Sage Ledger links tickets, assets, and lessons",
                "Roxy interprets packaging",
                "Slay chooses scale, repair, or lesson",
            ],
        },
    ]


def _ticket_rows(slate: CalendarSlate | None) -> list[dict[str, object]]:
    if slate is None:
        return []
    return [
        {
            "ticket_id": ticket.ticket_id,
            "project": ticket.project,
            "ticket_type": ticket.ticket_type.value.replace("_", " "),
            "content_type": ticket.content_type.value,
            "title": ticket.title,
            "owner": ticket.owner,
            "decision_owner": ticket.decision_owner,
            "priority": ticket.priority,
            "platform_primary": ticket.platform_primary,
            "status": ticket.status.value,
            "platforms": ", ".join(ticket.platforms),
            "storyboard_count": len(ticket.storyboard),
            "acceptance_count": len(ticket.acceptance_criteria),
            "asset_count": len(ticket.asset_requirements),
            "create_mission_url": f"/aurora/daily-slate/{ticket.project}/tickets/{ticket.ticket_id}/create-mission",
            "create_label": f"Create {ticket.ticket_type.value.replace('_', ' ')} mission",
        }
        for ticket in slate.tickets
    ]


def _slate_counts(slate: CalendarSlate | None) -> dict[str, int]:
    counts = slate.counts_by_type() if slate else {}
    return {
        "articles": counts.get(ProductionTicketType.ARTICLE, 0),
        "infographics": counts.get(ProductionTicketType.INFOGRAPHIC, 0),
        "short_videos": counts.get(ProductionTicketType.SHORT_VIDEO, 0),
        "long_videos": counts.get(ProductionTicketType.LONG_VIDEO, 0),
    }


def _mission_ticket_index(root: Path) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for job in list_all_jobs(root):
        ticket_source = getattr(job, "production_ticket", None)
        if not isinstance(ticket_source, dict):
            ticket_source = getattr(job, "video_package", None)
        if not isinstance(ticket_source, dict):
            continue
        ticket_id = str(ticket_source.get("ticket_id") or "")
        project = resolve_project_slug(str(ticket_source.get("project") or job.project), root=root)
        index_key = f"{project}:{ticket_id}"
        if not ticket_id or index_key in index:
            continue
        index[index_key] = {
            "job_id": job.id,
            "mission_url": f"/jobs/{job.id}",
            "mission_status": getattr(job.status, "value", str(job.status)).replace("_", " "),
            "mission_stage": str(job.stage).replace("_", " "),
        }
    return index


def _annotate_ticket_missions(tickets: list[dict[str, object]], mission_index: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    annotated = []
    for ticket in tickets:
        row = dict(ticket)
        index_key = f"{ticket.get('project')}:{ticket.get('ticket_id')}"
        mission = mission_index.get(index_key)
        row["has_mission"] = mission is not None
        row["mission"] = mission
        annotated.append(row)
    return annotated


def _next_slate_ticket(tickets: list[dict[str, object]]) -> dict[str, object] | None:
    if not tickets:
        return None
    return next((ticket for ticket in tickets if not ticket.get("has_mission")), tickets[0])


def _daily_slate_cards(root: Path) -> list[dict[str, object]]:
    cards = []
    mission_index = _mission_ticket_index(root)
    for project_slug in list_project_slugs(root):
        slate = _calendar_slate(root, project_slug)
        if slate is None:
            continue
        tickets = _annotate_ticket_missions(_ticket_rows(slate), mission_index)
        video_packages = _daily_slate_video_package_rows(slate)
        for package in video_packages:
            index_key = f"{slate.project}:{package.get('ticket_id')}"
            mission = mission_index.get(index_key)
            package["has_mission"] = mission is not None
            package["mission"] = mission
        cards.append(
            {
                "project": slate.project,
                "page_name": slate.page_name,
                "pm_name": slate.pm_name,
                "slate_date": slate.slate_date,
                "notes": slate.notes,
                "minimum_met": slate.satisfies_daily_minimum(),
                "counts": _slate_counts(slate),
                "ticket_count": len(tickets),
                "tickets": tickets,
                "next_ticket": _next_slate_ticket(tickets),
                "next_package": next((package for package in video_packages if not package.get("has_mission")), None),
                "video_packages": video_packages,
                "qa_status": _qa_status(slate),
            }
        )
    return cards


def _approval_default_video_path(job: ContentJob) -> str:
    return f"output/{job.pm.page_name}/{job.id}/final-video.mp4"


def _approval_default_caption(job: ContentJob) -> str:
    package = getattr(job, "video_package", None)
    title = str(package.get("title") if isinstance(package, dict) else job.brief)
    if "Stadium Sweethearts" in job.pm.page_name:
        return f"Fictional adult fan-cam replay: {title}. AI-generated, safe game-day energy, no real team marks."
    return f"{title} - ready for review before publish handoff."


def _approval_default_hashtags(job: ContentJob) -> str:
    if "Stadium Sweethearts" in job.pm.page_name:
        return "#StadiumSweethearts, #AIFanCam, #GameDay, #FictionalAdult"
    if "Slay" in job.pm.page_name:
        return "#SlayHack, #BeautyHack, #AIContent"
    return "#NayzFreedom, #AIContent"


def _approval_default_faq(job: ContentJob) -> str:
    return (
        "Q: Is this a real person?\n"
        "A: No. This is fictional AI-generated content featuring adult characters only.\n\n"
        "Q: Does this use real team marks or official footage?\n"
        "A: No. The package should avoid real logos, official marks, and real-person likenesses.\n\n"
        "Q: Who should review comments?\n"
        "A: Emma handles normal replies. Nora or the PM reviews anything risky before response."
    )


def _approval_risk_label(status: str, action_method: str) -> str:
    if status in {"Ready", "Dry-run complete"} or "dry" in status.lower():
        return "safe dry-run"
    if status == "Waiting real video":
        return "manual upload"
    if status == "Ready packaging":
        return "manual package"
    if status in {"Ready to publish", "Package complete", "Captain hold", "Needs edits"}:
        return "locked live publish"
    if status == "Scheduled handoff":
        return "handoff only"
    if action_method == "post":
        return "review gate"
    return "read only"


def _approval_lane_key(lane: str, status: str) -> str:
    if lane == "Nora review":
        return "nora"
    if lane == "Generation":
        return "generation"
    if lane == "Roxy + Emma":
        return "packaging"
    if lane == "Captain approval":
        return "captain"
    if lane in {"Scheduled", "Handoff"} or status == "Scheduled handoff":
        return "handoff"
    return "revision"


def _approval_lane_groups(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    lane_order = [
        ("nora", "Nora", "QA gate before generation"),
        ("generation", "Generation", "Safe dry-run and manual video intake"),
        ("packaging", "Roxy + Emma", "Caption, hashtags, FAQ, and publish prep"),
        ("captain", "Captain", "Captain approval before any schedule handoff"),
        ("handoff", "Handoff", "Scheduled dashboard handoff, still not live publishing"),
        ("revision", "Revision", "Hold or edit loop before approval"),
    ]
    return [
        {
            "key": key,
            "label": label,
            "detail": detail,
            "rows": [row for row in rows if row.get("lane_key") == key],
        }
        for key, label, detail in lane_order
    ]


def _approval_lane_filters(groups: list[dict[str, object]], selected: str) -> list[dict[str, object]]:
    total = sum(len(group["rows"]) for group in groups)
    return [{"key": "all", "label": "All lanes", "count": total, "active": selected == "all"}] + [
        {
            "key": str(group["key"]),
            "label": str(group["label"]),
            "count": len(group["rows"]),
            "active": selected == group["key"],
        }
        for group in groups
    ]


def _approval_queue_rows(root: Path) -> list[dict[str, object]]:
    rows = []
    for job in list_all_jobs(root):
        generation_request = getattr(job, "generation_request", None)
        request_status = str(generation_request.get("status", "")) if isinstance(generation_request, dict) else ""
        publish_status = _publish_execution_status(job)
        row: dict[str, object] | None = None

        if request_status == "nora_review":
            row = {
                "lane": "Nora review",
                "state": "missing",
                "status": "Needs review",
                "next_action": "Nora can mark the package ready for generation.",
                "action_label": "Mark ready",
                "action_url": f"/jobs/{job.id}/ready-for-generation",
                "action_method": "post",
            }
        elif _waiting_for_real_video(job):
            row = {
                "lane": "Generation",
                "state": "missing",
                "status": "Waiting real video",
                "next_action": "Attach the final generated video before publish packaging.",
                "action_label": "Record real video",
                "action_url": f"/jobs/{job.id}/record-generation-result",
                "action_method": "generation_result",
            }
        elif request_status in {"ready_for_generation", "dry_run_completed", "failed"}:
            row = {
                "lane": "Generation",
                "state": "ready" if request_status != "failed" else "failed",
                "status": _generation_status_label(request_status),
                "next_action": "Run or rerun the safe generation dry-run before real video handoff.",
                "action_label": "Run generation dry-run",
                "action_url": f"/jobs/{job.id}/run-generation-dry-run",
                "action_method": "post",
            }
        elif _real_generation_completed(job) and not _publish_package_completed(job):
            row = {
                "lane": "Roxy + Emma",
                "state": "missing",
                "status": "Ready packaging",
                "next_action": "Record caption, hashtags, FAQ, and publish notes.",
                "action_label": "Record publish package",
                "action_url": f"/jobs/{job.id}/record-publish-package",
                "action_method": "publish_package",
            }
        elif _publish_package_completed(job) and not publish_status:
            row = {
                "lane": "Captain approval",
                "state": "missing",
                "status": "Package complete",
                "next_action": "Create a publish job for explicit scheduling approval.",
                "action_label": "Create publish job",
                "action_url": f"/jobs/{job.id}/create-publish-job",
                "action_method": "post",
            }
        elif publish_status == "ready_to_publish":
            row = {
                "lane": "Captain approval",
                "state": "missing",
                "status": "Ready to publish",
                "next_action": "Captain approval required before schedule handoff. Dashboard scheduling is not a live post.",
                "action_label": "Captain review",
                "action_url": f"/jobs/{job.id}/captain-approval",
                "action_method": "get",
            }
        elif publish_status == "captain_hold":
            row = {
                "lane": "Captain approval",
                "state": "missing",
                "status": "Captain hold",
                "next_action": "Hold is active. Review the note before changing this package.",
                "action_label": "Captain review",
                "action_url": f"/jobs/{job.id}/captain-approval",
                "action_method": "get",
            }
        elif publish_status == "needs_edits":
            row = {
                "lane": "Revision",
                "state": "missing",
                "status": "Needs edits",
                "next_action": "Package needs edits before schedule handoff approval.",
                "action_label": "Captain review",
                "action_url": f"/jobs/{job.id}/captain-approval",
                "action_method": "get",
            }
        elif publish_status == "scheduled":
            row = {
                "lane": "Handoff",
                "state": "ready",
                "status": "Scheduled handoff",
                "next_action": "Inspect the locked live publish gate before any separate platform action.",
                "action_label": "Open live publish gate",
                "action_url": f"/jobs/{job.id}/live-publish-approval",
                "action_method": "get",
            }

        if row is None:
            continue
        lane_key = _approval_lane_key(str(row["lane"]), str(row["status"]))
        row.update(
            {
                "job_id": job.id,
                "brief": job.brief,
                "page_name": job.pm.page_name,
                "stage": job.stage,
                "lane_key": lane_key,
                "risk_label": _approval_risk_label(str(row["status"]), str(row["action_method"])),
                "detail_url": f"/jobs/{job.id}",
                "default_video_path": _approval_default_video_path(job),
                "default_caption": _approval_default_caption(job),
                "default_hashtags": _approval_default_hashtags(job),
                "default_faq": _approval_default_faq(job),
                "default_publish_notes": "Dashboard package only. Do not schedule or post live until Captain Nayz approves.",
            }
        )
        rows.append(row)

    order = {
        "Needs review": 0,
        "Ready": 1,
        "dry run completed": 2,
        "Waiting real video": 3,
        "Ready packaging": 4,
        "Package complete": 5,
        "Ready to publish": 6,
        "Captain hold": 7,
        "Needs edits": 8,
        "Scheduled handoff": 9,
    }
    return sorted(rows, key=lambda item: (order.get(str(item["status"]), 99), str(item["page_name"]), str(item["job_id"])))


MANUAL_POSTING_LANES = [
    ("needs_attention", "Needs Captain", "Manual posting or tracking needs review before closeout"),
    ("kit_synced", "Kit synced", "Drive kit is ready, but no manual post URL is recorded"),
    ("waiting_tracking", "Waiting tracking", "Manual post is recorded and snapshot checks are still pending"),
    ("tracking_complete", "Tracking complete", "Manual post has the required 24h and 72h proof"),
]


def _manual_posting_lane_filters(
    groups: list[dict[str, object]],
    selected: str,
) -> list[dict[str, object]]:
    total = sum(len(group["rows"]) for group in groups)
    return [
        {"key": "all", "label": "All", "count": total, "active": selected == "all"},
        *[
            {
                "key": str(group["key"]),
                "label": str(group["label"]),
                "count": len(group["rows"]),
                "active": selected == group["key"],
            }
            for group in groups
        ],
    ]


def _manual_posting_job_posts(job: ContentJob) -> dict[str, dict]:
    kit = job.manual_post_kit if isinstance(job.manual_post_kit, dict) else {}
    manual_post = kit.get("manual_post") if isinstance(kit, dict) else None
    if not isinstance(manual_post, dict):
        return {}
    return {
        str(platform): value
        for platform, value in manual_post.items()
        if isinstance(value, dict) and value.get("status") == "posted"
    }


def _manual_posting_publish_platforms(job: ContentJob) -> dict[str, dict]:
    publish_result = job.publish_result if isinstance(job.publish_result, dict) else {}
    return {
        str(platform): value
        for platform, value in publish_result.items()
        if isinstance(value, dict) and value.get("status") == "published" and value.get("manual") is True
    }


def _manual_posting_first_post(posts: dict[str, dict], publish_platforms: dict[str, dict]) -> dict[str, object]:
    combined = list(posts.items()) + [
        (platform, value) for platform, value in publish_platforms.items() if platform not in posts
    ]
    if not combined:
        return {"platforms": [], "post_url": "", "posted_at": ""}
    platform, value = sorted(
        combined,
        key=lambda item: str(item[1].get("posted_at") or item[1].get("published_at") or ""),
    )[0]
    return {
        "platforms": sorted({str(item[0]) for item in combined}),
        "post_url": str(value.get("post_url") or value.get("url") or ""),
        "posted_at": str(value.get("posted_at") or value.get("published_at") or ""),
        "platform": str(platform),
    }


def _manual_posting_proof_summary(
    *,
    drive_status: str,
    post_url: object,
    snapshots: int,
    queued_count: int,
    closeout: dict,
) -> dict[str, object]:
    learning_note = str(closeout.get("learning_note") or "").strip()
    return {
        "drive_synced": drive_status == "synced",
        "post_url_present": bool(str(post_url or "").strip()),
        "snapshot_24h_present": snapshots >= 1,
        "snapshot_72h_present": snapshots >= 2,
        "queued_tracking": queued_count,
        "learning_note_captured": bool(learning_note),
    }


def _manual_posting_row(job: ContentJob, queue_entries: list[dict]) -> dict[str, object] | None:
    kit = job.manual_post_kit if isinstance(job.manual_post_kit, dict) else {}
    drive_sync = kit.get("drive_sync") if isinstance(kit, dict) else None
    closeout = kit.get("closeout") if isinstance(kit.get("closeout"), dict) else {}
    drive_status = str(drive_sync.get("status", "")) if isinstance(drive_sync, dict) else ""
    posts = _manual_posting_job_posts(job)
    publish_platforms = _manual_posting_publish_platforms(job)
    has_manual_post = bool(posts or publish_platforms)
    if not has_manual_post and drive_status not in {"synced", "failed"}:
        return None

    job_queue = [entry for entry in queue_entries if entry.get("job_id") == job.id]
    queue_summary = summarize_track_queue(job_queue, limit=4)
    counts = queue_summary["counts"]
    snapshots = len(job.performance)
    first_post = _manual_posting_first_post(posts, publish_platforms)
    proof_summary = _manual_posting_proof_summary(
        drive_status=drive_status,
        post_url=first_post.get("post_url", ""),
        snapshots=snapshots,
        queued_count=int(counts["total"]),
        closeout=closeout,
    )
    closeout_status = str(closeout.get("status") or "open")
    next_entry = min(
        job_queue,
        key=lambda entry: parse_track_at(entry.get("track_at")) or datetime.max.replace(tzinfo=timezone.utc),
        default=None,
    )

    if closeout_status == "closed":
        lane = "tracking_complete"
        state = "ready"
        if isinstance(closeout.get("learning_applied"), dict):
            status = "Learning applied"
            next_action = "Manual proof is closed and the accepted lesson is applied to a Daily Slate mission."
        else:
            status = "Needs Captain learning review"
            next_action = "Promote the daily brief lesson, then apply it to the next Daily Slate mission."
    elif drive_status == "failed":
        lane = "needs_attention"
        state = "failed"
        status = "Drive sync failed"
        next_action = "Repair Drive credentials or job ownership, then sync the manual kit again."
    elif drive_status == "synced" and not has_manual_post:
        lane = "kit_synced"
        state = "missing"
        status = "Kit synced, not posted"
        next_action = "Captain posts from the Drive kit, then records the platform URL."
    elif has_manual_post and int(counts["overdue"]) > 0:
        lane = "needs_attention"
        state = "failed"
        status = "Tracking overdue"
        next_action = "Run or inspect the tracking scheduler before closing this manual post."
    elif has_manual_post and (int(counts["due_now"]) > 0 or int(counts["invalid"]) > 0):
        lane = "needs_attention"
        state = "missing"
        status = "Tracking needs attention"
        next_action = "Check the due or invalid tracking queue entry before closing this job."
    elif has_manual_post and job_queue:
        lane = "waiting_tracking"
        state = "missing"
        status = "Manual posted, waiting tracking"
        next_due = str(next_entry.get("track_at")) if next_entry else "next snapshot"
        next_action = f"Wait for queued tracking snapshot at {next_due}."
    elif has_manual_post and snapshots >= 2:
        lane = "tracking_complete"
        state = "ready"
        status = "Tracking complete"
        next_action = "Review the performance proof and capture the learning note."
    elif has_manual_post and snapshots == 1:
        lane = "needs_attention"
        state = "missing"
        status = "72h tracking missing"
        next_action = "One snapshot is recorded, but the 72h proof is not queued or present."
    else:
        lane = "needs_attention"
        state = "missing"
        status = "Tracking queue missing"
        next_action = "Manual post is recorded, but no snapshot checks are queued."

    return {
        "job_id": job.id,
        "brief": job.brief,
        "page_name": job.pm.page_name,
        "stage": job.stage,
        "lane": lane,
        "state": state,
        "status": status,
        "next_action": next_action,
        "detail_url": f"/jobs/{job.id}",
        "drive_status": drive_status or "not synced",
        "drive_link": str(drive_sync.get("web_view_link") or "") if isinstance(drive_sync, dict) else "",
        "drive_synced_at": str(drive_sync.get("synced_at") or "") if isinstance(drive_sync, dict) else "",
        "platforms": first_post.get("platforms", []),
        "post_url": first_post.get("post_url", ""),
        "posted_at": first_post.get("posted_at", ""),
        "snapshot_count": snapshots,
        "queue_summary": queue_summary,
        "queued_count": int(counts["total"]),
        "proof_summary": proof_summary,
        "closeout": {
            "status": closeout_status,
            "closed_at": str(closeout.get("closed_at") or ""),
            "closed_by": str(closeout.get("closed_by") or ""),
            "learning_note": str(closeout.get("learning_note") or ""),
            "proof_summary": closeout.get("proof_summary") if isinstance(closeout.get("proof_summary"), dict) else {},
            "learning_applied": closeout.get("learning_applied") if isinstance(closeout.get("learning_applied"), dict) else {},
        },
        "can_closeout": has_manual_post and snapshots >= 2 and closeout_status != "closed",
        "can_requeue_tracking": has_manual_post and not job_queue and snapshots < 2,
    }


def _manual_posting_queue_rows(root: Path) -> list[dict[str, object]]:
    queue_entries = read_queue(root)
    rows = [
        row
        for job in list_all_jobs(root)
        if (row := _manual_posting_row(job, queue_entries)) is not None
    ]
    order = {key: index for index, (key, _, _) in enumerate(MANUAL_POSTING_LANES)}
    return sorted(rows, key=lambda item: (order.get(str(item["lane"]), 99), str(item["page_name"]), str(item["job_id"])))


def _manual_posting_lane_groups(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "key": key,
            "label": label,
            "detail": detail,
            "rows": [row for row in rows if row["lane"] == key],
        }
        for key, label, detail in MANUAL_POSTING_LANES
    ]


def _qa_status(slate: CalendarSlate | None) -> list[dict[str, str]]:
    if slate is None:
        return [{"state": "Missing", "name": "Daily slate", "detail": "No slate is configured yet."}]
    long_tickets = [ticket for ticket in slate.tickets if ticket.ticket_type == ProductionTicketType.LONG_VIDEO]
    storyboard_ready = all(ticket.storyboard for ticket in long_tickets)
    video_packages = [
        _video_package_for_ticket(ticket)
        for ticket in slate.tickets
        if ticket.ticket_type in {ProductionTicketType.SHORT_VIDEO, ProductionTicketType.LONG_VIDEO}
    ]
    package_ready = bool(video_packages) and all(package is not None and package.scenes for package in video_packages)
    return [
        {
            "state": "Ready" if slate.satisfies_daily_minimum() else "Failed",
            "name": "Daily minimum",
            "detail": "Articles, infographics, short video, and long video floor is covered.",
        },
        {
            "state": "Ready" if storyboard_ready else "Failed",
            "name": "Long video storyboard",
            "detail": f"{len(long_tickets)} long video ticket{'s' if len(long_tickets) != 1 else ''} checked.",
        },
        {
            "state": "Ready" if package_ready else "Missing",
            "name": "Nora QA gate",
            "detail": "Video packages are ready for Nora to approve generation." if package_ready else "Tickets are planned; QA status starts after production output exists.",
        },
    ]


def _performance_loop(jobs) -> list[dict[str, str]]:
    completed = sum(getattr(job.status, "value", str(job.status)) == "completed" for job in jobs)
    failed = sum(getattr(job.status, "value", str(job.status)) == "failed" for job in jobs)
    reviewed = sum(1 for job in jobs if job.performance)
    reviews = [
        PerformanceReview(
            ticket_id="scale-candidates",
            project="slay_hack",
            platform="all",
            bucket=PerformanceBucket.SCALE,
            summary=f"{completed} completed missions available for scale review.",
            recommended_next_action="Repeat winning hooks and formats.",
        ),
        PerformanceReview(
            ticket_id="repair-candidates",
            project="slay_hack",
            platform="all",
            bucket=PerformanceBucket.REPAIR,
            summary=f"{failed} failed missions need repair.",
            recommended_next_action="Review failed publish and QA notes before relaunch.",
        ),
        PerformanceReview(
            ticket_id="lesson-loop",
            project="slay_hack",
            platform="all",
            bucket=PerformanceBucket.LESSON_LEARNED,
            summary=f"{reviewed} missions have recorded engagement metrics.",
            recommended_next_action="Turn repeated patterns into PM guidance.",
        ),
    ]
    return [
        {
            "state": "Ready" if review.bucket == PerformanceBucket.SCALE else "Failed" if review.bucket == PerformanceBucket.REPAIR and failed else "Missing",
            "bucket": review.bucket.value.replace("_", " "),
            "summary": review.summary,
            "next_action": review.recommended_next_action,
        }
        for review in reviews
    ]


def _cross_team_requests() -> list[CrossTeamRequest]:
    return [
        CrossTeamRequest(
            request_id="central-market-scan",
            project="slay_hack",
            from_role="Slay",
            to_role="Market & Monetization Analyst",
            question="Validate audience, competitor, monetization, and viral potential before scaling a new content pillar.",
        ),
        CrossTeamRequest(
            request_id="archive-duplicate-check",
            project="slay_hack",
            from_role="Slay",
            to_role="Sage Ledger",
            question="Check Drive, Notion, and prior output for duplicate topics before production starts.",
        ),
    ]


def _aurora_workflow_snapshot(root: Path) -> dict[str, object]:
    jobs = list_all_jobs(root)
    slate = _calendar_slate(root)
    video_packages = _video_package_rows(slate)
    return {
        "mission_types": _mission_type_cards(),
        "workflow_lanes": _workflow_lanes(),
        "slate": slate,
        "slate_counts": _slate_counts(slate),
        "tickets": _ticket_rows(slate),
        "video_packages": video_packages,
        "featured_video_package": video_packages[0] if video_packages else None,
        "qa_status": _qa_status(slate),
        "performance_loop": _performance_loop(jobs),
        "cross_team_requests": _cross_team_requests(),
    }




def _decode_meta_signed_request(signed_request: str) -> dict:
    if "." not in signed_request:
        raise ValueError("signed_request must contain a signature and payload")

    encoded_sig, encoded_payload = signed_request.split(".", 1)
    app_secret = os.environ.get("META_APP_SECRET", "")
    if app_secret:
        expected_sig = hmac.new(
            app_secret.encode("utf-8"),
            msg=encoded_payload.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        actual_sig = base64.urlsafe_b64decode(encoded_sig + "=" * (-len(encoded_sig) % 4))
        if not hmac.compare_digest(actual_sig, expected_sig):
            raise ValueError("signed_request signature mismatch")

    payload = base64.urlsafe_b64decode(
        encoded_payload + "=" * (-len(encoded_payload) % 4)
    )
    return json.loads(payload.decode("utf-8"))
