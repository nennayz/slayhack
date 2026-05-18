"""Minimal project administration dashboard routes."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.responses import HTMLResponse

from routes.deps import _root, templates, verify_auth

router = APIRouter(prefix="/project-admin", tags=["project-admin"])


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def _mask_chat_id(chat_id: object) -> str:
    text = str(chat_id)
    if len(text) <= 5:
        return "***"
    return f"{text[:2]}***{text[-4:]}"


def _active_project_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pm_path in sorted((root / "projects").glob("*/pm_profile.yaml")):
        project_dir = pm_path.parent
        if project_dir.name.startswith("."):
            continue
        pm = _read_yaml(pm_path)
        brand = _read_yaml(project_dir / "brand.yaml")
        activation = _read_yaml(project_dir / "scout_activation.yaml")
        rows.append(
            {
                "slug": project_dir.name,
                "page_name": pm.get("page_name", project_dir.name),
                "pm": pm.get("name", ""),
                "platforms": brand.get("platforms") or [],
                "source": activation.get("source") or "fleet",
                "rotation": "approved" if activation.get("scheduler_rotation_approved") else ("pending" if activation else "n/a"),
            }
        )
    return rows


def _archived_project_rows(root: Path) -> list[dict[str, Any]]:
    archive_dir = root / "vault" / "deleted_projects"
    if not archive_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for project_dir in sorted(path for path in archive_dir.iterdir() if path.is_dir()):
        pm = _read_yaml(project_dir / "pm_profile.yaml")
        activation = _read_yaml(project_dir / "scout_activation.yaml")
        rows.append(
            {
                "slug": project_dir.name,
                "page_name": pm.get("page_name", project_dir.name),
                "source": activation.get("source") or "archived",
                "status": activation.get("status") or "archived",
            }
        )
    return rows


def _output_only_rows(root: Path, active_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output_dir = root / "output"
    if not output_dir.exists():
        return []
    active_page_names = {str(row["page_name"]) for row in active_rows}
    system_dirs = {"scout_reports", "comment_reply_log", "track_queue_history"}
    rows: list[dict[str, Any]] = []
    for page_dir in sorted(path for path in output_dir.iterdir() if path.is_dir()):
        if page_dir.name in active_page_names or page_dir.name in system_dirs:
            continue
        job_dirs = [path for path in page_dir.iterdir() if path.is_dir()]
        rows.append({"page_name": page_dir.name, "jobs": len(job_dirs), "path": str(page_dir.relative_to(root))})
    return rows


def _comment_chat_rows(root: Path) -> list[dict[str, Any]]:
    chat_map_path = Path(os.getenv("COMMENT_CHAT_MAP_PATH", str(root / "comment_chat_map.yaml")))
    if not chat_map_path.exists():
        chat_map_path = root / "comment_chat_map.yaml"
    data = _read_yaml(chat_map_path)
    rows: list[dict[str, Any]] = []
    for chat_id, cfg in sorted((data.get("chats") or {}).items(), key=lambda item: str(item[0])):
        rows.append(
            {
                "chat_id": _mask_chat_id(chat_id),
                "project": cfg.get("project", ""),
                "default_platform": cfg.get("default_platform", ""),
            }
        )
    return rows


def _comment_log_rows(root: Path) -> list[dict[str, Any]]:
    log_dir = root / "output" / "comment_reply_log"
    if not log_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for log_path in sorted(log_dir.glob("*.jsonl")):
        count = 0
        last_ts = ""
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            count += 1
            try:
                last_ts = json.loads(line).get("timestamp", last_ts)
            except json.JSONDecodeError:
                continue
        rows.append({"project": log_path.stem, "entries": count, "last_timestamp": last_ts})
    return rows


@router.get("/", response_class=HTMLResponse)
async def project_admin_index(request: Request, _: str = Depends(verify_auth)):
    root = _root(request)
    active_projects = _active_project_rows(root)
    return templates.TemplateResponse(
        request,
        "project_admin.html",
        {
            "active_projects": active_projects,
            "archived_projects": _archived_project_rows(root),
            "output_only_rows": _output_only_rows(root, active_projects),
            "comment_chat_rows": _comment_chat_rows(root),
            "comment_log_rows": _comment_log_rows(root),
        },
    )
