"""/freedom and /lyra placeholder ship routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.responses import HTMLResponse

from routes.deps import templates, verify_auth

router = APIRouter()


@router.get("/freedom", response_class=HTMLResponse)
def freedom_overview(request: Request, _: str = Depends(verify_auth)):
    return templates.TemplateResponse(request, "freedom.html", {})


@router.get("/lyra", response_class=HTMLResponse)
def lyra_overview(request: Request, _: str = Depends(verify_auth)):
    return templates.TemplateResponse(request, "lyra.html", {})
