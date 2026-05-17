"""Shared FastAPI app, templates, auth, and helpers used by all route modules."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

DASHBOARD_USER = os.environ.get("DASHBOARD_USER")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD")
if not DASHBOARD_USER or not DASHBOARD_PASSWORD:
    raise RuntimeError(
        "DASHBOARD_USER and DASHBOARD_PASSWORD must be set in environment before starting the dashboard."
    )

_ROOT = Path(__file__).resolve().parent.parent

VALID_CONTENT_TYPES = {"video", "article", "image", "infographic"}
MAX_BRIEF_LEN = 2000
OPS_PUBLIC_BASE_URL = os.environ.get("OPS_PUBLIC_BASE_URL", "https://fleet.nayzfreedom.cloud").rstrip("/")
OPS_UNITS = [
    "nayzfreedom-dashboard.service",
    "nayzfreedom-bot.service",
    "nayzfreedom-scheduler.timer",
    "nayzfreedom-reporter.timer",
    "nayzfreedom-instagram-queue.timer",
    "nayzfreedom-backup.timer",
    "nayzfreedom-healthcheck.timer",
    "nayzfreedom-production-summary.timer",
    "nayzfreedom-log-retention.timer",
    "nayzfreedom-ops-report.timer",
]
OPS_ACTIONS = {
    "backup": {
        "label": "Run backup now",
        "unit": "nayzfreedom-backup.service",
        "verb": "start",
    },
    "instagram_queue": {
        "label": "Run due Instagram queue now",
        "unit": "nayzfreedom-instagram-queue.service",
        "verb": "start",
    },
    "production_summary": {
        "label": "Run production summary now",
        "unit": "nayzfreedom-production-summary.service",
        "verb": "start",
    },
    "ops_report": {
        "label": "Send Ops report now",
        "unit": "nayzfreedom-ops-report.service",
        "verb": "start",
    },
    "restart_dashboard": {
        "label": "Restart dashboard",
        "unit": "nayzfreedom-dashboard.service",
        "verb": "restart",
        "delayed": True,
    },
}

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(_ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(_ROOT / "templates"))
security = HTTPBasic()


def _status_label(value: object) -> str:
    raw = getattr(value, "value", str(value))
    return raw.replace("_", " ").title()


def verify_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    correct_user = secrets.compare_digest(credentials.username, DASHBOARD_USER)
    correct_pass = secrets.compare_digest(credentials.password, DASHBOARD_PASSWORD)
    if not (correct_user and correct_pass):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    return credentials.username


def _root(request: Request) -> Path:
    return getattr(request.app.state, "root", _ROOT)


# Apply template filters and globals — imported lazily to avoid circular deps
def _apply_template_extras() -> None:
    from routes._helpers import (
        _status_label as _sl,
        _publish_status_items,
        _publish_history_items,
    )
    templates.env.filters["status_label"] = _sl
    templates.env.globals["publish_status_items"] = _publish_status_items
    templates.env.globals["publish_history_items"] = _publish_history_items


_apply_template_extras()
