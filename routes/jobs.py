"""/jobs/* mission detail routes."""
from __future__ import annotations

import subprocess
import sys

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from routes.deps import templates, verify_auth, _root
from track_queue import read_queue
from routes._helpers import (
    MISSION_FILTER_KEYS,
    _build_voyage_steps,
    _caption_readiness,
    _failed_publish_platforms,
    _filter_jobs,
    _find_job_at_root,
    _live_publish_gate_summary,
    _media_readiness,
    _mission_command,
    _mission_filters,
    _mission_outputs,
    _publish_execution_status,
    _publish_execution_summary,
    _publish_result_reason,
    _real_generation_completed,
    _record_captain_review,
    _record_generation_result,
    _record_publish_package,
    _run_generation_dry_run,
    _save_job_at_root,
    _create_publish_execution,
    _schedule_publish_execution,
    _write_work_event,
    list_all_jobs,
    QAResult,
    JobStatus,
)

# _ROOT for subprocess calls - use the project root
from routes.deps import _ROOT

# Import dashboard at module load time so monkeypatch.setattr(dashboard, "find_job", ...)
# patches the same object this module references.  dashboard.py is already partially
# registered in sys.modules when this module is first loaded (because dashboard.py
# imports us), so there is no circular-import problem.
import dashboard as _dashboard_mod  # noqa: E402

router = APIRouter()


@router.get("/jobs", response_class=HTMLResponse)
def jobs_redirect(_: str = Depends(verify_auth)):
    return RedirectResponse("/aurora/missions", status_code=307)


@router.get("/jobs/partial", response_class=HTMLResponse)
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


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(job_id: str, request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    try:
        job = _dashboard_mod.find_job(job_id)
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
    queue = read_queue()
    job_queue_entries = [e for e in queue if e["job_id"] == job.id]
    snapshot_count = len(job.performance)
    if job_queue_entries:
        next_snapshot = min(job_queue_entries, key=lambda e: e["track_at"])
        snapshot_status = f"Next snapshot: {next_snapshot['track_at']} UTC"
    elif snapshot_count >= 2:
        snapshot_status = "24h ✓ — 72h ✓"
    elif snapshot_count == 1:
        snapshot_status = "24h tracked ✓ — 72h pending"
    else:
        snapshot_status = "No performance data yet"
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
            "snapshot_status": snapshot_status,
        },
    )


@router.get("/jobs/{job_id}/captain-approval", response_class=HTMLResponse)
def captain_approval(job_id: str, request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    try:
        job = _find_job_at_root(root, job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    if _publish_execution_status(job) not in {"ready_to_publish", "captain_hold", "needs_edits", "scheduled"}:
        raise HTTPException(status_code=400, detail="Job is not ready for Captain approval")
    faq_path = root / "output" / job.pm.page_name / job_id / "faq.md"
    faq_content = faq_path.read_text() if faq_path.exists() else None
    return templates.TemplateResponse(
        request,
        "captain_approval.html",
        {
            "job": job,
            "publish_package": getattr(job, "publish_package", None),
            "publish_execution": getattr(job, "publish_execution", None),
            "publish_execution_summary": _publish_execution_summary(job),
            "publish_result_reason": _publish_result_reason(job),
            "faq_content": faq_content,
        },
    )


@router.get("/jobs/{job_id}/live-publish-approval", response_class=HTMLResponse)
def live_publish_approval(job_id: str, request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    try:
        job = _find_job_at_root(root, job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    if _publish_execution_status(job) != "scheduled":
        raise HTTPException(status_code=400, detail="Job must have a dashboard handoff before live publish review")
    return templates.TemplateResponse(
        request,
        "live_publish_approval.html",
        {
            "job": job,
            "publish_package": getattr(job, "publish_package", None),
            "publish_execution": getattr(job, "publish_execution", None),
            "publish_execution_summary": _publish_execution_summary(job),
            "publish_result_reason": _publish_result_reason(job),
            "live_gate": _live_publish_gate_summary(root, job),
        },
    )


@router.post("/jobs/{job_id}/ready-for-generation")
def ready_for_generation(job_id: str, request: Request, user: str = Depends(verify_auth)):
    from datetime import datetime, timezone
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


@router.post("/jobs/{job_id}/run-generation-dry-run")
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


@router.post("/jobs/{job_id}/record-generation-result")
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


@router.post("/jobs/{job_id}/record-publish-package")
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


@router.post("/jobs/{job_id}/create-publish-job")
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
        next_action="Captain review required before dashboard handoff. Live publishing remains locked.",
        metadata={"job_id": job_id},
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@router.post("/jobs/{job_id}/captain-review")
def captain_review(
    job_id: str,
    request: Request,
    decision: str = Form(...),
    note: str = Form(""),
    user: str = Depends(verify_auth),
):
    root = _root(request)
    try:
        job = _find_job_at_root(root, job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    try:
        _record_captain_review(root, job, decision, note)
    except ValueError as exc:
        _write_work_event(root, "blocker", f"Captain review blocked for {job_id}", actor=user, result=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    result = "scheduled publish handoff" if decision == "approve_schedule_handoff" else decision
    _write_work_event(
        root,
        "production_smoke" if decision == "approve_schedule_handoff" else "implementation_step",
        f"Captain review decision for {job_id}",
        actor=user,
        result=result,
        next_action="Live publishing remains locked until explicit approval." if decision == "approve_schedule_handoff" else "Review approval queue for next action.",
        metadata={"job_id": job_id, "decision": decision},
    )
    return RedirectResponse(f"/jobs/{job_id}/captain-approval", status_code=303)


@router.post("/jobs/{job_id}/schedule-publish")
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
        f"Scheduled dashboard handoff for {job_id}",
        actor=user,
        result="scheduled publish handoff",
        next_action="Live publishing remains locked until explicit approval.",
        metadata={"job_id": job_id},
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@router.post("/jobs/{job_id}/retry-publish")
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
    subprocess.Popen(command, cwd=str(root))
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


@router.post("/jobs/{job_id}/publish-instagram-now")
def publish_instagram_now(job_id: str, request: Request, user: str = Depends(verify_auth)):
    import time
    from datetime import datetime, timezone
    root = _root(request)
    try:
        job = _dashboard_mod.find_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    ig_result = (job.publish_result or {}).get("instagram", {})
    if not isinstance(ig_result, dict) or ig_result.get("status") != "pending_queue":
        raise HTTPException(status_code=400, detail="Instagram is not pending queue for this job")
    ig_result["scheduled_publish_time"] = int(time.time()) - 1
    ig_result["due_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ig_result["publish_now_requested"] = True
    _dashboard_mod.save_job(job)
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


@router.get("/metrics", response_class=HTMLResponse)
def metrics_redirect(_: str = Depends(verify_auth)):
    return RedirectResponse("/aurora/metrics", status_code=307)


@router.get("/trigger", response_class=HTMLResponse)
def trigger_form_redirect(_: str = Depends(verify_auth)):
    return RedirectResponse("/aurora/new-mission", status_code=307)


@router.post("/trigger")
def trigger_run(
    request: Request,
    project: str = Form(...),
    brief: str = Form(...),
    content_type: str = Form(...),
    dry_run: str = Form(default=None),
    user: str = Depends(verify_auth),
):
    from routes._helpers import (
        VALID_CONTENT_TYPES,
        MAX_BRIEF_LEN,
        list_project_slugs,
        resolve_project_slug,
    )
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
