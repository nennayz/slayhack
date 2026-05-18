"""Scout pipeline dashboard routes."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, Form
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from config import Config
from models.niche_opportunity import ScoutJob
from routes.deps import templates, verify_auth, _root

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scout", tags=["scout"])


def _latest_report(root: Path) -> ScoutJob | None:
    reports_dir = root / "output" / "scout_reports"
    if not reports_dir.exists():
        return None
    reports = sorted(reports_dir.glob("*.json"), reverse=True)
    if not reports:
        return None
    return ScoutJob.model_validate_json(reports[0].read_text())


@router.get("/", response_class=HTMLResponse)
async def scout_index(request: Request, _: str = Depends(verify_auth)):
    job = _latest_report(_root(request))
    return templates.TemplateResponse(
        "scout.html",
        {"request": request, "job": job},
    )


@router.post("/run")
async def scout_run(request: Request, _: str = Depends(verify_auth)):
    root = _root(request)

    def _background() -> None:
        try:
            cfg = Config.from_env()
            from scout_pipeline import run_scout_pipeline
            run_scout_pipeline(cfg, triggered_by="dashboard", output_root=root / "output")
        except Exception as exc:
            logger.error("Dashboard scout failed: %s", exc)

    threading.Thread(target=_background, daemon=True).start()
    return RedirectResponse(url="/scout/", status_code=303)


@router.post("/approve")
async def scout_approve(
    request: Request,
    job_id: str = Form(...),
    niche_name: str = Form(...),
    _: str = Depends(verify_auth),
):
    root = _root(request)

    def _background() -> None:
        try:
            cfg = Config.from_env()
            from scout_pipeline import approve_niche
            report_path = root / "output" / "scout_reports" / f"{job_id}-scout-report.json"
            job = ScoutJob.model_validate_json(report_path.read_text())
            approve_niche(job, niche_name, cfg, projects_root=root / "projects")
        except Exception as exc:
            logger.error("Dashboard approve failed: %s", exc)

    threading.Thread(target=_background, daemon=True).start()
    return RedirectResponse(url="/scout/", status_code=303)
