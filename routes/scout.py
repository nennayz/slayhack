"""Scout pipeline dashboard routes."""
from __future__ import annotations

import logging
import json
import re
import shutil
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
_NICHE_SLUG_RE = re.compile(r"^[a-z0-9_]+$")


def _niche_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _load_report(root: Path, job_id: str) -> ScoutJob:
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    reports_dir = (root / "output" / "scout_reports").resolve()
    report_path = (reports_dir / f"{job_id}-scout-report.json").resolve()
    if not str(report_path).startswith(str(reports_dir) + "/"):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Scout report not found")
    return ScoutJob.model_validate_json(report_path.read_text())


def _find_opportunity(job: ScoutJob, niche_slug: str):
    if not _NICHE_SLUG_RE.match(niche_slug):
        raise HTTPException(status_code=400, detail="Invalid niche")
    for opp in job.opportunities:
        if _niche_slug(opp.niche_name) == niche_slug:
            return opp
    raise HTTPException(status_code=404, detail="Niche not found in report")


def _source_data(job: ScoutJob, opp) -> dict:
    for signal in job.signals:
        if signal.niche_name.lower() == opp.niche_name.lower():
            return signal.raw_data
    return opp.signals or {}


def _source_cards(source: dict, opp) -> list[dict]:
    brave = source.get("brave") or []
    trends = source.get("google_trends") or {}
    reddit = source.get("reddit") or {}
    meta = source.get("meta_ads") or {}
    reddit_subs = reddit.get("subreddits") or []
    return [
        {
            "name": "Brave Search",
            "status": "working" if brave else "missing",
            "summary": f"{len(brave)} search signals found" if brave else "No search examples captured",
        },
        {
            "name": "Google Trends",
            "status": "working" if trends and trends.get("trend_direction") != "unknown" else "limited",
            "summary": trends.get("trend_direction", opp.trend_direction),
        },
        {
            "name": "Reddit",
            "status": "working" if reddit_subs else "missing",
            "summary": f"{len(reddit_subs)} subreddit signals" if reddit_subs else "No Reddit credentials/signals",
        },
        {
            "name": "Meta Ads",
            "status": "working" if meta.get("active_ads") is not None else "limited",
            "summary": f"{meta.get('active_ads')} active ads sampled" if meta.get("active_ads") is not None else "Token/permission limited",
        },
    ]


def _project_review_status(root: Path, niche_name: str) -> dict:
    project_slug = _niche_slug(niche_name)
    project_dir = root / "projects" / project_slug
    activation_path = project_dir / "scout_activation.yaml"
    status = {"slug": project_slug, "exists": project_dir.exists(), "rotation_approved": False, "label": ""}
    if activation_path.exists():
        try:
            data = yaml.safe_load(activation_path.read_text()) or {}
        except yaml.YAMLError:
            data = {}
        status["rotation_approved"] = bool(data.get("scheduler_rotation_approved"))
        status["label"] = "Project in scheduler rotation" if status["rotation_approved"] else "Project created, pending rotation approval"
    elif project_dir.exists():
        status["label"] = "Project already exists"
    return status


def _scout_report_view(root: Path, job: ScoutJob, opp) -> dict:
    source = _source_data(job, opp)
    source_cards = _source_cards(source, opp)
    platforms = ", ".join(opp.platforms)
    formats = ", ".join(opp.content_formats)
    monetization_text = opp.monetization_notes.strip()
    monetization_score = 78
    money_keywords = ["affiliate", "e-book", "ebook", "course", "membership", "sponsor", "cpm", "newsletter", "coaching"]
    monetization_score += sum(3 for keyword in money_keywords if keyword in monetization_text.lower())
    trend_bonus = 8 if opp.trend_direction == "rising" else (2 if opp.trend_direction == "stable" else -8)
    source_confidence = 45 + sum(12 for card in source_cards if card["status"] == "working")

    score_cards = [
        {"label": "Viral potential", "score": _score(opp.reach_score + trend_bonus), "note": f"{opp.trend_direction} trend on {platforms}"},
        {"label": "Target clarity", "score": _score(65 + min(len(opp.target_audience), 80) / 2), "note": opp.target_audience},
        {"label": "Monetization", "score": _score(monetization_score), "note": monetization_text},
        {"label": "Content depth", "score": _score(58 + len(opp.content_formats) * 10 + len(opp.platforms) * 4), "note": formats},
        {"label": "Brand fit", "score": _score(82 if "women" in opp.target_audience.lower() else 70), "note": "Fits the current women 18-44 Scout brief"},
        {"label": "Source confidence", "score": _score(source_confidence), "note": "Based on unlocked data sources"},
    ]

    brave_items = source.get("brave") or []
    reddit_items = (source.get("reddit") or {}).get("subreddits") or []
    viral_drivers = [
        f"Reach score is {opp.reach_score:.0f}/100 with a {opp.trend_direction} trend read.",
        f"Best early formats: {formats}.",
    ]
    viral_drivers.extend(
        item.get("title") or item.get("description", "")
        for item in brave_items[:3]
        if item.get("title") or item.get("description")
    )
    viral_drivers.extend(
        f"r/{item.get('name')} has {item.get('subscribers', 0):,} subscribers"
        for item in reddit_items[:2]
        if item.get("name")
    )

    monetization_paths = [part.strip() for part in re.split(r"[,;]", monetization_text) if part.strip()]
    if not monetization_paths:
        monetization_paths = ["Lead magnet", "low-ticket digital product", "affiliate offers"]

    content_angles = [
        f"{opp.niche_name} myth vs fact",
        f"{opp.niche_name} beginner checklist",
        f"{opp.niche_name} mistake audit",
        f"{opp.niche_name} product or tool stack",
    ]

    recommendation = "Approve to create project" if opp.reach_score >= 80 else "Watchlist and gather more data"
    if _score(source_confidence) < 60:
        recommendation = "Need more source data before project approval"

    return {
        "job_id": job.job_id,
        "niche_slug": _niche_slug(opp.niche_name),
        "opportunity": opp,
        "project_status": _project_review_status(root, opp.niche_name),
        "summary": (
            f"{opp.niche_name} is a {opp.trend_direction} niche for {opp.target_audience}. "
            f"The opening is {formats} content on {platforms}, with monetization via {monetization_text}."
        ),
        "worth_opening": "High" if opp.reach_score >= 80 else ("Medium" if opp.reach_score >= 65 else "Low"),
        "recommendation": recommendation,
        "score_cards": score_cards,
        "source_cards": source_cards,
        "viral_drivers": [item for item in viral_drivers if item][:6],
        "target_profile": [
            f"Core audience: {opp.target_audience}",
            f"Primary platforms: {platforms}",
            f"Best starter formats: {formats}",
        ],
        "monetization_paths": monetization_paths[:6],
        "content_angles": content_angles,
        "risks": [
            "Approve project only after reading this report.",
            "Missing Reddit or Meta Ads data lowers confidence until credentials are unlocked.",
            "Run a dry-run proof before scheduler rotation.",
        ],
    }


