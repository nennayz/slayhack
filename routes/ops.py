"""/ops routes — operational dashboard, smoke tests, incidents, publish failures."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from routes.deps import templates, verify_auth, _root, _ROOT
from routes._helpers import (
    _write_ops_audit,
    _write_ops_incident,
    _update_ops_incident_status,
    _ops_publish_failure_triage,
    _find_job_at_root,
    _sanitize_ops_detail,
    _publish_failure_category,
    _write_work_event,
    list_all_jobs,
)


def _get_dashboard():
    """Lazy import of dashboard module to avoid circular imports at load time.
    Ops helpers (_ops_snapshot, _run_ops_action) are defined in dashboard.py so
    that monkeypatch.setattr(dashboard, …) works in tests."""
    import dashboard
    return dashboard

import subprocess
import sys

router = APIRouter()


@router.get("/healthz")
def healthz():
    from fastapi.responses import JSONResponse
    return JSONResponse({"status": "ok", "service": "nayzfreedom-dashboard"})


@router.get("/media/public/{job_id}/{filename}")
def public_media(job_id: str, filename: str, request: Request):
    from routes._helpers import _public_media_path
    try:
        path = _public_media_path(_root(request), job_id, filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Public media not found")
    return FileResponse(path)


@router.api_route("/privacy", methods=["GET", "HEAD"], response_class=HTMLResponse)
def privacy_policy(request: Request):
    return templates.TemplateResponse(request, "privacy.html", {})


@router.api_route("/data-deletion", methods=["GET", "HEAD"], response_class=HTMLResponse)
@router.api_route("/data_deletion.html", methods=["GET", "HEAD"], response_class=HTMLResponse)
def data_deletion(request: Request):
    return templates.TemplateResponse(request, "data_deletion.html", {})


@router.post("/data-deletion-callback")
async def data_deletion_callback(signed_request: str = Form(...)):
    from routes._helpers import _decode_meta_signed_request
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


@router.get("/ops", response_class=HTMLResponse)
def ops_dashboard(request: Request, _: str = Depends(verify_auth)):
    snapshot = _get_dashboard()._ops_snapshot(_root(request))
    return templates.TemplateResponse(request, "ops.html", snapshot)


@router.post("/ops/smoke-test", response_class=HTMLResponse)
def ops_smoke_test(request: Request, user: str = Depends(verify_auth)):
    root = _root(request)
    smoke_results = _get_dashboard()._ops_smoke_results(root)
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
    snapshot = _get_dashboard()._ops_snapshot(root, smoke_results=smoke_results)
    return templates.TemplateResponse(request, "ops.html", snapshot)


@router.post("/ops/actions/{action}", response_class=HTMLResponse)
def ops_action(action: str, request: Request, user: str = Depends(verify_auth)):
    root = _root(request)
    action_result = _get_dashboard()._run_ops_action(action)
    _write_ops_audit(root, user, action, action_result)
    _write_work_event(
        root,
        "deploy_step" if action == "restart_dashboard" else "implementation_step",
        f"Dashboard Ops action: {action}",
        actor=user,
        result=str(action_result.get("detail", action_result.get("state", ""))),
        metadata={"state": action_result.get("state", ""), "name": action_result.get("name", action)},
    )
    snapshot = _get_dashboard()._ops_snapshot(root)
    snapshot["action_result"] = action_result
    return templates.TemplateResponse(request, "ops.html", snapshot)


@router.post("/ops/incidents", response_class=HTMLResponse)
def ops_incident(
    request: Request,
    title: str = Form(""),
    severity: str = Form("info"),
    note: str = Form(""),
    user: str = Depends(verify_auth),
):
    root = _root(request)
    snapshot = _get_dashboard()._ops_snapshot(root)
    try:
        incident = _write_ops_incident(root, user, title, severity, note)
    except ValueError as exc:
        snapshot["incident_result"] = {"state": "Failed", "detail": str(exc)}
        return templates.TemplateResponse(request, "ops.html", snapshot, status_code=400)
    snapshot = _get_dashboard()._ops_snapshot(root)
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


@router.post("/ops/incidents/{incident_id}/status", response_class=HTMLResponse)
def ops_incident_status(
    incident_id: str,
    request: Request,
    status: str = Form(...),
    user: str = Depends(verify_auth),
):
    root = _root(request)
    snapshot = _get_dashboard()._ops_snapshot(root)
    try:
        incident = _update_ops_incident_status(root, incident_id, status, user)
    except ValueError as exc:
        snapshot["incident_result"] = {"state": "Failed", "detail": str(exc)}
        return templates.TemplateResponse(request, "ops.html", snapshot, status_code=400)
    snapshot = _get_dashboard()._ops_snapshot(root)
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


@router.post("/ops/publish-failures/{job_id}/{platform}/retry", response_class=HTMLResponse)
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


@router.post("/ops/publish-failures/retry-safe-instagram", response_class=HTMLResponse)
def ops_retry_safe_instagram_failures(request: Request, user: str = Depends(verify_auth)):
    root = _root(request)
    jobs = list_all_jobs(root)
    triage = _ops_publish_failure_triage(root, jobs, limit=1000)
    rows = triage["safe_instagram_retry_rows"]
    if not rows:
        snapshot = _get_dashboard()._ops_snapshot(root)
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
