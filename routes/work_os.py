from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Query
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from models.work_os import PlanStatus, ReviewStatus, SlateStatus
from routes.deps import _root, templates, verify_auth
from work_os_store import (
    build_daily_work_brief,
    create_ticket_for_plan,
    create_today_slate,
    export_manual_publish_checklist,
    generate_bubbles,
    load_bubbles,
    load_monetize,
    load_plans,
    load_slates,
    load_tickets,
    publish_queue_rows,
    seed_content_planner,
    seed_monetize,
    sync_approved_ideas_into_planner,
    update_plan_status,
    update_publish_review,
    update_slate_status,
)

router = APIRouter()


def _knowledge_store(root):
    try:
        import os
        from knowledge.embedder import Embedder, openai_embed_fn
        from knowledge.settings import KnowledgeSettings
        from knowledge.store import KnowledgeStore

        settings = KnowledgeSettings.from_env(root)
        embed_fn = openai_embed_fn(settings.embed_model, os.getenv("OPENAI_API_KEY", ""))
        return KnowledgeStore(settings, Embedder(settings.embed_model, embed_fn=embed_fn))
    except Exception:  # noqa: BLE001 - dashboard planner must still render without KS availability
        return None


def _approved_ideas_waiting_planning_count(root, store) -> int:
    if store is None:
        return 0
    planned_source_uids = {plan.source_idea_uid for plan in load_plans(root) if plan.source_idea_uid}
    try:
        return sum(
            1
            for idea in store.recent(kind="idea", status="approved", limit=100, order="asc")
            if idea.uid not in planned_source_uids
        )
    except Exception:  # noqa: BLE001 - daily brief must render without KS availability
        return 0


@router.get("/aurora/planner", response_class=HTMLResponse)
def work_os_planner(request: Request, _: str = Depends(verify_auth)) -> HTMLResponse:
    root = _root(request)
    store = _knowledge_store(root)
    synced_count = 0
    if store is not None:
        plans, synced_count = sync_approved_ideas_into_planner(root, store)
        slates = load_slates(root)
        tickets = load_tickets(root)
    else:
        plans = load_plans(root)
        slates = load_slates(root)
        tickets = load_tickets(root)
    if not plans and not slates and not tickets:
        plans, slates, tickets = seed_content_planner(root)
    return templates.TemplateResponse(
        request,
        "work_os_planner.html",
        {
            "request": request,
            "plans": plans,
            "slates": slates,
            "tickets": tickets,
            "queued_tickets": [item for item in tickets if item.status.value == "queued"],
            "synced_count": synced_count,
        },
    )


@router.post("/aurora/planner/seed")
def work_os_planner_seed(request: Request, _: str = Depends(verify_auth)) -> RedirectResponse:
    seed_content_planner(_root(request))
    return RedirectResponse("/aurora/planner", status_code=303)


@router.post("/aurora/planner/sync")
def work_os_planner_sync(request: Request, _: str = Depends(verify_auth)) -> RedirectResponse:
    root = _root(request)
    store = _knowledge_store(root)
    if store is not None:
        sync_approved_ideas_into_planner(root, store)
    return RedirectResponse("/aurora/planner", status_code=303)


@router.post("/aurora/planner/review")
def work_os_plan_review(
    request: Request,
    plan_id: str = Form(...),
    decision: str = Form(...),
    _: str = Depends(verify_auth),
) -> RedirectResponse:
    status = PlanStatus.APPROVED if decision == "approve" else PlanStatus.REJECTED
    update_plan_status(_root(request), plan_id, status)
    return RedirectResponse("/aurora/planner", status_code=303)


@router.post("/aurora/planner/slate")
def work_os_create_slate(
    request: Request,
    page: str = Form(""),
    _: str = Depends(verify_auth),
) -> RedirectResponse:
    create_today_slate(_root(request), page or None)
    return RedirectResponse("/aurora/planner", status_code=303)


@router.post("/aurora/planner/slate/review")
def work_os_slate_review(
    request: Request,
    slate_id: str = Form(...),
    decision: str = Form(...),
    _: str = Depends(verify_auth),
) -> RedirectResponse:
    status = SlateStatus.APPROVED if decision == "approve" else SlateStatus.DRAFT
    update_slate_status(_root(request), slate_id, status)
    return RedirectResponse("/aurora/planner", status_code=303)


