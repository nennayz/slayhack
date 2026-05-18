from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("DASHBOARD_USER", "admin")
os.environ.setdefault("DASHBOARD_PASSWORD", "8888")

import dashboard as _dm  # noqa: E402


def _auth() -> dict:
    token = base64.b64encode(b"admin:8888").decode()
    return {"Authorization": f"Basic {token}"}


def _client(root: Path) -> TestClient:
    app = _dm.app
    app.state.root = root
    return TestClient(app, raise_server_exceptions=True)


def _write_project(root: Path, slug: str, page_name: str) -> None:
    project_dir = root / "projects" / slug
    project_dir.mkdir(parents=True)
    (project_dir / "pm_profile.yaml").write_text(
        f"name: Slay\npage_name: {page_name}\npersona: PM\n",
        encoding="utf-8",
    )
    (project_dir / "brand.yaml").write_text(
        "mission: test\nplatforms: [instagram, tiktok]\ntone: smart\ntarget_audience: women\nscript_style: concise\nvisual:\n  colors: ['#fff']\n  style: clean\n",
        encoding="utf-8",
    )


def test_project_admin_shows_active_output_only_chat_and_logs(tmp_path, monkeypatch):
    _write_project(tmp_path, "slay_hack", "SlayHack")
    output_only = tmp_path / "output" / "PersonalFinanceForWomen" / "20260518_041815_694380"
    output_only.mkdir(parents=True)
    (output_only / "job.json").write_text("{}", encoding="utf-8")
    log_dir = tmp_path / "output" / "comment_reply_log"
    log_dir.mkdir(parents=True)
    (log_dir / "slay_hack.jsonl").write_text(
        json.dumps({"timestamp": "2026-05-18T08:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    chat_map = tmp_path / "secrets" / "comment_chat_map.yaml"
    chat_map.parent.mkdir()
    chat_map.write_text(
        "chats:\n  '-5210714067':\n    project: slay_hack\n    default_platform: instagram\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("COMMENT_CHAT_MAP_PATH", str(chat_map))

    resp = _client(tmp_path).get("/project-admin/", headers=_auth())
    assert resp.status_code == 200
    assert "Project Admin" in resp.text
    assert "SlayHack" in resp.text
    assert "PersonalFinanceForWomen" in resp.text
    assert "Output only" in resp.text
    assert "slay_hack" in resp.text
    assert "***4067" in resp.text
    assert "Reply history" in resp.text
    assert "2026-05-18T08:00:00Z" in resp.text


def test_project_admin_handles_mixed_string_and_numeric_chat_ids(tmp_path, monkeypatch):
    _write_project(tmp_path, "slay_hack", "SlayHack")
    chat_map = tmp_path / "comment_chat_map.yaml"
    chat_map.write_text(
        "chats:\n"
        "  -5210714067:\n"
        "    project: slay_hack\n"
        "    default_platform: instagram\n"
        "  '-5271108012':\n"
        "    project: stadium_sweethearts\n"
        "    default_platform: tiktok\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("COMMENT_CHAT_MAP_PATH", str(chat_map))

    resp = _client(tmp_path).get("/project-admin/", headers=_auth())
    assert resp.status_code == 200
    assert "slay_hack" in resp.text
    assert "stadium_sweethearts" in resp.text


def test_project_admin_requires_auth(tmp_path):
    resp = _client(tmp_path).get("/project-admin/")
    assert resp.status_code == 401
