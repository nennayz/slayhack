"""NayzFreedom Fleet dashboard — thin entry point.

All helpers live in routes/_helpers.py.
All route handlers live in routes/{captain,aurora,jobs,ships,readiness,ops}.py.
This module imports and re-exports them so existing tests and tools that do
``import dashboard`` continue to work unchanged.
"""
from __future__ import annotations
import os as _os
import subprocess  # noqa: F401 – re-exported so tests can patch dashboard.subprocess.Popen
import sys as _sys_top  # noqa: F401

# Production starts this file as `python dashboard.py`, which makes the module
# name `__main__`. Route modules import `dashboard` for test monkeypatch
# compatibility, so alias the active script module before importing routes.
_sys_top.modules.setdefault("dashboard", _sys_top.modules[__name__])

# Guard: raise early if auth env vars are not set (tests expect this from `import dashboard`)
if not _os.environ.get("DASHBOARD_USER") or not _os.environ.get("DASHBOARD_PASSWORD"):
    raise RuntimeError(
        "DASHBOARD_USER and DASHBOARD_PASSWORD must be set in environment before starting the dashboard."
    )

# ── Shared FastAPI app and supporting objects ────────────────────────────────
from routes.deps import (  # noqa: F401
    app,
    templates,
    security,
    verify_auth,
    _root,
    DASHBOARD_USER,
    DASHBOARD_PASSWORD,
    _ROOT,
    OPS_PUBLIC_BASE_URL,
    OPS_UNITS,
    OPS_ACTIONS,
    VALID_CONTENT_TYPES,
    MAX_BRIEF_LEN,
)

# ── All helper functions (re-exported for test compatibility) ────────────────
from routes._helpers import (  # noqa: F401
    MISSION_FILTER_KEYS,
    GENERATION_FILTERS,
    _status_label,
    _publish_status_items,
    _publish_history_items,
    _publish_result_reason,
    _filter_jobs,
    _mission_filters,
    _run_command,
    _sanitize_ops_detail,
    _ops_log_path,
    _ops_incident_path,
    _ops_report_path,
    _instagram_queue_history_path,
    _write_ops_audit,
    _write_work_event,
    _recent_ops_audit,
    _write_ops_incident,
    _load_ops_incidents,
    _recent_ops_incidents,
    _recent_ops_reports,
    _recent_instagram_queue_history,
    _track_queue_summary,
    _recent_track_queue_history,
    _tracking_failure_rows,
    _tracking_readiness_rows,
    _latest_performance_signals,
    _sanitize_ops_report_summary,
    _incident_summary,
    _update_ops_incident_status,
    _ops_log_status,
    _job_state_write_health,
    _systemctl_args,
    _ops_action_buttons,
    _run_ops_action,
    _ops_unit_status,
    _latest_backup_status,
    _backup_history,
    _restore_smoke_history,
    _system_resources,
    _service_event_history,
    _ops_publish_errors,
    _publish_failure_category,
    _content_type_value,
    _media_readiness,
    _public_media_path,
    _public_media_url,
    _public_url_readiness,
    _failed_publish_platforms,
    _caption_readiness,
    _retry_recommendation,
    _ops_publish_failure_triage,
    _ops_now_utc,
    _parse_ops_time,
    _instagram_due_time,
    _ops_time_distance,
    _caption_preview,
    _ops_publish_summary,
    _workflow_owner_summary,
    _security_hygiene_checks,
    _ops_daily_summary,
    _signed_request_for_smoke,
    _http_smoke,
    _ops_smoke_results,
    _ops_snapshot,
    _project_options,
    _read_review_note,
    _read_asset_audit_note,
    _png_dimensions,
    _sha256,
    _crew_asset_audit,
    _latest_learning_brief,
    _build_voyage_steps,
    _mission_command,
    _mission_outputs,
    _readiness_checks,
    _ticket_type_from_calendar_key,
    _content_type_for_ticket,
    _platforms_for_ticket,
    _owner_for_ticket,
    _acceptance_criteria_for_ticket,
    _asset_requirements_for_ticket,
    _storyboard_for_long_video,
    _storyboard_for_short_video,
    _video_package_for_ticket,
    _video_package_rows,
    _daily_slate_video_package_rows,
    _find_video_ticket,
    _find_slate_ticket,
    _ticket_payload,
    _video_package_payload,
    _generation_request_for_package,
    _generation_status_label,
    _generation_state,
    _waiting_for_real_video,
    _real_generation_completed,
    _publish_package_completed,
    _publish_execution_status,
    _publish_execution_label,
    _publish_execution_state,
    _clean_generation_text,
    _generation_artifact_path,
    _generation_artifact_display_path,
    _publish_packaging_label,
    _publish_packaging_state,
    _publish_execution_summary,
    _path_readiness,
    _live_publish_gate_summary,
    _manual_posting_lane_groups,
    _manual_posting_queue_rows,
    _generation_row_matches_filter,
    _generation_filter_cards,
    _generation_queue,
    _run_generation_dry_run,
    _split_hashtags,
    _record_publish_package,
    _create_publish_execution,
    _record_captain_review,
    _schedule_publish_execution,
    _record_generation_result,
    _safe_job_suffix,
    _save_job_at_root,
    _find_job_at_root,
    _video_package_job,
    _slate_ticket_job,
    _create_video_package_mission,
    _create_slate_ticket_mission,
    _weekly_calendar,
    _calendar_slate,
    _mission_type_cards,
    _workflow_lanes,
    _ticket_rows,
    _slate_counts,
    _mission_ticket_index,
    _annotate_ticket_missions,
    _next_slate_ticket,
    _daily_slate_cards,
    _approval_default_video_path,
    _approval_default_caption,
    _approval_default_hashtags,
    _approval_default_faq,
    _approval_risk_label,
    _approval_lane_key,
    _approval_lane_groups,
    _approval_lane_filters,
    _approval_queue_rows,
    _qa_status,
    _performance_loop,
    _cross_team_requests,
    _aurora_workflow_snapshot,
    _decode_meta_signed_request,
    load_performance_all,
)

