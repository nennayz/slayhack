from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
import yaml
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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
from models.content_job import ContentJob, ContentType, GrowthStrategy, JobStatus, QAResult
from project_loader import (
    list_project_slugs,
    load_project,
    load_project_page_name,
    project_slug_matches,
    resolve_project_slug,
)
from work_activity import read_recent_work_activity, work_activity_status, write_work_activity

DASHBOARD_USER = os.environ.get("DASHBOARD_USER")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD")
if not DASHBOARD_USER or not DASHBOARD_PASSWORD:
    raise RuntimeError(
        "DASHBOARD_USER and DASHBOARD_PASSWORD must be set in environment before starting the dashboard."
    )

_ROOT = Path(__file__).resolve().parent

VALID_CONTENT_TYPES = {"video", "article", "image", "infographic"}
MAX_BRIEF_LEN = 2000
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
    "restart_dashboard": {
        "label": "Restart dashboard",
        "unit": "nayzfreedom-dashboard.service",
        "verb": "restart",
        "delayed": True,
    },
}

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(_ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(_ROOT / "templates"))
security = HTTPBasic()


def _status_label(value: object) -> str:
    raw = getattr(value, "value", str(value))
    return raw.replace("_", " ").title()


templates.env.filters["status_label"] = _status_label


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
        if platform == "facebook" and status == "scheduled":
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


templates.env.globals["publish_status_items"] = _publish_status_items


def _publish_history_items(job) -> list[dict[str, str]]:
    items = []
    for item in _publish_status_items(job):
        value = (job.publish_result or {}).get(item["platform"], {})
        if not isinstance(value, dict):
            continue
        detail = value.get("due_at") or value.get("id") or value.get("reason") or value.get("error") or ""
        items.append({**item, "detail": str(detail)})
    return items


templates.env.globals["publish_history_items"] = _publish_history_items


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


MISSION_FILTER_KEYS = {"all", "running", "failed", "ready_to_publish", "scheduled", "queued", "published", "publish_failed"}


def _mission_filters(jobs, selected: str) -> list[dict[str, object]]:
    filters = [
        ("all", "All"),
        ("running", "Running"),
        ("failed", "Failed"),
        ("ready_to_publish", "Ready to publish"),
        ("scheduled", "Scheduled"),
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
    ops_reports: list[dict[str, str]],
) -> list[dict[str, str]]:
    summary = summarize_jobs(jobs)
    unit_failures = sum(item["state"] != "Ready" for item in units)
    publish_counts = publish_summary["counts"]
    ig_attention = publish_counts["instagram_failed"] + publish_counts["instagram_retrying"]
    if summary["failed"] or incident_summary["open"] or unit_failures or backup["state"] == "Failed" or publish_counts["instagram_failed"]:
        state = "Failed"
        action = "Review failed missions, open incidents, service state, or publish failures."
    elif backup["state"] != "Ready" or publish_counts["instagram_retrying"]:
        state = "Missing"
        action = "Check stale backup or queued Instagram retry before launching more work."
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
        "smoke_results": smoke_results,
        "action_buttons": _ops_action_buttons(),
        "action_result": None,
        "ops_audit": _recent_ops_audit(root),
        "ops_log": _ops_log_status(root),
        "work_activity": read_recent_work_activity(root),
        "work_activity_log": work_activity_status(root),
        "ops_incidents": _recent_ops_incidents(root),
        "ops_reports": ops_reports,
        "incident_summary": incident_summary,
        "incident_result": None,
        "ops_daily_summary": _ops_daily_summary(jobs, units, backup, incident_summary, publish_summary, ops_reports),
        "workflow_owners": _workflow_owner_summary(jobs),
        "security_hygiene": _security_hygiene_checks(root),
    }


@app.get("/healthz")
def healthz():
    return JSONResponse({"status": "ok", "service": "nayzfreedom-dashboard"})


