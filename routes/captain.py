"""Captain's Deck route — /"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from routes.deps import templates, verify_auth, _root
from routes._helpers import (
    _captain_action_console,
    _captain_attention_lane,
    _captain_learning_runbook,
    _apply_accepted_learning_to_next_mission,
    _confirm_mission_learning,
    _console_history,
    _find_job_at_root,
    _manual_closeout_undrafted_learning_rows,
    _update_daily_brief_draft_status,
    _write_manual_closeout_learning_draft,
    _write_work_event,
    active_jobs,
    attention_jobs,
    command_brief,
    fleet_status,
    list_all_jobs,
    load_performance_all,
    summarize_jobs,
)

router = APIRouter()


def _runbook_return_path(value: str) -> str:
    if value in {"/", "/aurora"}:
        return value
    return "/"


def _runbook_redirect_path(value: str, result: str) -> str:
    return f"{_runbook_return_path(value)}?runbook_result={quote(result, safe='')}"


@router.get("/", response_class=HTMLResponse)
def captains_deck(request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    jobs = list_all_jobs(root)
    performance = load_performance_all(root)
    summary = summarize_jobs(jobs)
    signals = attention_jobs(jobs)
    active = active_jobs(jobs)
    brief = command_brief(jobs)
    ships = fleet_status(jobs)
    learning_runbook = _captain_learning_runbook(root, jobs)
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
            "captain_action_console": _captain_action_console(root, jobs),
            "captain_attention_lane": _captain_attention_lane(
                learning_runbook=learning_runbook,
                attention_items=signals,
                active_items=active,
            ),
            "learning_runbook": learning_runbook,
            "runbook_result": request.query_params.get("runbook_result", ""),
            "captain_action_history": _console_history(
                root,
                station=request.query_params.get("history_station", "all"),
                actor=request.query_params.get("history_actor", "all"),
                mission=request.query_params.get("history_mission", ""),
                needs_captain=request.query_params.get("needs_captain") == "1",
            ),
        },
    )


@router.post("/learning-runbook/create-draft")
def learning_runbook_create_draft(
    request: Request,
    return_path: str = Form("/"),
    user: str = Depends(verify_auth),
):
    root = _root(request)
    lessons = _manual_closeout_undrafted_learning_rows(root)
    if not lessons:
        raise HTTPException(status_code=400, detail="No closed manual posting lessons need a daily draft")
    draft = _write_manual_closeout_learning_draft(root, lessons, created_by=user)
    _write_work_event(
        root,
        "implementation_step",
        "Created manual posting daily learning draft from runbook",
        actor=user,
        result=str(draft["path"]),
        next_action="Accept the daily learning draft before applying it to the next mission.",
        metadata={"source_job_ids": draft["source_job_ids"]},
    )
    return RedirectResponse(_runbook_redirect_path(return_path, f"Created draft: {draft['path']}"), status_code=303)


@router.post("/learning-runbook/accept-draft")
def learning_runbook_accept_draft(
    request: Request,
    draft_path: str = Form(...),
    return_path: str = Form("/"),
    user: str = Depends(verify_auth),
):
    root = _root(request)
    try:
        result = _update_daily_brief_draft_status(root, draft_path, "accepted", actor=user)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Draft {draft_path!r} not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _write_work_event(
        root,
        "implementation_step",
        "Accepted daily learning draft from runbook",
        actor=user,
        result=str(result["path"]),
        next_action="Apply accepted learning to the next Daily Slate mission.",
        metadata={"source_job_ids": result["source_job_ids"]},
    )
    return RedirectResponse(_runbook_redirect_path(return_path, f"Accepted artifact: {result['path']}"), status_code=303)


@router.post("/learning-runbook/apply-learning")
def learning_runbook_apply_learning(
    request: Request,
    project_slug: str = Form(...),
    return_path: str = Form("/"),
    user: str = Depends(verify_auth),
):
    root = _root(request)
    try:
        result = _apply_accepted_learning_to_next_mission(root, project_slug, actor=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _write_work_event(
        root,
        "implementation_step",
        f"Applied accepted learning from runbook to mission {result['job_id']}",
        actor=user,
        result=f"{result['project']}:{result['ticket_id']}",
        next_action="Confirm applied learning on the mission before generation.",
        metadata={
            "job_id": result["job_id"],
            "project": result["project"],
            "ticket_id": result["ticket_id"],
            "source_job_ids": result["source_job_ids"],
            "created": result["created"],
        },
    )
    return RedirectResponse(
        _runbook_redirect_path(return_path, f"Applied mission: {result['job_id']} ({result['project']}:{result['ticket_id']})"),
        status_code=303,
    )


@router.post("/learning-runbook/confirm-learning")
def learning_runbook_confirm_learning(
    request: Request,
    job_id: str = Form(...),
    return_path: str = Form("/"),
    user: str = Depends(verify_auth),
):
    root = _root(request)
    try:
        job = _find_job_at_root(root, job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    try:
        result = _confirm_mission_learning(root, job, actor=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _write_work_event(
        root,
        "implementation_step",
        f"Confirmed accepted learning from runbook for {job_id}",
        actor=user,
        result="learning_confirmed",
        next_action="Crew can use the confirmed learning in safe generation execution.",
        metadata=result,
    )
    return RedirectResponse(_runbook_redirect_path(return_path, f"Confirmed mission: {job_id}"), status_code=303)
