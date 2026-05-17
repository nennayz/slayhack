"""Captain's Deck route — /"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.responses import HTMLResponse

from routes.deps import templates, verify_auth, _root
from routes._helpers import (
    _captain_action_console,
    _captain_learning_runbook,
    _console_history,
    active_jobs,
    attention_jobs,
    command_brief,
    fleet_status,
    list_all_jobs,
    load_performance_all,
    summarize_jobs,
)

router = APIRouter()


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
            "learning_runbook": _captain_learning_runbook(root, jobs),
            "captain_action_history": _console_history(
                root,
                station=request.query_params.get("history_station", "all"),
                actor=request.query_params.get("history_actor", "all"),
                mission=request.query_params.get("history_mission", ""),
                needs_captain=request.query_params.get("needs_captain") == "1",
            ),
        },
    )
