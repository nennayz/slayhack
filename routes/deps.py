"""Shared FastAPI app, templates, auth, and helpers used by all route modules."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from ops_config import OPS_ACTIONS, OPS_PUBLIC_BASE_URL, OPS_UNITS  # noqa: F401

DASHBOARD_USER = os.environ.get("DASHBOARD_USER")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD")
if not DASHBOARD_USER or not DASHBOARD_PASSWORD:
    raise RuntimeError(
        "DASHBOARD_USER and DASHBOARD_PASSWORD must be set in environment before starting the dashboard."
    )

_DASHBOARD_USER: str = DASHBOARD_USER
_DASHBOARD_PASSWORD: str = DASHBOARD_PASSWORD

_ROOT = Path(__file__).resolve().parent.parent

VALID_CONTENT_TYPES = {"video", "article", "image", "infographic"}
MAX_BRIEF_LEN = 2000

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(_ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(_ROOT / "templates"))
security = HTTPBasic()


def _status_label(value: object) -> str:
    raw = getattr(value, "value", str(value))
    return raw.replace("_", " ").title()


def verify_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    correct_user = secrets.compare_digest(credentials.username, _DASHBOARD_USER)
    correct_pass = secrets.compare_digest(credentials.password, _DASHBOARD_PASSWORD)
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
