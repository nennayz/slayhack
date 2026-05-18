"""Scout pipeline dashboard routes."""
from __future__ import annotations

import logging
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse

_JOB_ID_RE = re.compile(r"^\d{8}_\d{6}$")

from config import Config
from models.niche_opportunity import ScoutJob
from project_loader import load_project_page_name
from routes.deps import templates, verify_auth, _root

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scout", tags=["scout"])
_PROJECT_SLUG_RE = re.compile(r"^[a-z0-9_]+$")


def _latest_report(root: Path) -> ScoutJob | None:
    reports_dir = root / "output" / "scout_reports"
    if not reports_dir.exists():
        return None
    reports = sorted(reports_dir.glob("*.json"), reverse=True)
    if not reports:
        return None
    return ScoutJob.model_validate_json(reports[0].read_text())


def _latest_dry_run_proof(root: Path, project_slug: str) -> dict | None:
    page_name = load_project_page_name(project_slug, root=root)
    output_dir = root / "output" / page_name
    if not output_dir.exists():
        return None
    jobs = sorted(output_dir.glob("*/job.json"), reverse=True)
    for job_path in jobs:
        try:
            data = json.loads(job_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("dry_run") is not True:
            continue
        job_dir = job_path.parent
        artifacts = sorted(p.name for p in job_dir.iterdir() if p.is_file())
        selected = data.get("selected_idea") or {}
        return {
            "job_id": data.get("id", job_dir.name),
            "output_path": str(job_dir.relative_to(root)),
            "content_type": data.get("content_type", ""),
            "idea_title": selected.get("title", ""),
            "stage": data.get("stage", ""),
            "artifacts": artifacts,
        }
    return None


def _activation_reviews(root: Path) -> list[dict]:
    reviews: list[dict] = []
    for activation_path in sorted((root / "projects").glob("*/scout_activation.yaml")):
        try:
            data = yaml.safe_load(activation_path.read_text()) or {}
        except yaml.YAMLError:
            data = {"status": "invalid", "scheduler_rotation_approved": False}
        slug = activation_path.parent.name
        approved = bool(data.get("scheduler_rotation_approved"))
        reviews.append({
            "slug": slug,
            "page_name": load_project_page_name(slug, root=root),
            "niche_name": data.get("niche_name", slug.replace("_", " ")),
            "source_report": data.get("source_report", ""),
            "status": data.get("status", "captain_review"),
            "approved": approved,
            "proof": _latest_dry_run_proof(root, slug),
        })
    return reviews


@router.get("/", response_class=HTMLResponse)
async def scout_index(request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    job = _latest_report(root)
    return templates.TemplateResponse(
        request,
        "scout.html",
        {"job": job, "activation_reviews": _activation_reviews(root)},
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


@router.post("/rotation/approve")
async def scout_rotation_approve(
    request: Request,
    project_slug: str = Form(...),
    _: str = Depends(verify_auth),
):
    root = _root(request)
    if not _PROJECT_SLUG_RE.match(project_slug):
        raise HTTPException(status_code=400, detail="Invalid project_slug")

    projects_dir = (root / "projects").resolve()
    project_dir = (projects_dir / project_slug).resolve()
    if not str(project_dir).startswith(str(projects_dir) + "/"):
        raise HTTPException(status_code=400, detail="Invalid project_slug")

    activation_path = project_dir / "scout_activation.yaml"
    if not activation_path.exists():
        raise HTTPException(status_code=404, detail="Scout activation marker not found")

    try:
        data = yaml.safe_load(activation_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail="Invalid scout activation marker") from exc
    data["scheduler_rotation_approved"] = True
    data["status"] = "rotation_approved"
    data["approved_at"] = datetime.now(timezone.utc).isoformat()
    activation_path.write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    return RedirectResponse(url="/scout/", status_code=303)


@router.post("/approve")
async def scout_approve(
    request: Request,
    job_id: str = Form(...),
    niche_name: str = Form(...),
    _: str = Depends(verify_auth),
):
    root = _root(request)

    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    reports_dir = (root / "output" / "scout_reports").resolve()
    report_path = (reports_dir / f"{job_id}-scout-report.json").resolve()
    if not str(report_path).startswith(str(reports_dir) + "/"):
        raise HTTPException(status_code=400, detail="Invalid job_id")

    def _background() -> None:
        try:
            cfg = Config.from_env()
            from scout_pipeline import approve_niche
            job = ScoutJob.model_validate_json(report_path.read_text())
            approve_niche(job, niche_name, cfg, projects_root=root / "projects")
        except Exception as exc:
            logger.error("Dashboard approve failed: %s", exc)

    threading.Thread(target=_background, daemon=True).start()
    return RedirectResponse(url="/scout/", status_code=303)