def _compare_rows(root: Path, job: ScoutJob | None) -> list[dict]:
    if not job:
        return []
    rows = []
    for opp in sorted(job.opportunities, key=lambda item: item.reach_score, reverse=True):
        report = _scout_report_view(root, job, opp)
        score_lookup = {card["label"]: card["score"] for card in report["score_cards"]}
        source_working = sum(1 for card in report["source_cards"] if card["status"] == "working")
        rows.append({
            "slug": report["niche_slug"],
            "niche_name": opp.niche_name,
            "target": opp.target_audience,
            "viral_score": score_lookup.get("Viral potential", _score(opp.reach_score)),
            "monetization_score": score_lookup.get("Monetization", 0),
            "target_score": score_lookup.get("Target clarity", 0),
            "confidence_score": score_lookup.get("Source confidence", 0),
            "worth_opening": report["worth_opening"],
            "recommendation": report["recommendation"],
            "project_label": report["project_status"]["label"] or "Report only",
            "source_count": source_working,
            "monetization": opp.monetization_notes,
            "formats": ", ".join(opp.content_formats),
            "report_url": f"/scout/reports/{job.job_id}/{report['niche_slug']}",
        })
    return rows


def _latest_report(root: Path) -> ScoutJob | None:
    reports_dir = root / "output" / "scout_reports"
    if not reports_dir.exists():
        return None
    reports = sorted(reports_dir.glob("*.json"), reverse=True)
    if not reports:
        return None
    return ScoutJob.model_validate_json(reports[0].read_text())


@router.get("/reports/{job_id}/{niche_slug}", response_class=HTMLResponse)
async def scout_report_detail(
    request: Request,
    job_id: str,
    niche_slug: str,
    _: str = Depends(verify_auth),
):
    root = _root(request)
    job = _load_report(root, job_id)
    opp = _find_opportunity(job, niche_slug)
    return templates.TemplateResponse(
        request,
        "scout_report.html",
        {"job": job, "report": _scout_report_view(root, job, opp)},
    )


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
            "can_delete": data.get("source") == "scout",
        })
    return reviews


@router.get("/", response_class=HTMLResponse)
async def scout_index(request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    job = _latest_report(root)
    return templates.TemplateResponse(
        request,
        "scout.html",
        {
            "job": job,
            "opportunity_reports": [
                {"opportunity": opp, "slug": _niche_slug(opp.niche_name)}
                for opp in (job.opportunities if job else [])
            ],
            "compare_rows": _compare_rows(root, job),
            "activation_reviews": _activation_reviews(root),
        },
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


@router.post("/projects/delete")
async def scout_project_delete(
    request: Request,
    project_slug: str = Form(...),
    confirm_slug: str = Form(...),
    _: str = Depends(verify_auth),
):
    root = _root(request)
    if not _PROJECT_SLUG_RE.match(project_slug) or confirm_slug != project_slug:
        raise HTTPException(status_code=400, detail="Invalid project delete confirmation")

    projects_dir = (root / "projects").resolve()
    project_dir = (projects_dir / project_slug).resolve()
    if not str(project_dir).startswith(str(projects_dir) + "/"):
        raise HTTPException(status_code=400, detail="Invalid project_slug")

    activation_path = project_dir / "scout_activation.yaml"
    if not activation_path.exists():
        raise HTTPException(status_code=404, detail="Only Scout-created projects can be deleted here")

    try:
        activation_data = yaml.safe_load(activation_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail="Invalid scout activation marker") from exc
    if activation_data.get("source") != "scout":
        raise HTTPException(status_code=403, detail="Only Scout-created projects can be deleted here")

    archive_dir = root / "vault" / "deleted_projects"
    archive_dir.mkdir(parents=True, exist_ok=True)
    destination = archive_dir / project_slug
    if destination.exists():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = archive_dir / f"{project_slug}-{timestamp}"
    shutil.move(str(project_dir), str(destination))
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

    def _background() -> None:
        try:
            cfg = Config.from_env()
            from scout_pipeline import approve_niche
            job = _load_report(root, job_id)
            approve_niche(job, niche_name, cfg, projects_root=root / "projects")
        except Exception as exc:
            logger.error("Dashboard approve failed: %s", exc)

    threading.Thread(target=_background, daemon=True).start()
    return RedirectResponse(url="/scout/", status_code=303)
