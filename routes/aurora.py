"""All /aurora/* routes including the new /aurora/islands/{project_slug}/calendar editor."""
from __future__ import annotations

import yaml
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from routes.deps import templates, verify_auth, _root
from routes._helpers import (
    CREW,
    GENERATION_FILTERS,
    MISSION_FILTER_KEYS,
    _approval_lane_filters,
    _approval_lane_groups,
    _approval_queue_rows,
    _aurora_workflow_snapshot,
    _calendar_slate,
    _captain_action_console,
    _console_history,
    _create_slate_ticket_mission,
    _create_video_package_mission,
    _daily_slate_cards,
    _filter_jobs,
    _generation_filter_cards,
    _generation_queue,
    _generation_row_matches_filter,
    _latest_learning_brief,
    _latest_performance_signals,
    _manual_posting_lane_groups,
    _manual_posting_queue_rows,
    _tracking_readiness_rows,
    _mission_filters,
    _project_options,
    _read_asset_audit_note,
    _read_review_note,
    _crew_asset_audit,
    _readiness_checks,
    _weekly_calendar,
    _write_work_event,
    active_jobs,
    attention_jobs,
    command_brief,
    get_crew_member,
    list_all_jobs,
    list_project_slugs,
    load_performance_all,
    resolve_project_slug,
    summarize_jobs,
    load_project,
    project_slug_matches,
)

# Import dashboard at module load time so monkeypatch.setattr(dashboard, "load_performance_all", ...)
# patches the same object this module references.
import dashboard as _dashboard_mod  # noqa: E402

router = APIRouter()

CALENDAR_BRIEF_KEYS = [
    "short_video_1",
    "short_video_2",
    "long_video",
    "article_1",
    "article_2",
    "infographic_1",
    "infographic_2",
]


@router.get("/aurora", response_class=HTMLResponse)
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
            "captain_action_console": _captain_action_console(root, jobs),
            "captain_action_history": _console_history(
                root,
                station=request.query_params.get("history_station", "all"),
                actor=request.query_params.get("history_actor", "all"),
                mission=request.query_params.get("history_mission", ""),
                needs_captain=request.query_params.get("needs_captain") == "1",
            ),
        },
    )


@router.get("/aurora/workflow", response_class=HTMLResponse)
def aurora_workflow(request: Request, _: str = Depends(verify_auth)):
    return templates.TemplateResponse(request, "aurora_workflow.html", _aurora_workflow_snapshot(_root(request)))


@router.get("/aurora/daily-slate", response_class=HTMLResponse)
def aurora_daily_slate(request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    all_slate_cards = _daily_slate_cards(root)
    selected_project = request.query_params.get("project", "all")
    project_slugs = {str(card["project"]) for card in all_slate_cards}
    if selected_project not in project_slugs:
        selected_project = "all"
    slate_cards = [
        card for card in all_slate_cards if selected_project == "all" or card["project"] == selected_project
    ]
    project_filters = [{"label": "All pages", "project": "all", "active": selected_project == "all"}] + [
        {
            "label": str(card["page_name"]),
            "project": str(card["project"]),
            "active": selected_project == card["project"],
        }
        for card in all_slate_cards
    ]
    selected_project_label = next(
        (item["label"] for item in project_filters if item["active"]),
        "All pages",
    )
    approval_queue = _approval_queue_rows(root)
    jobs = list_all_jobs(root)
    performance_signals = _latest_performance_signals(jobs)
    tracking_readiness = _tracking_readiness_rows(root, jobs, limit=4)
    return templates.TemplateResponse(
        request,
        "daily_slate.html",
        {
            "slate_cards": slate_cards,
            "project_filters": project_filters,
            "selected_project": selected_project,
            "selected_project_label": selected_project_label,
            "latest_brief": _latest_learning_brief(root),
            "performance_signals": performance_signals,
            "tracking_readiness": tracking_readiness,
            "approval_queue": approval_queue[:8],
            "approval_lane_groups": _approval_lane_groups(approval_queue),
            "total_tickets": sum(int(card["ticket_count"]) for card in all_slate_cards),
            "ready_pages": sum(1 for card in all_slate_cards if card["minimum_met"]),
            "approval_count": len(approval_queue),
        },
    )


@router.get("/aurora/approval-queue", response_class=HTMLResponse)
def aurora_approval_queue(request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    rows = _approval_queue_rows(root)
    all_lane_groups = _approval_lane_groups(rows)
    selected_lane = request.query_params.get("lane", "all")
    valid_lanes = {"all"} | {str(group["key"]) for group in all_lane_groups}
    if selected_lane not in valid_lanes:
        selected_lane = "all"
    lane_groups = [
        group for group in all_lane_groups if selected_lane == "all" or group["key"] == selected_lane
    ]
    return templates.TemplateResponse(
        request,
        "approval_queue.html",
        {
            "approval_queue": rows,
            "approval_lane_groups": lane_groups,
            "approval_lane_filters": _approval_lane_filters(all_lane_groups, selected_lane),
            "selected_lane": selected_lane,
            "needs_review_count": sum(1 for row in rows if row["status"] == "Needs review"),
            "ready_publish_count": sum(1 for row in rows if row["status"] == "Ready to publish"),
        },
    )


@router.get("/aurora/generation", response_class=HTMLResponse)
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
            "scheduled_handoff_count": sum(1 for item in rows if item["publish_execution"]["status"] == "scheduled"),
            "failed_count": sum(1 for item in rows if item["status"] == "failed"),
        },
    )