# ── Re-define patchable functions so monkeypatch.setattr(dashboard, …) works ─
# Tests patch dashboard._latest_backup_status, dashboard._run_command, etc.
# These calls must go through dashboard's own global namespace, not _helpers'.
import sys as _sys

def _ops_snapshot(root, smoke_results=None):  # type: ignore[override]
    """Wrapper that calls helpers through dashboard globals for monkeypatching."""
    _mod = _sys.modules[__name__]
    jobs = list_all_jobs(root)
    summary = summarize_jobs(jobs)
    units = _mod._ops_unit_status()
    backup = _mod._latest_backup_status()
    incident_summary = _incident_summary(root)
    ops_reports = _recent_ops_reports(root)
    publish_summary = _ops_publish_summary(jobs)
    track_summary = _track_queue_summary(root)
    job_state_health = _mod._job_state_write_health(root)
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


def _ops_unit_status():  # type: ignore[override]
    _mod = _sys.modules[__name__]
    rows = []
    for unit in OPS_UNITS:
        result = _mod._run_command(["systemctl", "is-active", unit], timeout=4)
        active = result["state"] == "ok" and result["detail"] == "active"
        rows.append({
            "name": unit,
            "state": "Ready" if active else "Missing" if result["state"] == "unavailable" else "Failed",
            "detail": result["detail"],
        })
    return rows


def _run_ops_action(action: str):  # type: ignore[override]
    _mod = _sys.modules[__name__]
    from routes._helpers import OPS_ACTIONS, _systemctl_args
    import json, subprocess, sys
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
        except Exception as exc:
            return {"name": label, "state": "Failed", "detail": str(exc)[:300]}
        return {"name": label, "state": "Ready", "detail": f"Queued {verb} for {unit}."}
    result = _mod._run_command(_systemctl_args(verb, unit), timeout=30)
    state = "Ready" if result["state"] == "ok" else "Failed"
    detail = result["detail"]
    if result["state"] == "failed" and "password" in detail.lower():
        detail = "sudo permission missing for this Ops action."
    return {"name": label, "state": state, "detail": detail}


def _ops_now_utc():  # type: ignore[override]
    # The function itself is replaced by monkeypatch. This default implementation is used normally.
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _ops_publish_summary(jobs) -> dict[str, object]:  # type: ignore[override]
    """Override that calls _ops_now_utc through dashboard globals so monkeypatch works."""
    from datetime import timedelta
    from routes._helpers import _instagram_due_time, _ops_time_distance, _caption_preview, _parse_ops_time
    _mod = _sys.modules[__name__]
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
    now = _mod._ops_now_utc()
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
            from routes._helpers import _sanitize_ops_detail
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


# Also re-export datetime/timezone for tests that do _dm.datetime(...)
from datetime import datetime, timezone  # noqa: F401

# ── Additional imports needed by the overridden functions above ───────────────
from dashboard_store import list_all_jobs, summarize_jobs  # noqa: F401
from job_store import find_job, save_job  # noqa: F401
from work_activity import read_recent_work_activity, work_activity_status  # noqa: F401

# ── Register route modules ───────────────────────────────────────────────────
from routes.captain import router as _captain_router
from routes.aurora import router as _aurora_router
from routes.jobs import router as _jobs_router
from routes.ships import router as _ships_router
from routes.readiness import router as _readiness_router
from routes.ops import router as _ops_router

app.include_router(_ops_router)      # includes healthz, media, privacy, data-deletion first
app.include_router(_captain_router)
app.include_router(_aurora_router)
app.include_router(_jobs_router)
app.include_router(_ships_router)
app.include_router(_readiness_router)


if __name__ == "__main__":
    import uvicorn
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("dashboard:app", host=args.host, port=args.port, reload=False)
