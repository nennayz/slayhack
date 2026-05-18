"""Tests for /scout dashboard routes."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

os.environ.setdefault("DASHBOARD_USER", "admin")
os.environ.setdefault("DASHBOARD_PASSWORD", "8888")

import dashboard as _dm  # noqa: E402
from models.niche_opportunity import NicheOpportunity, ScoutJob, ScoutJobStatus  # noqa: E402


def _auth() -> dict:
    token = base64.b64encode(b"admin:8888").decode()
    return {"Authorization": f"Basic {token}"}


def _client(root: Path) -> TestClient:
    app = _dm.app
    app.state.root = root
    return TestClient(app, raise_server_exceptions=True)


def _saved_job(tmp_path: Path) -> ScoutJob:
    job = ScoutJob(
        job_id="20260517_120000",
        triggered_by="test",
        status=ScoutJobStatus.AWAITING_APPROVAL,
        opportunities=[
            NicheOpportunity(
                niche_name="clean beauty",
                target_audience="Women USA 22-38",
                platforms=["instagram"],
                reach_score=91.0,
                trend_direction="rising",
                content_formats=["reel"],
                monetization_notes="High affiliate",
                signals={},
            )
        ],
    )
    reports_dir = tmp_path / "output" / "scout_reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / f"{job.job_id}-scout-report.json").write_text(job.model_dump_json())
    return job


def _saved_activation_review(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "personal_finance_for_women"
    project_dir.mkdir(parents=True)
    (project_dir / "pm_profile.yaml").write_text(
        yaml.dump({
            "name": "Alex",
            "page_name": "PersonalFinanceForWomen",
            "persona": "Scout-created PM",
        })
    )
    (project_dir / "scout_activation.yaml").write_text(
        yaml.dump({
            "source": "scout",
            "source_report": "20260518_040508",
            "niche_name": "personal finance for women",
            "status": "captain_review",
            "scheduler_rotation_approved": False,
        })
    )
    proof_dir = tmp_path / "output" / "PersonalFinanceForWomen" / "20260518_041815_694380"
    proof_dir.mkdir(parents=True)
    (proof_dir / "job.json").write_text(json.dumps({
        "id": "20260518_041815_694380",
        "dry_run": True,
        "content_type": "article",
        "stage": "publish_done",
        "selected_idea": {"title": "Empowering Women Through Smart Investments"},
    }))
    for artifact in ["ideas.md", "bella_output.md", "growth.md", "faq.md"]:
        (proof_dir / artifact).write_text("proof")


# ── GET /scout/ ────────────────────────────────────────────────────────────


def test_scout_index_no_report(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/scout/", headers=_auth())
    assert resp.status_code == 200
    assert "Nothing scanned yet" in resp.text


def test_scout_index_shows_report(tmp_path):
    job = _saved_job(tmp_path)
    client = _client(tmp_path)
    resp = client.get("/scout/", headers=_auth())
    assert resp.status_code == 200
    assert job.job_id in resp.text
    assert "clean beauty" in resp.text


def test_scout_index_shows_activation_review_with_dry_run_proof(tmp_path):
    _saved_activation_review(tmp_path)
    client = _client(tmp_path)
    resp = client.get("/scout/", headers=_auth())
    assert resp.status_code == 200
    assert "Scout-created projects" in resp.text
    assert "PersonalFinanceForWomen" in resp.text
    assert "Dry-run proven" in resp.text
    assert "Not in live rotation" in resp.text
    assert "Empowering Women Through Smart Investments" in resp.text
    assert "Approve for scheduler rotation" in resp.text


def test_scout_index_requires_auth(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/scout/")
    assert resp.status_code == 401


# ── POST /scout/run ────────────────────────────────────────────────────────


def test_scout_run_redirects(tmp_path):
    client = _client(tmp_path)
    with patch("routes.scout.threading.Thread") as mock_thread:
        mock_thread.return_value = MagicMock()
        resp = client.post("/scout/run", headers=_auth(), follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/scout/")


def test_scout_run_requires_auth(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/scout/run", follow_redirects=False)
    assert resp.status_code == 401


# ── POST /scout/approve ────────────────────────────────────────────────────


def test_scout_approve_valid_job_id_redirects(tmp_path):
    job = _saved_job(tmp_path)
    client = _client(tmp_path)
    with patch("routes.scout.threading.Thread") as mock_thread:
        mock_thread.return_value = MagicMock()
        resp = client.post(
            "/scout/approve",
            data={"job_id": job.job_id, "niche_name": "clean beauty"},
            headers=_auth(),
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/scout/")


def test_scout_approve_invalid_job_id_format_returns_400(tmp_path):
    client = _client(tmp_path)
    resp = client.post(
        "/scout/approve",
        data={"job_id": "../../etc/passwd", "niche_name": "x"},
        headers=_auth(),
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_scout_approve_path_traversal_blocked(tmp_path):
    client = _client(tmp_path)
    for bad_id in ["../secrets", "20260517_120000/../evil", "20260517_120000\x00"]:
        resp = client.post(
            "/scout/approve",
            data={"job_id": bad_id, "niche_name": "x"},
            headers=_auth(),
            follow_redirects=False,
        )
        assert resp.status_code in (400, 422), f"Expected 400/422 for job_id={bad_id!r}"


def test_scout_approve_requires_auth(tmp_path):
    client = _client(tmp_path)
    resp = client.post(
        "/scout/approve",
        data={"job_id": "20260517_120000", "niche_name": "x"},
        follow_redirects=False,
    )
    assert resp.status_code == 401


# ── POST /scout/rotation/approve ───────────────────────────────────────────


def test_scout_rotation_approve_updates_marker(tmp_path):
    _saved_activation_review(tmp_path)
    client = _client(tmp_path)
    resp = client.post(
        "/scout/rotation/approve",
        data={"project_slug": "personal_finance_for_women"},
        headers=_auth(),
        follow_redirects=False,
    )
    assert resp.status_code == 303
    marker = yaml.safe_load(
        (tmp_path / "projects" / "personal_finance_for_women" / "scout_activation.yaml").read_text()
    )
    assert marker["scheduler_rotation_approved"] is True
    assert marker["status"] == "rotation_approved"
    assert "approved_at" in marker


def test_scout_rotation_approve_blocks_bad_slug(tmp_path):
    client = _client(tmp_path)
    resp = client.post(
        "/scout/rotation/approve",
        data={"project_slug": "../slay_hack"},
        headers=_auth(),
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_scout_rotation_approve_requires_auth(tmp_path):
    _saved_activation_review(tmp_path)
    client = _client(tmp_path)
    resp = client.post(
        "/scout/rotation/approve",
        data={"project_slug": "personal_finance_for_women"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
