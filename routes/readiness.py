"""/readiness operational preflight route."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.responses import HTMLResponse

from routes.deps import templates, verify_auth, _root
from routes._helpers import _readiness_checks

router = APIRouter()


@router.get("/readiness", response_class=HTMLResponse)
def readiness(request: Request, _: str = Depends(verify_auth)):
    checks = _readiness_checks(_root(request))
    return templates.TemplateResponse(request, "readiness.html", {"checks": checks})
