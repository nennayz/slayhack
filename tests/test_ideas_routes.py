"""Tests for /ideas dashboard routes."""
from __future__ import annotations

import base64
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from knowledge.embedder import Embedder
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore

os.environ.setdefault("DASHBOARD_USER", "admin")
os.environ.setdefault("DASHBOARD_PASSWORD", "8888")
os.environ.setdefault("PUBLIC_BASE_URL", "http://localhost")
os.environ.setdefault("OPS_PUBLIC_BASE_URL", "http://localhost")

import dashboard as _dm  # noqa: E402


def _auth() -> dict:
    token = base64.b64encode(b"admin:8888").decode()
    return {"Authorization": f"Basic {token}"}


def _client(root: Path) -> TestClient:
    app = _dm.app
    app.state.root = root
    return TestClient(app, raise_server_exceptions=True, follow_redirects=False)


@pytest.fixture
def store(tmp_path):
    settings = KnowledgeSettings(root=tmp_path)
    embedder = Embedder("test", embed_fn=lambda texts: [[0.0] * 4 for _ in texts])
    return KnowledgeStore(settings, embedder)


def _add_idea(store: KnowledgeStore, title: str, n: int) -> ContentObject:
    obj = ContentObject(
        page="nayzfreedom_fleet",
        kind="idea",
        title=title,
        dedup_text=f"{title}|nayzfreedom_fleet|20260519|{n}",
        body=f"## {title}\n\n**Hook:** test hook\n",
        tags=["video", "Tutorial", "nayzfreedom_fleet"],
        status="new",
    )
    return store.add(obj, embed=False)


def test_ideas_list_returns_200(tmp_path, store):
    with patch("routes.ideas._get_store", return_value=store):
        resp = _client(tmp_path).get("/ideas", headers=_auth())
    assert resp.status_code == 200


def test_ideas_list_no_auth_returns_401(tmp_path):
    resp = _client(tmp_path).get("/ideas")
    assert resp.status_code == 401


def test_approve_idea_redirects(tmp_path, store):
    obj = _add_idea(store, "Approve Test Idea", 1)
    with patch("routes.ideas._get_store", return_value=store):
        resp = _client(tmp_path).post(f"/ideas/{obj.uid}/approve", headers=_auth())
    assert resp.status_code == 303
    assert resp.headers["location"] == "/ideas?status=new"
    updated = store.get(obj.uid)
    assert updated is not None and updated.status == "approved"


def test_reject_idea_redirects(tmp_path, store):
    obj = _add_idea(store, "Reject Test Idea", 2)
    with patch("routes.ideas._get_store", return_value=store):
        resp = _client(tmp_path).post(f"/ideas/{obj.uid}/reject", headers=_auth())
    assert resp.status_code == 303
    assert resp.headers["location"] == "/ideas?status=new"
    updated = store.get(obj.uid)
    assert updated is not None and updated.status == "rejected"


def test_approve_unknown_uid_returns_404(tmp_path, store):
    with patch("routes.ideas._get_store", return_value=store):
        resp = _client(tmp_path).post("/ideas/no-such-uid/approve", headers=_auth())
    assert resp.status_code == 404


def test_generate_returns_202(tmp_path, store):
    with patch("routes.ideas._run_pipeline_background"):
        resp = _client(tmp_path).post("/ideas/generate/nayzfreedom_fleet", headers=_auth())
    assert resp.status_code == 202
    assert resp.json()["status"] == "started"


def test_generate_invalid_slug_returns_400(tmp_path):
    resp = _client(tmp_path).post("/ideas/generate/bad slug!", headers=_auth())
    assert resp.status_code == 400


def test_status_filter_approved_reflects_set_status(tmp_path, store):
    obj = _add_idea(store, "Status Filter Test", 3)
    store.set_status(obj.uid, "approved")
    with patch("routes.ideas._get_store", return_value=store):
        resp = _client(tmp_path).get(
            "/ideas?page=nayzfreedom_fleet&status=approved", headers=_auth()
        )
    assert resp.status_code == 200


def test_ideas_list_renders_fleet_html(tmp_path, store):
    _add_idea(store, "Fleet HTML Test Idea", 99)
    with patch("routes.ideas._get_store", return_value=store):
        resp = _client(tmp_path).get("/ideas", headers=_auth())
    assert resp.status_code == 200
    assert "Fleet HTML Test Idea" in resp.text
    assert "Idea Bank" in resp.text
    assert "Generate Ideas Now" in resp.text