@router.get("/aurora/manual-posting", response_class=HTMLResponse)
def aurora_manual_posting(request: Request, _: str = Depends(verify_auth)):
    rows = _manual_posting_queue_rows(_root(request))
    lane_groups = _manual_posting_lane_groups(rows)
    return templates.TemplateResponse(
        request,
        "manual_posting_queue.html",
        {
            "manual_posting_rows": rows,
            "manual_posting_lane_groups": lane_groups,
            "kit_synced_count": sum(1 for row in rows if row["lane"] == "kit_synced"),
            "waiting_tracking_count": sum(1 for row in rows if row["lane"] == "waiting_tracking"),
            "tracking_complete_count": sum(1 for row in rows if row["lane"] == "tracking_complete"),
            "needs_attention_count": sum(1 for row in rows if row["lane"] == "needs_attention"),
        },
    )


@router.post("/aurora/workflow/video-packages/{ticket_id}/create-mission")
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


@router.post("/aurora/daily-slate/{project_slug}/video-packages/{ticket_id}/create-mission")
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


@router.post("/aurora/daily-slate/{project_slug}/tickets/{ticket_id}/create-mission")
def create_daily_slate_ticket_mission(
    project_slug: str,
    ticket_id: str,
    request: Request,
    user: str = Depends(verify_auth),
):
    from routes._helpers import ContentType
    root = _root(request)
    try:
        project_slug = resolve_project_slug(project_slug, root=root)
        job = _create_slate_ticket_mission(root, project_slug, ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    next_action = (
        "Mark ready for generation after Nora review."
        if job.content_type == ContentType.VIDEO
        else "Open the mission and run the appropriate content workflow."
    )
    _write_work_event(
        root,
        "implementation_step",
        f"Created daily slate ticket mission {job.id}",
        actor=user,
        result=f"{project_slug}:{ticket_id}",
        next_action=next_action,
        metadata={"job_id": job.id, "project": project_slug, "ticket_id": ticket_id},
    )
    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


@router.get("/aurora/crew", response_class=HTMLResponse)
def aurora_crew(request: Request, _: str = Depends(verify_auth)):
    by_slug = {member.slug: member for member in CREW}

    def members(slugs: list) -> list:
        return [by_slug[slug] for slug in slugs if slug in by_slug]

    crew_groups = [
        {
            "eyebrow": "Fleet Command",
            "title": "Captain direction",
            "description": "Top-level owner authority and final taste/risk decisions for the whole Fleet.",
            "members": members(["captain-nayz"]),
        },
        {
            "eyebrow": "Page PMs",
            "title": "Island owners",
            "description": "Project managers who turn Captain intent into page-specific plans and approvals.",
            "members": members(["slay", "stadium"]),
        },
        {
            "eyebrow": "Aurora Production Route",
            "title": "Build and package the mission",
            "description": "The operating chain from mission command through creative production, QA, and community prep.",
            "members": members(["robin", "mia", "zoe", "bella", "lila", "video-producer", "nora", "roxy", "emma"]),
        },
        {
            "eyebrow": "Learning Loop",
            "title": "Read, store, and improve",
            "description": "Post-publish intelligence and durable lesson capture for the next cycle.",
            "members": members(["iris-gauge", "sage-ledger"]),
        },
    ]
    return templates.TemplateResponse(request, "crew.html", {"crew": CREW, "crew_groups": crew_groups})


@router.get("/aurora/learning", response_class=HTMLResponse)
def aurora_learning(request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    return templates.TemplateResponse(
        request,
        "learning.html",
        {
            "latest_brief": _latest_learning_brief(root),
            "review_note": _read_review_note(root),
            "asset_audit_note": _read_asset_audit_note(root),
            "crew_asset_audit": _crew_asset_audit(root),
        },
    )


@router.get("/aurora/crew/{slug}", response_class=HTMLResponse)
def aurora_character_sheet(slug: str, request: Request, _: str = Depends(verify_auth)):
    member = get_crew_member(slug)
    if member is None:
        raise HTTPException(status_code=404, detail=f"Crew member {slug!r} not found")
    return templates.TemplateResponse(request, "crew_detail.html", {"member": member})


@router.get("/aurora/islands/{project_slug}", response_class=HTMLResponse)
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


@router.get("/aurora/islands/{project_slug}/calendar", response_class=HTMLResponse)
def calendar_editor_get(project_slug: str, request: Request, _: str = Depends(verify_auth)):
    """Display the 7-day weekly calendar editor for a project island."""
    root = _root(request)
    resolved = resolve_project_slug(project_slug, root=root)
    calendar_path = root / "projects" / resolved / "weekly_calendar.yaml"
    if not calendar_path.exists():
        # Start with empty calendar
        calendar: dict = {}
    else:
        try:
            calendar = yaml.safe_load(calendar_path.read_text()) or {}
        except yaml.YAMLError:
            calendar = {}

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    # Normalise: ensure every day has every key (fill missing with "")
    grid = {}
    for day in days:
        day_data = calendar.get(day) or {}
        grid[day] = {key: str(day_data.get(key) or "") for key in CALENDAR_BRIEF_KEYS}

    return templates.TemplateResponse(
        request,
        "calendar_editor.html",
        {
            "project_slug": resolved,
            "days": days,
            "grid": grid,
            "brief_keys": CALENDAR_BRIEF_KEYS,
            "post_url": f"/aurora/islands/{resolved}/calendar",
        },
    )


@router.post("/aurora/islands/{project_slug}/calendar")
async def calendar_editor_post(
    project_slug: str,
    request: Request,
    user: str = Depends(verify_auth),
):
    """Receive edited form data and write back to weekly_calendar.yaml, then redirect to GET."""
    root = _root(request)
    resolved = resolve_project_slug(project_slug, root=root)
    calendar_path = root / "projects" / resolved / "weekly_calendar.yaml"

    # Read existing calendar to preserve any keys we don't edit
    if calendar_path.exists():
        try:
            existing: dict = yaml.safe_load(calendar_path.read_text()) or {}
        except yaml.YAMLError:
            existing = {}
    else:
        existing = {}

    # We need the form data — use sync approach via request.form() via run_until_complete
    form_data = await request.form()

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    updated: dict = dict(existing)
    for day in days:
        day_data: dict = dict(existing.get(day) or {})
        for key in CALENDAR_BRIEF_KEYS:
            field_name = f"{day}__{key}"
            value = str(form_data.get(field_name) or "").strip()
            if value:
                day_data[key] = value
            else:
                day_data.pop(key, None)
        if day_data:
            updated[day] = day_data
        else:
            updated.pop(day, None)

    calendar_path.parent.mkdir(parents=True, exist_ok=True)
    calendar_path.write_text(yaml.safe_dump(updated, default_flow_style=False, allow_unicode=True))

    _write_work_event(
        root,
        "implementation_step",
        f"Updated weekly calendar for {resolved}",
        actor=user,
        result="weekly_calendar.yaml written",
        next_action="Review the updated calendar on the island page.",
        metadata={"project": resolved},
    )
    return RedirectResponse(f"/aurora/islands/{resolved}/calendar", status_code=303)


@router.get("/aurora/missions", response_class=HTMLResponse)
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


@router.get("/aurora/metrics", response_class=HTMLResponse)
def aurora_metrics(request: Request, _: str = Depends(verify_auth)):
    data = _dashboard_mod.load_performance_all(_root(request))
    return templates.TemplateResponse(request, "metrics.html", {"data": data})


@router.get("/aurora/new-mission", response_class=HTMLResponse)
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