@app.get("/media/public/{job_id}/{filename}")
def public_media(job_id: str, filename: str, request: Request):
    try:
        path = _public_media_path(_root(request), job_id, filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Public media not found")
    return FileResponse(path)


@app.api_route("/privacy", methods=["GET", "HEAD"], response_class=HTMLResponse)
def privacy_policy(request: Request):
    return templates.TemplateResponse(request, "privacy.html", {})


@app.api_route("/data-deletion", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/data_deletion.html", methods=["GET", "HEAD"], response_class=HTMLResponse)
def data_deletion(request: Request):
    return templates.TemplateResponse(request, "data_deletion.html", {})


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


@app.post("/data-deletion-callback")
async def data_deletion_callback(signed_request: str = Form(...)):
    try:
        payload = _decode_meta_signed_request(signed_request)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user_id = str(payload.get("user_id") or payload.get("user", {}).get("id") or "unknown")
    confirmation_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
    confirmation_code = f"slayhack-delete-{confirmation_hash}"
    return JSONResponse(
        {
            "url": "https://fleet.nayzfreedom.cloud/data-deletion",
            "confirmation_code": confirmation_code,
        }
    )


def verify_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    correct_user = secrets.compare_digest(credentials.username, DASHBOARD_USER)
    correct_pass = secrets.compare_digest(credentials.password, DASHBOARD_PASSWORD)
    if not (correct_user and correct_pass):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    return credentials.username


def _root(request: Request) -> Path:
    return getattr(request.app.state, "root", _ROOT)


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


def _latest_learning_brief(root: Path) -> dict | None:
    daily_dir = root / "docs" / "learning" / "daily"
    if not daily_dir.exists():
        return None
    briefs = sorted(daily_dir.glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not briefs:
        return None
    path = briefs[0]
    return {
        "title": path.stem.replace("-", " ").title(),
        "path": str(path.relative_to(root)),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        "body": path.read_text(encoding="utf-8"),
    }


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

    outputs = [
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
            "state": "Ready" if generation_status in {"ready_for_generation", "dry_run_completed", "completed"} else "Waiting" if video_package_ready else "Not needed",
            "detail": "Nora approved the package for generation." if generation_status in {"ready_for_generation", "dry_run_completed", "completed"} else "Waiting for Nora to mark ready for generation." if video_package_ready else "No video generation gate is needed yet.",
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
            "state": "Ready" if DASHBOARD_USER and DASHBOARD_PASSWORD else "Missing",
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
        "scheduled": "Scheduled publish",
        "published": "Published",
        "failed": "Publish failed",
    }
    return labels.get(status, "Create publish job" if _publish_package_completed(job) else "Not ready")


def _publish_execution_state(job: ContentJob) -> str:
    status = _publish_execution_status(job)
    if status in {"scheduled", "published"}:
        return "ready"
    if status == "ready_to_publish":
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


GENERATION_FILTERS = (
    ("all", "All"),
    ("waiting_real_video", "Waiting real video"),
    ("ready_packaging", "Ready packaging"),
    ("package_complete", "Package complete"),
    ("ready_to_publish", "Ready to publish"),
    ("scheduled", "Scheduled publish"),
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
        rows.append(
            {
                "job": job,
                "status": status,
                "status_label": _generation_status_label(status),
                "state": _generation_state(status),
                "tool_hint": request.get("tool_hint", "generation"),
                "scene_count": request.get("scene_count", 0),
                "asset_count": request.get("asset_count", 0),
                "attempt": request.get("attempt", 0),
                "next_action": request.get("next_action", "Review generation package."),
                "result": result if isinstance(result, dict) else None,
                "can_run": status in {"ready_for_generation", "failed", "dry_run_completed"},
                "can_record": status in {"ready_for_generation", "dry_run_completed", "failed"},
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
        "next_action": "Publish package is ready for scheduling or manual publish.",
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
        "next_action": "Captain can schedule publish when platform readiness is confirmed.",
    }
    job.stage = "ready_to_publish"
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
            "next_action": "Publish package is scheduled. Use platform publisher controls for live posting.",
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
            "ticket_type": ticket.ticket_type.value.replace("_", " "),
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


def _daily_slate_cards(root: Path) -> list[dict[str, object]]:
    cards = []
    for project_slug in list_project_slugs(root):
        slate = _calendar_slate(root, project_slug)
        if slate is None:
            continue
        tickets = _ticket_rows(slate)
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
                "video_packages": _daily_slate_video_package_rows(slate),
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
                "action_label": "Open mission",
                "action_url": f"/jobs/{job.id}",
                "action_method": "get",
            }
        elif publish_status == "scheduled":
            row = {
                "lane": "Scheduled",
                "state": "ready",
                "status": "Scheduled publish",
                "next_action": "Waiting for platform publisher controls; no external API call was made by this handoff.",
                "action_label": "Open mission",
                "action_url": f"/jobs/{job.id}",
                "action_method": "get",
            }

        if row is None:
            continue
        row.update(
            {
                "job_id": job.id,
                "brief": job.brief,
                "page_name": job.pm.page_name,
                "stage": job.stage,
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
        "Scheduled publish": 7,
    }
    return sorted(rows, key=lambda item: (order.get(str(item["status"]), 99), str(item["page_name"]), str(item["job_id"])))


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


@app.get("/", response_class=HTMLResponse)
def captains_deck(request: Request, _: str = Depends(verify_auth)):
    jobs = list_all_jobs(_root(request))
    performance = load_performance_all(_root(request))
    summary = summarize_jobs(jobs)
    signals = attention_jobs(jobs)
    active = active_jobs(jobs)
    brief = command_brief(jobs)
    ships = fleet_status(jobs)
    return templates.TemplateResponse(
        request,
        "captains_deck.html",
        {
            "jobs": jobs[:5],
            "summary": summary,
            "attention_jobs": signals,
            "active_jobs": active,
            "command_brief": brief,
            "fleet_status": ships,
            "performance": performance,
        },
    )


@app.get("/aurora", response_class=HTMLResponse)
def aurora_overview(request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    jobs = list_all_jobs(root)
    projects = _project_options(root)
    performance = load_performance_all(root)
    signals = attention_jobs(jobs)
    active = active_jobs(jobs)
    return templates.TemplateResponse(
        request,
        "aurora.html",
        {
            "jobs": jobs[:5],
            "summary": summarize_jobs(jobs),
            "attention_jobs": signals,
            "active_jobs": active,
            "command_brief": command_brief(jobs),
            "projects": projects,
            "performance": performance,
            "crew": CREW[:4],
        },
    )


@app.get("/aurora/workflow", response_class=HTMLResponse)
def aurora_workflow(request: Request, _: str = Depends(verify_auth)):
    return templates.TemplateResponse(request, "aurora_workflow.html", _aurora_workflow_snapshot(_root(request)))


@app.get("/aurora/daily-slate", response_class=HTMLResponse)
def aurora_daily_slate(request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    slate_cards = _daily_slate_cards(root)
    approval_queue = _approval_queue_rows(root)
    return templates.TemplateResponse(
        request,
        "daily_slate.html",
        {
            "slate_cards": slate_cards,
            "latest_brief": _latest_learning_brief(root),
            "approval_queue": approval_queue[:8],
            "total_tickets": sum(int(card["ticket_count"]) for card in slate_cards),
            "ready_pages": sum(1 for card in slate_cards if card["minimum_met"]),
            "approval_count": len(approval_queue),
        },
    )


@app.get("/aurora/approval-queue", response_class=HTMLResponse)
def aurora_approval_queue(request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    rows = _approval_queue_rows(root)
    return templates.TemplateResponse(
        request,
        "approval_queue.html",
        {
            "approval_queue": rows,
            "needs_review_count": sum(1 for row in rows if row["status"] == "Needs review"),
            "ready_publish_count": sum(1 for row in rows if row["status"] == "Ready to publish"),
        },
    )


@app.get("/aurora/generation", response_class=HTMLResponse)
def aurora_generation(request: Request, _: str = Depends(verify_auth)):
    rows = _generation_queue(_root(request))
    selected_filter = request.query_params.get("filter", "all")
    valid_filters = {key for key, _ in GENERATION_FILTERS}
    if selected_filter not in valid_filters:
        selected_filter = "all"
    filtered_rows = [item for item in rows if _generation_row_matches_filter(item, selected_filter)]
    return templates.TemplateResponse(
        request,
        "aurora_generation.html",
        {
            "generation_jobs": filtered_rows,
            "generation_filters": _generation_filter_cards(rows, selected_filter),
            "selected_filter": selected_filter,
            "ready_count": sum(1 for item in rows if item["status"] == "ready_for_generation"),
            "dry_run_count": sum(1 for item in rows if item["status"] == "dry_run_completed"),
            "completed_count": sum(1 for item in rows if item["status"] == "completed"),
            "waiting_real_count": sum(1 for item in rows if item["waiting_for_real_video"]),
            "ready_publish_count": sum(1 for item in rows if item["publish_execution"]["status"] == "ready_to_publish"),
            "scheduled_publish_count": sum(1 for item in rows if item["publish_execution"]["status"] == "scheduled"),
            "failed_count": sum(1 for item in rows if item["status"] == "failed"),
        },
    )


@app.post("/aurora/workflow/video-packages/{ticket_id}/create-mission")
def create_video_package_mission(ticket_id: str, request: Request, user: str = Depends(verify_auth)):
    root = _root(request)
    try:
        job = _create_video_package_mission(root, "slay_hack", ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _write_work_event(
        root,
        "implementation_step",
        f"Created video package mission {job.id}",
        actor=user,
        result=ticket_id,
        next_action="Mark ready for generation after Nora review.",
        metadata={"job_id": job.id, "ticket_id": ticket_id},
    )
    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


@app.post("/aurora/daily-slate/{project_slug}/video-packages/{ticket_id}/create-mission")
def create_daily_slate_video_package_mission(
    project_slug: str,
    ticket_id: str,
    request: Request,
    user: str = Depends(verify_auth),
):
    root = _root(request)
    try:
        project_slug = resolve_project_slug(project_slug, root=root)
        job = _create_video_package_mission(root, project_slug, ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _write_work_event(
        root,
        "implementation_step",
        f"Created daily slate mission {job.id}",
        actor=user,
        result=f"{project_slug}:{ticket_id}",
        next_action="Mark ready for generation after Nora review.",
        metadata={"job_id": job.id, "project": project_slug, "ticket_id": ticket_id},
    )
    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


@app.get("/aurora/crew", response_class=HTMLResponse)
def aurora_crew(request: Request, _: str = Depends(verify_auth)):
    return templates.TemplateResponse(request, "crew.html", {"crew": CREW})


@app.get("/aurora/learning", response_class=HTMLResponse)
def aurora_learning(request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    return templates.TemplateResponse(
        request,
        "learning.html",
        {
            "latest_brief": _latest_learning_brief(root),
            "review_note": _read_review_note(root),
        },
    )


@app.get("/aurora/crew/{slug}", response_class=HTMLResponse)
def aurora_character_sheet(slug: str, request: Request, _: str = Depends(verify_auth)):
    member = get_crew_member(slug)
    if member is None:
        raise HTTPException(status_code=404, detail=f"Crew member {slug!r} not found")
    return templates.TemplateResponse(request, "crew_detail.html", {"member": member})


@app.get("/aurora/islands/{project_slug}", response_class=HTMLResponse)
def island_detail(project_slug: str, request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    project_slug = resolve_project_slug(project_slug)
    try:
        pm = load_project(project_slug, root=root)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Island {project_slug!r} not found")
    jobs = [
        job for job in list_all_jobs(root)
        if project_slug_matches(job.project, project_slug)
    ]
    summary = summarize_jobs(jobs)
    signals = attention_jobs(jobs)
    active = active_jobs(jobs)
    return templates.TemplateResponse(
        request,
        "island_detail.html",
        {
            "project_slug": project_slug,
            "pm": pm,
            "jobs": jobs[:5],
            "summary": summary,
            "attention_jobs": signals,
            "active_jobs": active,
            "command_brief": command_brief(jobs),
            "allowed_content_types": [content_type.value for content_type in pm.brand.allowed_content_types],
        },
    )


@app.get("/aurora/missions", response_class=HTMLResponse)
def aurora_missions(request: Request, _: str = Depends(verify_auth)):
    jobs = list_all_jobs(_root(request))
    selected_filter = request.query_params.get("filter", "all")
    if selected_filter not in MISSION_FILTER_KEYS:
        selected_filter = "all"
    filtered_jobs = _filter_jobs(jobs, selected_filter)
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {
            "jobs": filtered_jobs,
            "mission_filters": _mission_filters(jobs, selected_filter),
            "selected_filter": selected_filter,
        },
    )


@app.get("/aurora/metrics", response_class=HTMLResponse)
def aurora_metrics(request: Request, _: str = Depends(verify_auth)):
    data = load_performance_all(_root(request))
    return templates.TemplateResponse(request, "metrics.html", {"data": data})


@app.get("/aurora/new-mission", response_class=HTMLResponse)
def aurora_new_mission(request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    project_slugs = list_project_slugs(root)
    projects = _project_options(root)
    selected_project = request.query_params.get("project")
    if selected_project:
        selected_project = resolve_project_slug(selected_project, root=root)
    if selected_project not in project_slugs:
        selected_project = project_slugs[0] if project_slugs else None
    return templates.TemplateResponse(
        request,
        "trigger.html",
        {"projects": projects, "selected_project": selected_project},
    )


@app.get("/freedom", response_class=HTMLResponse)
def freedom_overview(request: Request, _: str = Depends(verify_auth)):
    return templates.TemplateResponse(request, "freedom.html", {})


@app.get("/lyra", response_class=HTMLResponse)
def lyra_overview(request: Request, _: str = Depends(verify_auth)):
    return templates.TemplateResponse(request, "lyra.html", {})


@app.get("/readiness", response_class=HTMLResponse)
def readiness(request: Request, _: str = Depends(verify_auth)):
    checks = _readiness_checks(_root(request))
    return templates.TemplateResponse(request, "readiness.html", {"checks": checks})


@app.get("/ops", response_class=HTMLResponse)
def ops_dashboard(request: Request, _: str = Depends(verify_auth)):
    snapshot = _ops_snapshot(_root(request))
    return templates.TemplateResponse(request, "ops.html", snapshot)


@app.post("/ops/smoke-test", response_class=HTMLResponse)
def ops_smoke_test(request: Request, user: str = Depends(verify_auth)):
    root = _root(request)
    smoke_results = _ops_smoke_results(root)
    failed = [item for item in smoke_results if item["state"] != "Ready"]
    audit_result = {
        "name": "Run smoke test",
        "state": "Failed" if failed else "Ready",
        "detail": f"{len(smoke_results) - len(failed)}/{len(smoke_results)} checks passed",
    }
    _write_ops_audit(root, user, "smoke_test", audit_result)
    _write_work_event(
        root,
        "production_smoke",
        "Dashboard Ops smoke test",
        actor=user,
        result=audit_result["detail"],
        next_action="Review failed checks before continuing." if failed else "Continue production operations.",
        metadata={"state": audit_result["state"]},
    )
    snapshot = _ops_snapshot(root, smoke_results=smoke_results)
    return templates.TemplateResponse(request, "ops.html", snapshot)


@app.post("/ops/actions/{action}", response_class=HTMLResponse)
def ops_action(action: str, request: Request, user: str = Depends(verify_auth)):
    root = _root(request)
    action_result = _run_ops_action(action)
    _write_ops_audit(root, user, action, action_result)
    _write_work_event(
        root,
        "deploy_step" if action == "restart_dashboard" else "implementation_step",
        f"Dashboard Ops action: {action}",
        actor=user,
        result=str(action_result.get("detail", action_result.get("state", ""))),
        metadata={"state": action_result.get("state", ""), "name": action_result.get("name", action)},
    )
    snapshot = _ops_snapshot(root)
    snapshot["action_result"] = action_result
    return templates.TemplateResponse(request, "ops.html", snapshot)


@app.post("/ops/incidents", response_class=HTMLResponse)
def ops_incident(
    request: Request,
    title: str = Form(""),
    severity: str = Form("info"),
    note: str = Form(""),
    user: str = Depends(verify_auth),
):
    root = _root(request)
    snapshot = _ops_snapshot(root)
    try:
        incident = _write_ops_incident(root, user, title, severity, note)
    except ValueError as exc:
        snapshot["incident_result"] = {"state": "Failed", "detail": str(exc)}
        return templates.TemplateResponse(request, "ops.html", snapshot, status_code=400)
    snapshot = _ops_snapshot(root)
    snapshot["incident_result"] = {"state": "Ready", "detail": f"Saved incident: {incident['title']}"}
    _write_work_event(
        root,
        "blocker",
        f"Ops incident opened: {incident['title']}",
        actor=user,
        result=f"{incident['severity']} {incident['status']}",
        next_action="Investigate or resolve from the Ops incident panel.",
    )
    return templates.TemplateResponse(request, "ops.html", snapshot)


@app.post("/ops/incidents/{incident_id}/status", response_class=HTMLResponse)
def ops_incident_status(
    incident_id: str,
    request: Request,
    status: str = Form(...),
    user: str = Depends(verify_auth),
):
    root = _root(request)
    snapshot = _ops_snapshot(root)
    try:
        incident = _update_ops_incident_status(root, incident_id, status, user)
    except ValueError as exc:
        snapshot["incident_result"] = {"state": "Failed", "detail": str(exc)}
        return templates.TemplateResponse(request, "ops.html", snapshot, status_code=400)
    snapshot = _ops_snapshot(root)
    snapshot["incident_result"] = {
        "state": "Ready",
        "detail": f"Marked incident {incident['title']} as {incident['status']}",
    }
    _write_work_event(
        root,
        "implementation_step",
        f"Ops incident status updated: {incident['title']}",
        actor=user,
        result=str(incident["status"]),
    )
    return templates.TemplateResponse(request, "ops.html", snapshot)


@app.get("/jobs", response_class=HTMLResponse)
def jobs_redirect(_: str = Depends(verify_auth)):
    return RedirectResponse("/aurora/missions", status_code=307)


@app.get("/jobs/partial", response_class=HTMLResponse)
def jobs_partial(request: Request, _: str = Depends(verify_auth)):
    jobs = list_all_jobs(_root(request))
    selected_filter = request.query_params.get("filter", "all")
    if selected_filter not in MISSION_FILTER_KEYS:
        selected_filter = "all"
    return templates.TemplateResponse(
        request,
        "_jobs_partial.html",
        {"jobs": _filter_jobs(jobs, selected_filter), "selected_filter": selected_filter},
    )


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(job_id: str, request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    try:
        job = find_job(job_id)
    except FileNotFoundError:
        try:
            job = _find_job_at_root(root, job_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    faq_path = root / "output" / job.pm.page_name / job_id / "faq.md"
    faq_content = faq_path.read_text() if faq_path.exists() else None
    voyage_steps = _build_voyage_steps(job)
    completed_count = sum(1 for item in voyage_steps if item["state"] == "done")
    mission_command = _mission_command(job, voyage_steps, completed_count)
    mission_outputs = _mission_outputs(job, faq_content)
    video_package = getattr(job, "video_package", None)
    generation_request = getattr(job, "generation_request", None)
    generation_result = getattr(job, "generation_result", None)
    publish_package = getattr(job, "publish_package", None)
    publish_execution = getattr(job, "publish_execution", None)
    return templates.TemplateResponse(
        request,
        "job_detail.html",
        {
            "job": job,
            "faq_content": faq_content,
            "voyage_steps": voyage_steps,
            "progress_count": completed_count,
            "total_stages": len(voyage_steps),
            "mission_command": mission_command,
            "mission_outputs": mission_outputs,
            "video_package": video_package,
            "generation_request": generation_request,
            "generation_result": generation_result,
            "publish_package": publish_package,
            "publish_execution": publish_execution,
            "can_record_publish_package": _real_generation_completed(job),
            "publish_execution_summary": _publish_execution_summary(job),
        },
    )


@app.post("/jobs/{job_id}/ready-for-generation")
def ready_for_generation(job_id: str, request: Request, user: str = Depends(verify_auth)):
    root = _root(request)
    try:
        job = _find_job_at_root(root, job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    if not getattr(job, "video_package", None):
        raise HTTPException(status_code=400, detail="No video package is attached to this mission")
    generation_request = dict(job.generation_request or {})
    generation_request["status"] = "ready_for_generation"
    generation_request["next_action"] = "Ready for the video generation tool to consume this package."
    generation_request["approved_by"] = "Nora"
    generation_request["approved_at"] = datetime.now(timezone.utc).isoformat()
    job.generation_request = generation_request
    job.qa_result = QAResult(
        passed=True,
        script_feedback="Scene timing and prompt package are ready for generation.",
        visual_feedback="Asset checklist and visual direction are complete enough for generation.",
    )
    job.stage = "nora_done"
    job.status = JobStatus.AWAITING_APPROVAL
    _save_job_at_root(root, job)
    _write_work_event(
        root,
        "implementation_step",
        f"Marked generation ready for {job_id}",
        actor=user,
        result="ready_for_generation",
        next_action="Run generation dry-run or hand off to real generation.",
        metadata={"job_id": job_id},
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/run-generation-dry-run")
def run_generation_dry_run(job_id: str, request: Request, user: str = Depends(verify_auth)):
    root = _root(request)
    try:
        job = _find_job_at_root(root, job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    try:
        _run_generation_dry_run(root, job)
    except ValueError as exc:
        _write_work_event(root, "blocker", f"Generation dry-run blocked for {job_id}", actor=user, result=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    _write_work_event(
        root,
        "test_result",
        f"Generation dry-run completed for {job_id}",
        actor=user,
        result="dry_run_completed",
        next_action="Record real generation result before publish packaging.",
        metadata={"job_id": job_id},
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/record-generation-result")
def record_generation_result(
    job_id: str,
    request: Request,
    video_path: str = Form(...),
    provider: str = Form("manual_upload"),
    provider_request_id: str = Form(""),
    note: str = Form(""),
    user: str = Depends(verify_auth),
):
    root = _root(request)
    try:
        job = _find_job_at_root(root, job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    try:
        _record_generation_result(root, job, video_path, provider, provider_request_id, note)
    except ValueError as exc:
        _write_work_event(root, "blocker", f"Real generation result blocked for {job_id}", actor=user, result=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    _write_work_event(
        root,
        "implementation_step",
        f"Recorded real generation result for {job_id}",
        actor=user,
        result=f"provider={provider}",
        next_action="Record Roxy and Emma publish package.",
        metadata={"job_id": job_id, "provider_request_id": provider_request_id},
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/record-publish-package")
def record_publish_package(
    job_id: str,
    request: Request,
    caption: str = Form(...),
    hashtags: str = Form(...),
    faq: str = Form(...),
    publish_notes: str = Form(""),
    user: str = Depends(verify_auth),
):
    root = _root(request)
    try:
        job = _find_job_at_root(root, job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    try:
        _record_publish_package(root, job, caption, hashtags, faq, publish_notes)
    except ValueError as exc:
        _write_work_event(root, "blocker", f"Publish package blocked for {job_id}", actor=user, result=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    _write_work_event(
        root,
        "implementation_step",
        f"Recorded publish package for {job_id}",
        actor=user,
        result="publish_package completed",
        next_action="Create publish job.",
        metadata={"job_id": job_id},
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/create-publish-job")
def create_publish_job(job_id: str, request: Request, user: str = Depends(verify_auth)):
    root = _root(request)
    try:
        job = _find_job_at_root(root, job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    try:
        _create_publish_execution(root, job)
    except ValueError as exc:
        _write_work_event(root, "blocker", f"Create publish job blocked for {job_id}", actor=user, result=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    _write_work_event(
        root,
        "implementation_step",
        f"Created publish job for {job_id}",
        actor=user,
        result="ready_to_publish",
        next_action="Schedule publish after platform readiness check.",
        metadata={"job_id": job_id},
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/schedule-publish")
def schedule_publish(job_id: str, request: Request, user: str = Depends(verify_auth)):
    root = _root(request)
    try:
        job = _find_job_at_root(root, job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    try:
        _schedule_publish_execution(root, job)
    except ValueError as exc:
        _write_work_event(root, "blocker", f"Schedule publish blocked for {job_id}", actor=user, result=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    _write_work_event(
        root,
        "production_smoke",
        f"Scheduled publish handoff for {job_id}",
        actor=user,
        result="scheduled publish handoff",
        next_action="Use platform publisher controls for live posting.",
        metadata={"job_id": job_id},
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/retry-publish")
def retry_publish(job_id: str, request: Request, user: str = Depends(verify_auth)):
    root = _root(request)
    try:
        job = _find_job_at_root(root, job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    failed_platforms = _failed_publish_platforms(job)
    if not failed_platforms:
        raise HTTPException(status_code=400, detail=f"Job {job_id!r} has no failed publish platform")
    command = [sys.executable, "main.py", "--publish-only", job_id, "--schedule"]
    for platform in failed_platforms:
        command.extend(["--publish-platform", platform])
    subprocess.Popen(
        command,
        cwd=str(root),
    )
    _write_work_event(
        root,
        "deploy_step",
        f"Retry publish requested for {job_id}",
        actor=user,
        command="main.py --publish-only --schedule --publish-platform",
        result="subprocess started",
        metadata={"job_id": job_id, "platforms": failed_platforms},
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.post("/ops/publish-failures/{job_id}/{platform}/retry", response_class=HTMLResponse)
def ops_retry_publish_failure(
    job_id: str,
    platform: str,
    request: Request,
    user: str = Depends(verify_auth),
):
    root = _root(request)
    try:
        job = _find_job_at_root(root, job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    result = job.publish_result or {}
    platform_result = result.get(platform) if isinstance(result, dict) else None
    if not isinstance(platform_result, dict) or platform_result.get("status") != "failed":
        raise HTTPException(status_code=400, detail=f"{platform} is not failed for job {job_id}")
    error = _sanitize_ops_detail(platform_result.get("error") or platform_result.get("reason") or "failed")
    subprocess.Popen(
        [sys.executable, "main.py", "--publish-only", job_id, "--schedule", "--publish-platform", platform],
        cwd=str(root),
    )
    _write_work_event(
        root,
        "deploy_step",
        f"Ops retry requested for {platform} publish failure on {job_id}",
        actor=user,
        command="main.py --publish-only --schedule --publish-platform",
        result=_publish_failure_category(platform, error),
        next_action="Watch publish failure triage for updated platform status.",
        metadata={"job_id": job_id, "platform": platform},
    )
    return RedirectResponse("/ops", status_code=303)


@app.post("/ops/publish-failures/retry-safe-instagram", response_class=HTMLResponse)
def ops_retry_safe_instagram_failures(request: Request, user: str = Depends(verify_auth)):
    root = _root(request)
    jobs = list_all_jobs(root)
    triage = _ops_publish_failure_triage(root, jobs, limit=1000)
    rows = triage["safe_instagram_retry_rows"]
    if not rows:
        snapshot = _ops_snapshot(root)
        snapshot["action_result"] = {
            "name": "Retry safe Instagram failures",
            "state": "Ready",
            "detail": "No safe Instagram failures found.",
        }
        return templates.TemplateResponse(request, "ops.html", snapshot)
    for row in rows:
        subprocess.Popen(
            [
                sys.executable,
                "main.py",
                "--publish-only",
                row["job_id"],
                "--schedule",
                "--publish-platform",
                "instagram",
            ],
            cwd=str(root),
        )
    _write_work_event(
        root,
        "deploy_step",
        "Retry all safe Instagram publish failures",
        actor=user,
        command="main.py --publish-only --schedule --publish-platform instagram",
        result=f"subprocesses started: {len(rows)}",
        next_action="Refresh Ops after publish retries finish.",
        metadata={"job_ids": [row["job_id"] for row in rows], "platform": "instagram"},
    )
    return RedirectResponse("/ops", status_code=303)


@app.post("/jobs/{job_id}/publish-instagram-now")
def publish_instagram_now(job_id: str, request: Request, user: str = Depends(verify_auth)):
    from datetime import datetime, timezone
    import time

    root = _root(request)
    try:
        job = find_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    ig_result = (job.publish_result or {}).get("instagram", {})
    if not isinstance(ig_result, dict) or ig_result.get("status") != "pending_queue":
        raise HTTPException(status_code=400, detail="Instagram is not pending queue for this job")
    ig_result["scheduled_publish_time"] = int(time.time()) - 1
    ig_result["due_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ig_result["publish_now_requested"] = True
    save_job(job)
    subprocess.Popen([sys.executable, "instagram_queue.py"], cwd=str(_ROOT))
    _write_work_event(
        root,
        "deploy_step",
        f"Instagram publish-now requested for {job_id}",
        actor=user,
        command="instagram_queue.py",
        result="subprocess started",
        metadata={"job_id": job_id},
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.get("/metrics", response_class=HTMLResponse)
def metrics_redirect(_: str = Depends(verify_auth)):
    return RedirectResponse("/aurora/metrics", status_code=307)


@app.get("/trigger", response_class=HTMLResponse)
def trigger_form_redirect(_: str = Depends(verify_auth)):
    return RedirectResponse("/aurora/new-mission", status_code=307)


@app.post("/trigger")
def trigger_run(
    request: Request,
    project: str = Form(...),
    brief: str = Form(...),
    content_type: str = Form(...),
    dry_run: str = Form(default=None),
    user: str = Depends(verify_auth),
):
    root = _root(request)
    valid = set(list_project_slugs(root))
    project = resolve_project_slug(project, root=root)
    if project not in valid:
        raise HTTPException(status_code=400, detail="Unknown project")
    if content_type not in VALID_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid content_type")
    if len(brief) > MAX_BRIEF_LEN:
        raise HTTPException(status_code=400, detail=f"Brief too long (max {MAX_BRIEF_LEN} chars)")
    cmd = [
        sys.executable, "main.py",
        "--project", project,
        "--brief", brief,
        "--content-type", content_type,
        "--unattended",
    ]
    if dry_run:
        cmd.append("--dry-run")
    subprocess.Popen(cmd, cwd=str(_ROOT))
    _write_work_event(
        root,
        "terminal_command",
        "Dashboard mission trigger",
        actor=user,
        command=" ".join(cmd),
        result="subprocess started",
        next_action="Review mission output after pipeline completes.",
        metadata={"project": project, "content_type": content_type, "dry_run": bool(dry_run)},
    )
    return RedirectResponse("/aurora/missions", status_code=303)


if __name__ == "__main__":
    import uvicorn
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("dashboard:app", host=args.host, port=args.port, reload=False)