@router.post("/aurora/planner/tickets")
def work_os_create_ticket(
    request: Request,
    plan_id: str = Form(...),
    _: str = Depends(verify_auth),
) -> RedirectResponse:
    create_ticket_for_plan(_root(request), plan_id)
    return RedirectResponse("/aurora/planner", status_code=303)


@router.get("/aurora/publish-queue", response_class=HTMLResponse)
def work_os_publish_queue(
    request: Request,
    status: str = Query("all", pattern="^(all|pending|approved|rejected|posted_manually)$"),
    _: str = Depends(verify_auth),
) -> HTMLResponse:
    status_filter = None if status == "all" else status
    rows = publish_queue_rows(_root(request), status_filter=status_filter)
    all_rows = publish_queue_rows(_root(request))
    return templates.TemplateResponse(
        request,
        "work_os_publish_queue.html",
        {
            "request": request,
            "rows": rows,
            "all_count": len(all_rows),
            "pending_count": sum(1 for row in all_rows if row["status"] == "pending"),
            "approved_count": sum(1 for row in all_rows if row["status"] == "approved"),
            "rejected_count": sum(1 for row in all_rows if row["status"] == "rejected"),
            "status_filter": status,
        },
    )


@router.get("/aurora/publish-queue/checklist", response_class=PlainTextResponse)
def work_os_publish_queue_checklist(
    request: Request,
    status: str = Query("pending", pattern="^(pending|approved|rejected|posted_manually)$"),
    _: str = Depends(verify_auth),
) -> PlainTextResponse:
    return PlainTextResponse(export_manual_publish_checklist(_root(request), status_filter=status))


@router.post("/aurora/publish-queue/review")
def work_os_publish_queue_review(
    request: Request,
    package_id: str = Form(...),
    decision: str = Form(...),
    review_note: str = Form(""),
    _: str = Depends(verify_auth),
) -> RedirectResponse:
    status = ReviewStatus.APPROVED if decision == "approve" else ReviewStatus.REJECTED
    update_publish_review(_root(request), package_id, status, review_note)
    return RedirectResponse("/aurora/publish-queue", status_code=303)


@router.get("/aurora/work-brief", response_class=HTMLResponse)
def work_os_daily_brief(request: Request, _: str = Depends(verify_auth)) -> HTMLResponse:
    root = _root(request)
    store = _knowledge_store(root)
    approved_ideas_waiting_planning_count = _approved_ideas_waiting_planning_count(root, store)
    brief = build_daily_work_brief(
        root,
        approved_ideas_waiting_planning_count=approved_ideas_waiting_planning_count,
    )
    return templates.TemplateResponse(
        request,
        "work_os_brief.html",
        {
            "request": request,
            "brief": brief,
            "plans": load_plans(root),
            "draft_plans": [plan for plan in load_plans(root) if plan.status == PlanStatus.DRAFT],
            "slates": load_slates(root),
            "tickets": load_tickets(root),
            "queued_tickets": [ticket for ticket in load_tickets(root) if ticket.status.value == "queued"],
            "publish_rows": publish_queue_rows(root),
            "pending_publish_rows": [row for row in publish_queue_rows(root) if row["status"] == "pending"],
            "bubbles": load_bubbles(root),
            "monetize": load_monetize(root),
        },
    )


@router.get("/freedom/daily-brief", response_class=HTMLResponse)
def nami_daily_brief(request: Request, _: str = Depends(verify_auth)) -> HTMLResponse:
    root = _root(request)
    brief = build_daily_work_brief(root)
    return templates.TemplateResponse(
        request,
        "nami_daily_brief.html",
        {"request": request, "brief": brief},
    )


@router.get("/aurora/bubbles", response_class=HTMLResponse)
def work_os_bubbles(request: Request, _: str = Depends(verify_auth)) -> HTMLResponse:
    bubbles = generate_bubbles(_root(request))
    return templates.TemplateResponse(
        request,
        "work_os_bubbles.html",
        {"request": request, "bubbles": bubbles},
    )


@router.post("/aurora/bubbles/generate")
def work_os_bubbles_generate(request: Request, _: str = Depends(verify_auth)) -> RedirectResponse:
    generate_bubbles(_root(request))
    return RedirectResponse("/aurora/bubbles", status_code=303)


@router.get("/aurora/monetize", response_class=HTMLResponse)
def work_os_monetize(request: Request, _: str = Depends(verify_auth)) -> HTMLResponse:
    opportunities = seed_monetize(_root(request))
    return templates.TemplateResponse(
        request,
        "work_os_monetize.html",
        {"request": request, "opportunities": opportunities},
    )
