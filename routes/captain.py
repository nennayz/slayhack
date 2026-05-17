"""Captain's Deck route — /"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.responses import HTMLResponse

from routes.deps import templates, verify_auth, _root
from routes._helpers import (
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
