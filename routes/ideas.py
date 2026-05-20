"""Idea bank dashboard routes."""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from routes.deps import _root, templates, verify_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ideas", tags=["ideas"])
_SLUG_RE = re.compile(r"^[a-z0-9_]+$")


def _get_store(root: Path) -> Any:
    """Build a KnowledgeStore. Accepts root so tests can inject via patch."""
    import os

    from knowledge.embedder import Embedder, openai_embed_fn
    from knowledge.settings import KnowledgeSettings
    from knowledge.store import KnowledgeStore

    settings = KnowledgeSettings.from_env(root)
    api_key = os.getenv("OPENAI_API_KEY", "")
    embed_fn = openai_embed_fn(settings.embed_model, api_key)
    return KnowledgeStore(settings, Embedder(settings.embed_model, embed_fn=embed_fn))


def _run_pipeline_background(page_slug: str, root: Path, dry_run: bool = False) -> None:
    try:
        from config import Config
        from idea_planner_pipeline import run_idea_planner_pipeline

        cfg = Config.from_env()
        store = _get_store(root)
        job = run_idea_planner_pipeline(page_slug, cfg, store, dry_run=dry_run)
        logger.info(
            "Dashboard idea planner done: page=%s stored=%d skipped=%d",
            page_slug,
            job.ideas_stored,
            job.ideas_skipped,
        )
    except Exception as exc:
        logger.error("Dashboard idea planner failed for %s: %s", page_slug, exc)


@router.get("", response_class=HTMLResponse)
async def ideas_list(
    request: Request,
    page: str | None = None,
    status: str | None = None,
    _: str = Depends(verify_auth),
) -> HTMLResponse:
    root = _root(request)
    store = _get_store(root)
    ideas = store.recent(
        kind="idea",
        page=page or None,
        status=status or None,
        limit=50,
    )
    return templates.TemplateResponse(
        request,
        "ideas/list.html",
        {"ideas": ideas, "filter_page": page or "", "filter_status": status or ""},
    )


@router.post("/{uid}/approve")
async def approve_idea(
    uid: str,
    request: Request,
    _: str = Depends(verify_auth),
) -> JSONResponse:
    root = _root(request)
    store = _get_store(root)
    try:
        updated = store.set_status(uid, "approved")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Idea {uid!r} not found") from exc
    return JSONResponse({"uid": updated.uid, "status": updated.status})


@router.post("/{uid}/reject")
async def reject_idea(
    uid: str,
    request: Request,
    _: str = Depends(verify_auth),
) -> JSONResponse:
    root = _root(request)
    store = _get_store(root)
    try:
        updated = store.set_status(uid, "rejected")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Idea {uid!r} not found") from exc
    return JSONResponse({"uid": updated.uid, "status": updated.status})


@router.post("/generate/{page_slug}")
async def generate_ideas(
    page_slug: str,
    request: Request,
    _: str = Depends(verify_auth),
) -> JSONResponse:
    if not _SLUG_RE.match(page_slug):
        raise HTTPException(status_code=400, detail="Invalid page_slug")
    root = _root(request)
    threading.Thread(
        target=_run_pipeline_background, args=(page_slug, root), daemon=True
    ).start()
    return JSONResponse({"status": "started", "page_slug": page_slug}, status_code=202)
