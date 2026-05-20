from __future__ import annotations

from fastapi import APIRouter, Depends, Form
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from models.work_os import ReviewStatus
from routes.deps import _root, templates, verify_auth
from work_os_store import (
    build_daily_work_brief,
    create_ticket_for_plan,
    generate_bubbles,
    load_bubbles,
    load_monetize,
    load_plans,
    load_slates,
    load_tickets,
    publish_queue_rows,
    seed_content_planner,
    seed_monetize,
    update_publish_review,
)

router = APIRouter()


@router.get("/aurora/planner", response_class=HTMLResponse)
def work_os_planner(request: Request, _: str = Depends(verify_auth)) -> HTMLResponse:
    root = _root(request)
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
        },
    )


@router.post("/aurora/planner/seed")
def work_os_planner_seed(request: Request, _: str = Depends(verify_auth)) -> RedirectResponse:
    seed_content_planner(_root(request))
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
def work_os_publish_queue(request: Request, _: str = Depends(verify_auth)) -> HTMLResponse:
    rows = publish_queue_rows(_root(request))
    return templates.TemplateResponse(
        request,
        "work_os_publish_queue.html",
        {"request": request, "rows": rows, "pending_count": sum(1 for row in rows if row["status"] == "pending")},
    )


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
    brief = build_daily_work_brief(root)
    return templates.TemplateResponse(
        request,
        "work_os_brief.html",
        {
            "request": request,
            "brief": brief,
            "plans": load_plans(root),
            "slates": load_slates(root),
            "tickets": load_tickets(root),
            "publish_rows": publish_queue_rows(root),
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
