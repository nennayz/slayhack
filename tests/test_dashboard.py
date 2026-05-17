from __future__ import annotations
import base64
import html
import json
import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

# Set env vars before dashboard is first imported in this process
os.environ["DASHBOARD_USER"] = "admin"
os.environ["DASHBOARD_PASSWORD"] = "8888"

import dashboard as _dm  # noqa: E402


def _auth(user: str = "admin", pw: str = "8888") -> dict:
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _section_after_eyebrow(page: str, eyebrow: str) -> str:
    return page.split(f'<p class="eyebrow">{eyebrow}</p>', 1)[1].split("</section>", 1)[0]


def _make_pm_dict(page_name: str = "Slayhack") -> dict:
    return {
        "name": "Test PM", "page_name": page_name, "persona": "",
        "brand": {
            "mission": "m", "visual": {"colors": [], "style": ""},
            "platforms": [], "tone": "", "target_audience": "",
            "script_style": "", "nora_max_retries": 2,
        },
    }


def _write_job(tmp_path: Path, job_id: str, brief: str = "test brief",
               status: str = "completed", page: str = "Slayhack",
               stage: str = "init", publish_result: dict | None = None,
               performance: list[dict] | None = None,
               manual_post_kit: dict | None = None,
               published_at: str | None = None,
               video_package: dict | None = None,
               production_ticket: dict | None = None) -> None:
    job = {
        "id": job_id, "project": "nayzfreedom_fleet", "pm": _make_pm_dict(page),
        "brief": brief, "platforms": ["facebook"], "status": status,
        "stage": stage, "dry_run": False, "performance": performance or [], "checkpoint_log": [],
    }
    if publish_result is not None:
        job["publish_result"] = publish_result
    if manual_post_kit is not None:
        job["manual_post_kit"] = manual_post_kit
    if published_at is not None:
        job["published_at"] = published_at
    if video_package is not None:
        job["video_package"] = video_package
    if production_ticket is not None:
        job["production_ticket"] = production_ticket
    job_dir = tmp_path / "output" / page / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "job.json").write_text(json.dumps(job))


def _write_slay_hack_project(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "slay_hack"
    project_dir.mkdir(parents=True)
    (project_dir / "pm_profile.yaml").write_text(
        'name: "Slay"\npage_name: "Slay Hack"\npersona: "PM for Slay Hack"\n'
    )
    (project_dir / "brand.yaml").write_text(
        'mission: "beauty content"\nvisual:\n  colors: ["#fff"]\n  style: "warm 3D"\n'
        'platforms: ["instagram", "facebook", "tiktok", "youtube"]\ntone: "sassy"\n'
        'target_audience: "Gen Z women"\nscript_style: "bestie"\n'
        'allowed_content_types: ["video", "image", "infographic", "article"]\n'
    )
    (project_dir / "weekly_calendar.yaml").write_text(
        'monday:\n'
        '  short_video_1: "Quick hack"\n'
        '  long_video: "Long story episode"\n'
        '  article_1: "Guide one"\n'
        '  article_2: "Guide two"\n'
        '  infographic_1: "Save card one"\n'
        '  infographic_2: "Save card two"\n'
    )


def _write_stadium_project(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "stadium_sweethearts"
    project_dir.mkdir(parents=True)
    (project_dir / "pm_profile.yaml").write_text(
        'name: "Stadium"\npage_name: "Stadium Sweethearts"\npersona: "PM for sporty fan-cam content"\n'
    )
    (project_dir / "brand.yaml").write_text(
        'mission: "sporty fan-cam stories"\nvisual:\n  colors: ["#0047ab", "#ffffff"]\n  style: "glossy sports editorial"\n'
        'platforms: ["instagram", "facebook", "tiktok", "youtube"]\ntone: "playful"\n'
        'target_audience: "sports fans"\nscript_style: "stadium bestie"\n'
        'allowed_content_types: ["video", "image", "infographic", "article"]\n'
    )
    (project_dir / "weekly_calendar.yaml").write_text(
        'monday:\n'
        '  short_video_1: "Touchdown Reaction"\n'
        '  long_video: "Game day glow-up story"\n'
        '  article_1: "Fan-cam safety notes"\n'
        '  infographic_1: "Replayable moments card"\n'
    )


def _slay_hack_ticket_id(tmp_path: Path, suffix: str) -> str:
    slate = _dm._calendar_slate(tmp_path)
    assert slate is not None
    return next(ticket.ticket_id for ticket in slate.tickets if ticket.ticket_id.endswith(suffix))


def _project_ticket_id(tmp_path: Path, project_slug: str, suffix: str) -> str:
    slate = _dm._calendar_slate(tmp_path, project_slug)
    assert slate is not None
    return next(ticket.ticket_id for ticket in slate.tickets if ticket.ticket_id.endswith(suffix))


def test_healthz_does_not_require_auth(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "nayzfreedom-dashboard"}


def test_public_media_serves_job_file_without_auth(tmp_path, client):
    media_dir = tmp_path / "output" / "Slayhack" / "20260512_060000"
    media_dir.mkdir(parents=True)
    (media_dir / "image.png").write_bytes(b"PNG")

    resp = client.get("/media/public/20260512_060000/image.png")

    assert resp.status_code == 200
    assert resp.content == b"PNG"


def test_public_media_rejects_unknown_or_unsupported_file(tmp_path, client):
    media_dir = tmp_path / "output" / "Slayhack" / "20260512_060000"
    media_dir.mkdir(parents=True)
    (media_dir / "secret.txt").write_text("secret")

    resp = client.get("/media/public/20260512_060000/secret.txt")

    assert resp.status_code == 404


def test_meta_policy_pages_do_not_require_auth(client):
    privacy = client.get("/privacy")
    deletion = client.get("/data-deletion")
    deletion_html = client.get("/data_deletion.html")
    privacy_head = client.head("/privacy")
    deletion_head = client.head("/data-deletion")
    deletion_html_head = client.head("/data_deletion.html")

    assert privacy.status_code == 200
    assert "Privacy Policy" in privacy.text
    assert deletion.status_code == 200
    assert "Data Deletion" in deletion.text
    assert deletion_html.status_code == 200
    assert "Data Deletion" in deletion_html.text
    assert privacy_head.status_code == 200
    assert deletion_head.status_code == 200
    assert deletion_html_head.status_code == 200


def test_meta_data_deletion_callback_returns_confirmation(client, monkeypatch):
    monkeypatch.delenv("META_APP_SECRET", raising=False)
    payload = base64.urlsafe_b64encode(json.dumps({"user_id": "12345"}).encode()).decode().rstrip("=")
    signed_request = f"unused.{payload}"

    resp = client.post(
        "/data-deletion-callback",
        data={"signed_request": signed_request},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["url"] == "https://fleet.nayzfreedom.cloud/data-deletion"
    assert body["confirmation_code"].startswith("slayhack-delete-")


@pytest.fixture
def client(tmp_path):
    _dm.app.state.root = tmp_path
    return TestClient(_dm.app, raise_server_exceptions=True)


def test_dashboard_requires_auth(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 401


def test_dashboard_wrong_credentials(client):
    resp = client.get("/", headers=_auth("admin", "wrong"))
    assert resp.status_code == 401


def test_captains_deck_empty(client):
    resp = client.get("/", headers=_auth())
    assert resp.status_code == 200
    assert "NayzFreedom Fleet" in resp.text
    assert "Aurora / SlayHack" in resp.text
    assert "Captain's Deck" in resp.text
    assert "fleet-hero-command" in resp.text
    assert "Ready for first mission" in resp.text
    assert "Nami comes after privacy and memory boundaries are clear" in resp.text
    assert "Genie comes after the Fleet shell is stable" in resp.text
    assert "Filter log" in resp.text
    assert "Launch the first Aurora mission when the brief is ready." in resp.text
    assert "Next best action" in resp.text
    assert "Captain Action Console" in resp.text
    assert "Route Map" in resp.text
    assert "Shipyard" in resp.text
    assert "Harbor Gate" in resp.text
    assert "Captain Log" in resp.text
    assert "Captain Attention Lane" in resp.text
    assert "Captain lane clear" in resp.text
    assert "Do now" in resp.text
    assert "System did" in resp.text
    assert "Waiting on" in resp.text
    assert "Open Daily Slate" in resp.text
    assert "Learning Runbook" in resp.text
    assert "Learning loop clear" in resp.text
    assert "No missions yet" in resp.text


def test_captains_deck_shows_recent_mission(tmp_path, client):
    _write_job(tmp_path, "20260512_060000", brief="luxury brands rock")
    resp = client.get("/", headers=_auth())
    assert resp.status_code == 200
    assert "luxury brands rock" in resp.text


def test_captains_deck_surfaces_attention_and_active_missions(tmp_path, client):
    _write_job(tmp_path, "20260512_060000", brief="needs review", status="failed")
    _write_job(tmp_path, "20260513_060000", brief="still moving", status="running")

    resp = client.get("/", headers=_auth())

    assert resp.status_code == 200
    assert "Command priority" in resp.text
    assert "Review failed missions before launching new work." in resp.text
    assert "Captain Attention Lane" in resp.text
    assert "1 mission needs Captain attention." in resp.text
    assert "Open priority mission" in resp.text
    assert "Needs attention" in resp.text
    assert "needs review" in resp.text
    assert "Active missions" in resp.text
    assert "still moving" in resp.text
    assert "Failed" in resp.text
    assert "Running" in resp.text


def test_captains_deck_prioritizes_synced_manual_kits(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_synced",
        brief="synced kit mission",
        manual_post_kit={
            "drive_sync": {
                "status": "synced",
                "synced_at": "2026-05-17T13:00:00+00:00",
                "web_view_link": "https://drive.google.com/file/d/synced/view",
            }
        },
    )

    deck = client.get("/", headers=_auth())
    aurora = client.get("/aurora", headers=_auth())

    assert deck.status_code == 200
    assert aurora.status_code == 200
    deck_lane = _section_after_eyebrow(deck.text, "Captain Attention Lane")
    aurora_lane = _section_after_eyebrow(aurora.text, "Captain Attention Lane")
    assert "1 manual posting handoff needs queue follow-through." in deck_lane
    assert "Kit synced, not posted" in deck_lane
    assert "synced kit mission" in deck_lane
    assert "/aurora/manual-posting?lane=kit_synced&amp;focus=20260512_synced#manual-job-20260512_synced" in deck_lane
    assert "Open manual queue" in deck_lane
    assert "Kit synced, not posted" in aurora_lane


def test_captains_deck_surfaces_manual_closeout_attention(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_closeout",
        brief="manual closeout ready",
        status="completed",
        manual_post_kit={
            "manual_post": {
                "instagram": {
                    "status": "posted",
                    "post_url": "https://www.instagram.com/p/closeout/",
                    "posted_at": "2026-05-17T14:00:00+00:00",
                }
            }
        },
        performance=[
            {"platform": "instagram", "reach": 100, "recorded_at": "2026-05-18T14:00:00+00:00"},
            {"platform": "instagram", "reach": 180, "recorded_at": "2026-05-20T14:00:00+00:00"},
        ],
    )
    _write_job(
        tmp_path,
        "20260512_closed",
        brief="manual closeout closed",
        status="completed",
        manual_post_kit={
            "manual_post": {
                "instagram": {
                    "status": "posted",
                    "post_url": "https://www.instagram.com/p/closed/",
                    "posted_at": "2026-05-17T13:00:00+00:00",
                }
            },
            "closeout": {
                "status": "closed",
                "learning_note": "Already captured.",
                "proof_summary": {
                    "post_url_present": True,
                    "snapshot_24h_present": True,
                    "snapshot_72h_present": True,
                    "learning_note_captured": True,
                },
            },
        },
        performance=[
            {"platform": "instagram", "reach": 90, "recorded_at": "2026-05-18T13:00:00+00:00"},
            {"platform": "instagram", "reach": 130, "recorded_at": "2026-05-20T13:00:00+00:00"},
        ],
    )

    resp = client.get("/", headers=_auth())

    assert resp.status_code == 200
    assert "Needs Captain" in resp.text
    assert "Close manual posting lessons before launching more manual handoffs." in resp.text
    assert "1 manual post ready for closeout." in resp.text
    assert "Captain Attention Lane" in resp.text
    assert "Learning Runbook" in resp.text
    assert "Capture closeout lesson" in resp.text
    assert "Open manual closeout" in resp.text
    attention_lane = _section_after_eyebrow(resp.text, "Captain Attention Lane")
    assert "Capture closeout lesson" in attention_lane
    assert "1 manual post needs closeout learning." in attention_lane
    assert "/aurora/manual-posting?lane=tracking_complete" in attention_lane
    attention_section = resp.text.split("<h2>Needs attention</h2>", 1)[1].split("</article>", 1)[0]
    assert "manual closeout ready" in attention_section
    assert "manual closeout closed" not in attention_section


def test_dashboard_status_badges_use_human_labels(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_060000",
        brief="approval needed",
        status="awaiting_approval",
    )

    resp = client.get("/", headers=_auth())

    assert resp.status_code == 200
    assert "Awaiting Approval" in resp.text
    assert ">awaiting_approval<" not in resp.text


def test_aurora_overview_shows_projects(tmp_path, client):
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    (tmp_path / "projects" / "nayzfreedom_fleet" / "pm_profile.yaml").write_text("page_name: test\n")
    _write_job(tmp_path, "20260512_060000", brief="needs aurora", status="failed")
    _write_job(tmp_path, "20260513_060000", brief="active aurora", status="running")
    resp = client.get("/aurora", headers=_auth())
    assert resp.status_code == 200
    assert "The Aurora" in resp.text
    assert "fleet-hero-command" in resp.text
    assert "Mission control" in resp.text
    assert "Open priority mission" in resp.text
    assert "needs aurora" in resp.text
    assert "active aurora" in resp.text
    assert "test" in resp.text
    assert "/aurora/islands/nayzfreedom_fleet" in resp.text
    assert "Operating workflow" in resp.text
    assert "Daily Slate" in resp.text
    assert "Approvals" in resp.text
    assert "Generation" in resp.text
    assert "station-icon" in resp.text
    assert "Captain Action Console" in resp.text
    assert "Command bridge actions" in resp.text
    assert "Captain Attention Lane" in resp.text
    assert "Learning Runbook" in resp.text


def test_learning_runbook_routes_to_daily_draft_review(tmp_path, client):
    daily_dir = tmp_path / "docs" / "learning" / "daily"
    daily_dir.mkdir(parents=True)
    (daily_dir / "2026-05-17-manual-posting-lessons.md").write_text(
        "---\n"
        "status: reviewed\n"
        "source: manual_posting_closeout\n"
        "source_job_ids:\n"
        "  - 20260516_manual\n"
        "---\n\n"
        "# Daily Learning Brief\n\n"
        "## Manual Posting Lessons\n\n"
        "  - Lesson: Draft lesson needs Captain acceptance.\n"
    )

    resp = client.get("/", headers=_auth())

    assert resp.status_code == 200
    assert "Learning Runbook" in resp.text
    assert "Needs Captain" in resp.text
    assert "Accept daily learning draft" in resp.text
    assert "1 daily learning draft needs review." in resp.text
    assert "/learning-runbook/accept-draft" in resp.text
    assert "Open learning desk" not in resp.text


def test_learning_runbook_routes_to_apply_accepted_learning(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    daily_dir = tmp_path / "docs" / "learning" / "daily"
    daily_dir.mkdir(parents=True)
    (daily_dir / "2026-05-17-manual-posting-lessons.md").write_text(
        "---\n"
        "status: accepted\n"
        "source: manual_posting_closeout\n"
        "source_job_ids:\n"
        "  - 20260516_manual\n"
        "---\n\n"
        "# Daily Learning Brief\n\n"
        "## Manual Posting Lessons\n\n"
        "  - Lesson: Accepted lesson is ready for planning.\n"
    )

    resp = client.get("/aurora", headers=_auth())

    assert resp.status_code == 200
    assert "Learning Runbook" in resp.text
    assert "Apply learning to next mission" in resp.text
    assert "Accepted learning is ready to apply to the next Daily Slate mission." in resp.text
    assert "/learning-runbook/apply-learning" in resp.text


def test_learning_runbook_routes_to_unconfirmed_applied_mission(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_learning",
        brief="applied learning mission",
        video_package={
            "ticket_id": "monday-short-video-1",
            "accepted_learning": {
                "status": "applied",
                "source_artifacts": ["docs/learning/daily/2026-05-17-manual-posting-lessons.md"],
                "source_job_ids": ["20260516_manual"],
                "lessons": [{"category": "CTA", "note": "Short CTA got more saves."}],
            },
        },
    )

    resp = client.get("/", headers=_auth())

    assert resp.status_code == 200
    assert "Confirm learning before generation" in resp.text
    assert "1 mission has applied learning waiting for planning confirmation." in resp.text
    assert "Confirm learning used in plan" in resp.text
    assert "/learning-runbook/confirm-learning" in resp.text
    assert "/jobs/20260512_learning" in resp.text


def test_learning_runbook_closeout_step_remains_navigation_only(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_closeout",
        brief="manual closeout ready",
        status="completed",
        manual_post_kit={
            "manual_post": {
                "instagram": {
                    "status": "posted",
                    "post_url": "https://www.instagram.com/p/closeout/",
                    "posted_at": "2026-05-17T14:00:00+00:00",
                }
            }
        },
        performance=[
            {"platform": "instagram", "reach": 100, "recorded_at": "2026-05-18T14:00:00+00:00"},
            {"platform": "instagram", "reach": 180, "recorded_at": "2026-05-20T14:00:00+00:00"},
        ],
    )

    resp = client.get("/", headers=_auth())

    assert resp.status_code == 200
    assert "Capture closeout lesson" in resp.text
    assert "Open manual closeout" in resp.text
    assert "/aurora/manual-posting?lane=tracking_complete" in resp.text
    assert "/learning-runbook/closeout" not in resp.text


def test_learning_runbook_routes_to_create_daily_draft_for_closed_lessons(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_closed_lesson",
        brief="closed lesson mission",
        status="completed",
        manual_post_kit={
            "manual_post": {
                "instagram": {
                    "status": "posted",
                    "post_url": "https://www.instagram.com/p/lesson/",
                    "posted_at": "2026-05-17T14:00:00+00:00",
                }
            },
            "closeout": {
                "status": "closed",
                "closed_at": "2026-05-20T15:00:00+00:00",
                "closed_by": "admin",
                "learning_note": "Short CTA got more saves.",
                "proof_summary": {
                    "post_url_present": True,
                    "snapshot_24h_present": True,
                    "snapshot_72h_present": True,
                    "learning_note_captured": True,
                },
            },
        },
    )

    resp = client.get("/", headers=_auth())

    assert resp.status_code == 200
    assert "Create daily learning draft" in resp.text
    assert "1 closed manual lesson needs a daily learning draft." in resp.text
    assert "/learning-runbook/create-draft" in resp.text


def test_captain_attention_lane_routes_post_runbook_steps_to_anchor(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_closed_lesson",
        brief="closed lesson mission",
        status="completed",
        manual_post_kit={
            "manual_post": {
                "instagram": {
                    "status": "posted",
                    "post_url": "https://www.instagram.com/p/lesson/",
                    "posted_at": "2026-05-17T14:00:00+00:00",
                }
            },
            "closeout": {
                "status": "closed",
                "closed_at": "2026-05-20T15:00:00+00:00",
                "closed_by": "admin",
                "learning_note": "Short CTA got more saves.",
            },
        },
    )

    resp = client.get("/", headers=_auth())

    assert resp.status_code == 200
    attention_lane = _section_after_eyebrow(resp.text, "Captain Attention Lane")
    assert "Create daily learning draft" in attention_lane
    assert "1 closed manual lesson needs a daily learning draft." in attention_lane
    assert 'href="#learning-runbook"' in attention_lane
    assert 'action="/learning-runbook/create-draft"' not in attention_lane
    runbook_section = _section_after_eyebrow(resp.text, "Learning Runbook")
    assert 'action="/learning-runbook/create-draft"' in runbook_section


def test_learning_runbook_skips_create_draft_when_closed_lesson_is_already_drafted(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_closed_lesson",
        brief="closed lesson mission",
        status="completed",
        manual_post_kit={
            "manual_post": {"instagram": {"status": "posted", "post_url": "https://www.instagram.com/p/lesson/"}},
            "closeout": {
                "status": "closed",
                "closed_at": "2026-05-20T15:00:00+00:00",
                "closed_by": "admin",
                "learning_note": "Short CTA got more saves.",
            },
        },
    )
    daily_dir = tmp_path / "docs" / "learning" / "daily"
    daily_dir.mkdir(parents=True)
    (daily_dir / "2026-05-17-manual-posting-lessons.md").write_text(
        "---\n"
        "status: accepted\n"
        "source: manual_posting_closeout\n"
        "source_job_ids:\n"
        "  - 20260512_closed_lesson\n"
        "---\n\n"
        "# Daily Learning Brief\n\n"
    )

    resp = client.get("/", headers=_auth())

    assert resp.status_code == 200
    assert "No closed manual posting lesson is waiting for draft creation." in resp.text
    assert "/learning-runbook/create-draft" not in resp.text


def test_learning_runbook_create_draft_action_writes_draft_without_publish_side_effects(tmp_path, client):
    today = date.today().isoformat()
    _write_job(
        tmp_path,
        "20260512_closed_lesson",
        brief="closed lesson mission",
        status="completed",
        manual_post_kit={
            "manual_post": {
                "instagram": {
                    "status": "posted",
                    "post_url": "https://www.instagram.com/p/lesson/",
                    "posted_at": "2026-05-17T14:00:00+00:00",
                }
            },
            "closeout": {
                "status": "closed",
                "closed_at": "2026-05-20T15:00:00+00:00",
                "closed_by": "admin",
                "learning_note": "Short CTA got more saves.",
                "proof_summary": {
                    "post_url_present": True,
                    "snapshot_24h_present": True,
                    "snapshot_72h_present": True,
                    "learning_note_captured": True,
                },
            },
        },
    )

    resp = client.post(
        "/learning-runbook/create-draft",
        data={"return_path": "/aurora"},
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/aurora?runbook_result=")
    assert "Created%20draft%3A%20docs%2Flearning%2Fdaily%2F" in resp.headers["location"]
    draft = (tmp_path / "docs" / "learning" / "daily" / f"{today}-manual-posting-lessons.md").read_text()
    assert "status: draft" in draft
    assert "created_by: admin" in draft
    assert "Source job: 20260512_closed_lesson" in draft
    assert "Short CTA got more saves." in draft
    saved = json.loads((tmp_path / "output" / "Slayhack" / "20260512_closed_lesson" / "job.json").read_text())
    assert saved.get("publish_result") is None
    assert saved.get("publish_execution") is None
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Created manual posting daily learning draft from runbook" in work_activity
    page = client.get(resp.headers["location"], headers=_auth())
    assert page.status_code == 200
    assert "Runbook action result" in page.text
    assert f"Created draft: docs/learning/daily/{today}-manual-posting-lessons.md" in page.text


def test_learning_runbook_accept_action_updates_draft_status(tmp_path, client):
    daily_dir = tmp_path / "docs" / "learning" / "daily"
    daily_dir.mkdir(parents=True)
    draft_path = daily_dir / "2026-05-17-manual-posting-lessons.md"
    draft_path.write_text(
        "---\n"
        "status: reviewed\n"
        "source: manual_posting_closeout\n"
        "source_job_ids:\n"
        "  - 20260516_manual\n"
        "---\n\n"
        "# Daily Learning Brief\n\n"
        "  - Lesson: Ready for acceptance.\n"
    )

    resp = client.post(
        "/learning-runbook/accept-draft",
        data={"draft_path": "docs/learning/daily/2026-05-17-manual-posting-lessons.md", "return_path": "/aurora"},
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/aurora?runbook_result=Accepted%20artifact%3A%20docs%2Flearning%2Fdaily%2F2026-05-17-manual-posting-lessons.md"
    updated = draft_path.read_text()
    assert "status: accepted" in updated
    assert "reviewed_by: admin" in updated
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Accepted daily learning draft from runbook" in work_activity
    page = client.get(resp.headers["location"], headers=_auth())
    assert page.status_code == 200
    assert "Runbook action result" in page.text
    assert "Accepted artifact: docs/learning/daily/2026-05-17-manual-posting-lessons.md" in page.text


def test_learning_runbook_accept_action_blocks_missing_source_ids(tmp_path, client):
    daily_dir = tmp_path / "docs" / "learning" / "daily"
    daily_dir.mkdir(parents=True)
    draft_path = daily_dir / "2026-05-17-manual-posting-lessons.md"
    draft_path.write_text(
        "---\n"
        "status: reviewed\n"
        "source: manual_posting_closeout\n"
        "source_job_ids: []\n"
        "---\n\n"
        "# Daily Learning Brief\n\n"
    )

    resp = client.post(
        "/learning-runbook/accept-draft",
        data={"draft_path": "docs/learning/daily/2026-05-17-manual-posting-lessons.md", "return_path": "/"},
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 400
    assert "Source job IDs are required before accepting a draft" in resp.text
    assert "status: reviewed" in draft_path.read_text()


def test_learning_runbook_apply_action_writes_mission_without_publish_side_effects(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    daily_dir = tmp_path / "docs" / "learning" / "daily"
    daily_dir.mkdir(parents=True)
    (daily_dir / "2026-05-17-manual-posting-lessons.md").write_text(
        "---\n"
        "status: accepted\n"
        "source: manual_posting_closeout\n"
        "source_job_ids:\n"
        "  - 20260516_manual\n"
        "---\n\n"
        "# Daily Learning Brief\n\n"
        "## Manual Posting Lessons\n\n"
        "  - Lesson: Short CTA got more saves.\n"
    )

    resp = client.post(
        "/learning-runbook/apply-learning",
        data={"project_slug": "slay_hack", "return_path": "/"},
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/?runbook_result=Applied%20mission%3A%20")
    created = json.loads(next((tmp_path / "output").rglob("*/job.json")).read_text())
    accepted_learning = created["video_package"]["accepted_learning"]
    assert accepted_learning["status"] == "applied"
    assert accepted_learning["source_job_ids"] == ["20260516_manual"]
    assert created["publish_result"] is None
    assert created["publish_execution"] is None
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Applied accepted learning from runbook" in work_activity
    page = client.get(resp.headers["location"], headers=_auth())
    assert page.status_code == 200
    assert "Runbook action result" in page.text
    assert f"Applied mission: {created['id']}" in page.text
    assert "slay_hack:" in page.text


def test_learning_runbook_confirm_action_writes_confirmation_only(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_learning",
        brief="applied learning mission",
        video_package={
            "ticket_id": "monday-short-video-1",
            "accepted_learning": {
                "status": "applied",
                "source_artifacts": ["docs/learning/daily/2026-05-17-manual-posting-lessons.md"],
                "source_job_ids": ["20260516_manual"],
                "lessons": [{"category": "CTA", "note": "Short CTA got more saves."}],
            },
        },
    )

    resp = client.post(
        "/learning-runbook/confirm-learning",
        data={"job_id": "20260512_learning", "return_path": "/aurora"},
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/aurora?runbook_result=Confirmed%20mission%3A%2020260512_learning"
    saved = json.loads((tmp_path / "output" / "Slayhack" / "20260512_learning" / "job.json").read_text())
    learning = saved["video_package"]["accepted_learning"]
    assert learning["status"] == "confirmed"
    assert learning["learning_confirmed_by"] == "admin"
    assert saved["generation_result"] is None
    assert saved["publish_result"] is None
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Confirmed accepted learning from runbook" in work_activity
    page = client.get(resp.headers["location"], headers=_auth())
    assert page.status_code == 200
    assert "Runbook action result" in page.text
    assert "Confirmed mission: 20260512_learning" in page.text


def test_learning_runbook_proof_shows_latest_runbook_action(tmp_path, client):
    from work_activity import write_work_activity

    write_work_activity(
        tmp_path,
        "implementation_step",
        "Accepted daily learning draft from runbook",
        actor="admin",
        result="docs/learning/daily/2026-05-17-manual-posting-lessons.md",
        next_action="Apply accepted learning to the next Daily Slate mission.",
        metadata={"source_job_ids": ["20260516_manual"]},
    )
    write_work_activity(
        tmp_path,
        "implementation_step",
        "Applied accepted learning from runbook to mission 20260512_plan",
        actor="slay",
        result="slay_hack:monday-short-video-1",
        next_action="Confirm applied learning on the mission before generation.",
        metadata={
            "job_id": "20260512_plan",
            "project": "slay_hack",
            "ticket_id": "monday-short-video-1",
            "source_job_ids": ["20260516_manual"],
        },
    )

    resp = client.get("/", headers=_auth())

    assert resp.status_code == 200
    assert "Learning Runbook Proof" in resp.text
    assert "Loop clear after Applied lesson" in resp.text
    assert "Last action" in resp.text
    assert "Applied lesson" in resp.text
    assert "slay" in resp.text
    assert "slay_hack:monday-short-video-1" in resp.text
    assert "20260512_plan" in resp.text
    assert "20260516_manual" in resp.text
    assert "Confirm applied learning on the mission before generation." in resp.text


def test_captain_attention_lane_surfaces_latest_runbook_proof(tmp_path, client):
    from work_activity import write_work_activity

    write_work_activity(
        tmp_path,
        "implementation_step",
        "Accepted daily learning draft from runbook",
        actor="admin",
        result="docs/learning/daily/2026-05-17-manual-posting-lessons.md",
        next_action="Apply accepted learning to the next Daily Slate mission.",
        metadata={"source_job_ids": ["20260516_manual"]},
    )

    resp = client.get("/", headers=_auth())

    assert resp.status_code == 200
    attention_lane = _section_after_eyebrow(resp.text, "Captain Attention Lane")
    assert "System did" in attention_lane
    assert "Accepted draft" in attention_lane
    assert "docs/learning/daily/2026-05-17-manual-posting-lessons.md" in attention_lane


def test_learning_runbook_proof_ignores_unrelated_worklog_events(tmp_path, client):
    from work_activity import write_work_activity

    write_work_activity(
        tmp_path,
        "implementation_step",
        "Accepted daily learning draft from runbook",
        actor="admin",
        result="docs/learning/daily/2026-05-17-manual-posting-lessons.md",
        metadata={"source_job_ids": ["20260516_manual"]},
    )
    write_work_activity(
        tmp_path,
        "test_result",
        "Remote visual QA passed",
        actor="codex",
        result="dashboard ok",
    )

    resp = client.get("/", headers=_auth())

    assert resp.status_code == 200
    assert "Learning Runbook Proof" in resp.text
    assert "Loop clear after Accepted draft" in resp.text
    assert "Last action" in resp.text
    assert "Accepted draft" in resp.text
    assert "Remote visual QA passed" not in resp.text


def test_learning_runbook_proof_shows_clear_loop_summary(tmp_path, client):
    from work_activity import write_work_activity

    write_work_activity(
        tmp_path,
        "implementation_step",
        "Confirmed accepted learning from runbook for 20260512_learning",
        actor="admin",
        result="learning_confirmed",
        next_action="Crew can use the confirmed learning in safe generation execution.",
        metadata={"job_id": "20260512_learning"},
    )

    resp = client.get("/aurora", headers=_auth())

    assert resp.status_code == 200
    assert "Learning Runbook Proof" in resp.text
    assert "Loop clear after Confirmed mission" in resp.text
    assert "Learning loop clear" in resp.text
    assert "Next missing step" in resp.text
    assert "20260512_learning" in resp.text


def test_learning_runbook_proof_handles_missing_worklog(tmp_path, client):
    resp = client.get("/", headers=_auth())

    assert resp.status_code == 200
    assert "Learning Runbook Proof" in resp.text
    assert "No runbook proof recorded yet." in resp.text
    assert "Current loop state" in resp.text
    assert "Next missing step" in resp.text


def test_learning_runbook_full_manual_learning_loop_reaches_clear_state(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    today = date.today().isoformat()
    _write_job(
        tmp_path,
        "20260512_closed_lesson",
        brief="closed lesson mission",
        status="completed",
        manual_post_kit={
            "manual_post": {
                "instagram": {
                    "status": "posted",
                    "post_url": "https://www.instagram.com/p/lesson/",
                    "posted_at": "2026-05-17T14:00:00+00:00",
                }
            },
            "closeout": {
                "status": "closed",
                "closed_at": "2026-05-20T15:00:00+00:00",
                "closed_by": "admin",
                "learning_note": "Short CTA got more saves.",
                "proof_summary": {
                    "post_url_present": True,
                    "snapshot_24h_present": True,
                    "snapshot_72h_present": True,
                    "learning_note_captured": True,
                },
            },
        },
    )

    start = client.get("/", headers=_auth())
    assert start.status_code == 200
    assert "Create daily learning draft" in start.text
    assert "1 closed manual lesson needs a daily learning draft." in start.text

    created = client.post(
        "/learning-runbook/create-draft",
        data={"return_path": "/"},
        headers=_auth(),
        follow_redirects=False,
    )
    assert created.status_code == 303
    created_page = client.get(created.headers["location"], headers=_auth())
    assert "Runbook action result" in created_page.text
    assert f"Created draft: docs/learning/daily/{today}-manual-posting-lessons.md" in created_page.text
    assert "Accept daily learning draft" in created_page.text
    assert "Create daily learning draft</strong>" in created_page.text
    assert "No closed manual posting lesson is waiting for draft creation." in created_page.text

    accepted = client.post(
        "/learning-runbook/accept-draft",
        data={"draft_path": f"docs/learning/daily/{today}-manual-posting-lessons.md", "return_path": "/"},
        headers=_auth(),
        follow_redirects=False,
    )
    assert accepted.status_code == 303
    accepted_page = client.get(accepted.headers["location"], headers=_auth())
    assert "Accepted artifact:" in accepted_page.text
    assert "Apply learning to next mission" in accepted_page.text
    assert "Accepted learning is ready to apply to the next Daily Slate mission." in accepted_page.text

    applied = client.post(
        "/learning-runbook/apply-learning",
        data={"project_slug": "slay_hack", "return_path": "/aurora"},
        headers=_auth(),
        follow_redirects=False,
    )
    assert applied.status_code == 303
    created_jobs = [
        json.loads(path.read_text())
        for path in (tmp_path / "output").rglob("job.json")
        if path.parent.name != "20260512_closed_lesson"
    ]
    mission = next(job for job in created_jobs if job.get("video_package", {}).get("accepted_learning"))
    applied_page = client.get(applied.headers["location"], headers=_auth())
    assert "Applied mission:" in applied_page.text
    assert mission["id"] in applied_page.text
    assert "Confirm learning before generation" in applied_page.text
    assert "1 mission has applied learning waiting for planning confirmation." in applied_page.text

    confirmed = client.post(
        "/learning-runbook/confirm-learning",
        data={"job_id": mission["id"], "return_path": "/"},
        headers=_auth(),
        follow_redirects=False,
    )
    assert confirmed.status_code == 303
    clear = client.get(confirmed.headers["location"], headers=_auth())
    assert "Confirmed mission:" in clear.text
    assert "Learning loop clear" in clear.text
    assert "Closeout, draft review, apply, and confirmation gates are clear." in clear.text
    assert "Loop clear after Confirmed mission" in clear.text
    assert "Next missing step" in clear.text
    assert "None" in clear.text


def test_captain_action_console_surfaces_safe_next_moves(tmp_path, client):
    from work_activity import write_work_activity

    _write_slay_hack_project(tmp_path)
    short_video_ticket_id = _slay_hack_ticket_id(tmp_path, "short-video-1")
    created = client.post(
        f"/aurora/workflow/video-packages/{short_video_ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    job_id = created.headers["location"].split("/")[-1]
    client.post(f"/jobs/{job_id}/ready-for-generation", headers=_auth(), follow_redirects=False)
    _write_job(
        tmp_path,
        "20260512_published",
        brief="published tracking candidate",
        status="completed",
        stage="publish_done",
        publish_result={"instagram": {"status": "published"}},
    )
    _write_job(
        tmp_path,
        "20260512_handoff",
        brief="handoff mission",
        status="completed",
        stage="publish_scheduled",
        publish_result={"instagram": {"status": "scheduled", "dry_run": True}},
    )
    handoff_path = tmp_path / "output" / "Slayhack" / "20260512_handoff" / "job.json"
    handoff_data = json.loads(handoff_path.read_text())
    handoff_data["publish_execution"] = {
        "status": "scheduled",
        "platforms": ["instagram"],
        "next_action": "Dashboard handoff only.",
    }
    handoff_path.write_text(json.dumps(handoff_data))
    write_work_activity(
        tmp_path,
        "implementation_step",
        "Created daily slate mission for console test",
        actor="codex",
        result="console action history",
    )
    write_work_activity(
        tmp_path,
        "implementation_step",
        "Generation dry-run completed for console test",
        actor="robin",
        result="shipyard ready",
    )
    write_work_activity(
        tmp_path,
        "blocker",
        "Captain approval needed for handoff mission",
        actor="nora",
        result="needs captain review",
    )
    write_work_activity(
        tmp_path,
        "test_result",
        "Tracking proof captured for published mission",
        actor="iris",
        result="learning ready",
    )
    deck = client.get("/", headers=_auth())
    aurora = client.get("/aurora", headers=_auth())
    filtered = client.get(
        "/?history_station=harbor-gate&history_actor=nora&history_mission=handoff&needs_captain=1",
        headers=_auth(),
    )

    assert deck.status_code == 200
    assert aurora.status_code == 200
    assert filtered.status_code == 200
    assert "Captain Action Console" in deck.text
    assert "Command history" in deck.text
    assert "Filtered ship log" in deck.text
    assert "All stations" in deck.text
    assert "All actors" in deck.text
    assert "Needs Captain" in deck.text
    assert "Created daily slate mission for console test" in deck.text
    assert "Generation dry-run completed for console test" in deck.text
    assert "Captain approval needed for handoff mission" in deck.text
    assert "Tracking proof captured for published mission" in deck.text
    assert "Route Map" in deck.text
    assert "Shipyard" in deck.text
    assert "Harbor Gate" in deck.text
    assert "Captain Log" in deck.text
    assert "Slay Hack next course" in deck.text
    assert "waiting" in deck.text
    assert "safe mission create" in deck.text
    assert "Create safe mission" in deck.text
    assert "/aurora/daily-slate?project=slay_hack" in deck.text
    assert f'action="/jobs/{job_id}/run-generation-dry-run"' in deck.text
    assert "Run dry-run only" in deck.text
    assert "Open locked live gate" in deck.text
    assert 'action="/jobs/20260512_handoff/live-publish-approval"' not in deck.text
    assert 'href="/jobs/20260512_handoff/live-publish-approval"' in deck.text
    assert "Check performance now" in deck.text
    assert 'action="/jobs/20260512_published/track-now"' in deck.text
    assert "live publish locked" in deck.text
    assert "Captain Action Console" in aurora.text
    assert "safe mission create" in aurora.text
    assert "Filtered ship log" in aurora.text
    assert "Captain approval needed for handoff mission" in filtered.text
    assert 'value="harbor-gate" selected' in filtered.text
    assert 'value="nora" selected' in filtered.text
    assert "value=\"handoff\"" in filtered.text
    assert "checked" in filtered.text
    assert "Generation dry-run completed for console test" not in filtered.text
    assert "Tracking proof captured for published mission" not in filtered.text


def test_aurora_workflow_page_renders_daily_slate(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    short_video_ticket_id = _slay_hack_ticket_id(tmp_path, "short-video-1")
    _write_job(tmp_path, "20260512_060000", brief="completed mission", status="completed", page="Slay Hack")
    _write_job(tmp_path, "20260512_070000", brief="failed mission", status="failed", page="Slay Hack")

    resp = client.get("/aurora/workflow", headers=_auth())

    assert resp.status_code == 200
    assert "Operating workflow" in resp.text
    assert "fleet-header-chart" in resp.text
    assert "station-workflow" in resp.text
    assert "New project discovery" in resp.text
    assert "Content calendar plan" in resp.text
    assert "Operating lanes" in resp.text
    assert "Discovery" in resp.text
    assert "Planning" in resp.text
    assert "Production" in resp.text
    assert "Learning" in resp.text
    assert "Vera Reel prepares scene timing and Veo3 package" in resp.text
    assert "Iris Gauge reads metrics" in resp.text
    assert "Sage Ledger links tickets, assets, and lessons" in resp.text
    assert "PM daily slate" in resp.text
    assert "Slay Hack" in resp.text
    assert "Minimum met" in resp.text
    assert "Production tickets" in resp.text
    assert "Long story episode" in resp.text
    assert "Vera Reel owns production" in resp.text
    assert "Slay decides" in resp.text
    assert "primary youtube" in resp.text
    assert "Mission packages" in resp.text
    assert "Create mission" in resp.text
    assert f"/aurora/workflow/video-packages/{short_video_ticket_id}/create-mission" in resp.text
    assert "Short-form Veo3 package" in resp.text
    assert "Veo3 storyboard package" in resp.text
    assert "Vera Reel owns 3 scenes over 23 seconds for tiktok." in resp.text
    assert "0-5s" in resp.text
    assert "Keep pacing clear, character-led, and ready for generation." in resp.text
    assert "Bella confirms the spoken hook and CTA before generation." in resp.text
    assert "9 storyboard scenes" in resp.text
    assert "2 acceptance checks" in resp.text
    assert "4 asset needs" in resp.text
    assert "Engagement review" in resp.text
    assert "Cross-team requests" in resp.text


def test_aurora_daily_slate_renders_project_slates_and_learning(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    _write_stadium_project(tmp_path)
    daily_dir = tmp_path / "docs" / "learning" / "daily"
    daily_dir.mkdir(parents=True)
    (daily_dir / "2026-05-16-character-art-learning-brief.md").write_text(
        "# Daily Learning Brief\n\nKeep PM decisions separate from central crew execution.\n"
    )
    (daily_dir / "2026-05-17-manual-posting-lessons.md").write_text(
        "---\n"
        "status: accepted\n"
        "source: manual_posting_closeout\n"
        "source_job_ids:\n"
        "  - 20260516_manual\n"
        "---\n\n"
        "# Daily Learning Brief\n\n"
        "## Manual Posting Lessons\n\n"
        "- Slayhack / instagram: tested post\n"
        "  - Source job: 20260516_manual\n"
        "  - Lesson: Short CTA got more saves.\n"
    )
    _write_job(
        tmp_path,
        "20260516_120000",
        brief="winning hook test",
        performance=[
            {
                "platform": "instagram",
                "reach": 2200,
                "likes": 140,
                "saves": 30,
                "shares": 12,
                "recorded_at": "2026-05-16T18:00:00Z",
            }
        ],
    )

    resp = client.get("/aurora/daily-slate", headers=_auth())

    assert resp.status_code == 200
    assert "PM Command Slate" in resp.text
    assert "Slay Hack" in resp.text
    assert "Stadium Sweethearts" in resp.text
    assert "PM Slay" in resp.text
    assert "PM Stadium" in resp.text
    assert "Project filters" in resp.text
    assert "All pages" in resp.text
    assert "Quick hack" in resp.text
    assert "Touchdown Reaction" in resp.text
    assert "Ticket drawer" in resp.text
    assert "Video package drawer" in resp.text
    assert "Next best ticket" in resp.text
    assert "PM action plan" in resp.text
    assert "Create short video mission" in resp.text
    assert "Create article mission" in resp.text
    assert "Video packages" in resp.text
    assert "Approval queue" in resp.text
    assert "Nora" in resp.text
    assert "Generation" in resp.text
    assert "Roxy + Emma" in resp.text
    assert "Create mission" in resp.text
    assert "/aurora/daily-slate/stadium_sweethearts/video-packages/" in resp.text
    assert "Latest learning" in resp.text
    assert "Accepted learning intake" in resp.text
    assert "Learning-to-planning gate" in resp.text
    assert "Short CTA got more saves." in resp.text
    assert "Apply learning to next mission" in resp.text
    assert "Performance signal" in resp.text
    assert "Latest learning from tracked posts" in resp.text
    assert "winning hook test" in resp.text
    assert "Scale this angle" in resp.text
    assert "Tracking proof" in resp.text
    assert "Snapshot readiness" in resp.text
    assert "fleet-header-map" in resp.text
    assert "learning ready" in resp.text
    assert "workflow-rail-step active" in resp.text
    assert "docs/learning/daily/2026-05-17-manual-posting-lessons.md" in resp.text
    assert "Use this view for" in resp.text
    assert "Stadium checks fan-cam plays" in resp.text

    stadium_only = client.get("/aurora/daily-slate?project=stadium_sweethearts", headers=_auth())
    assert stadium_only.status_code == 200
    assert "Stadium Sweethearts" in stadium_only.text
    assert "Touchdown Reaction" in stadium_only.text
    assert "PM Slay" not in stadium_only.text
    assert "Quick hack" not in stadium_only.text

    invalid_filter = client.get("/aurora/daily-slate?project=missing", headers=_auth())
    assert invalid_filter.status_code == 200
    assert "Slay Hack" in invalid_filter.text
    assert "Stadium Sweethearts" in invalid_filter.text


def test_daily_slate_applies_accepted_learning_to_next_mission(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    _write_job(
        tmp_path,
        "20260516_manual",
        brief="closed manual mission",
        manual_post_kit={
            "manual_post": {
                "instagram": {
                    "status": "posted",
                    "post_url": "https://www.instagram.com/p/source/",
                    "posted_at": "2026-05-17T12:00:00+00:00",
                }
            },
            "closeout": {
                "status": "closed",
                "closed_at": "2026-05-17T13:00:00+00:00",
                "closed_by": "admin",
                "learning_note": "Short CTA got more saves.",
                "proof_summary": {
                    "post_url_present": True,
                    "snapshot_24h_present": True,
                    "snapshot_72h_present": True,
                    "learning_note_captured": True,
                },
            },
        },
    )
    daily_dir = tmp_path / "docs" / "learning" / "daily"
    daily_dir.mkdir(parents=True)
    (daily_dir / "2026-05-17-manual-posting-lessons.md").write_text(
        "---\n"
        "status: accepted\n"
        "source: manual_posting_closeout\n"
        "source_job_ids:\n"
        "  - 20260516_manual\n"
        "---\n\n"
        "# Daily Learning Brief\n\n"
        "## Manual Posting Lessons\n\n"
        "- Slayhack / instagram: closed manual mission\n"
        "  - Source job: 20260516_manual\n"
        "  - Lesson: Short CTA got more saves.\n"
    )

    resp = client.post(
        "/aurora/daily-slate/apply-learning",
        data={"project_slug": "slay_hack"},
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/jobs/")
    mission_id = resp.headers["location"].removeprefix("/jobs/")
    created = json.loads(next((tmp_path / "output").rglob(f"{mission_id}/job.json")).read_text())
    accepted_learning = created["video_package"]["accepted_learning"]
    assert accepted_learning["status"] == "applied"
    assert accepted_learning["source_job_ids"] == ["20260516_manual"]
    assert accepted_learning["lessons"][0]["note"] == "Short CTA got more saves."
    assert accepted_learning["next_action"] == "Use these accepted manual posting lessons while shaping this mission. Live publish stays locked."
    assert created["publish_result"] is None
    assert created["publish_execution"] is None
    detail = client.get(f"/jobs/{mission_id}", headers=_auth())
    assert detail.status_code == 200
    assert "Accepted learning applied" in detail.text
    assert "Needs planning confirmation" in detail.text
    assert "Short CTA got more saves." in detail.text
    assert "Confirm learning used in plan" in detail.text
    assert "Mark ready for generation" not in detail.text
    source = json.loads((tmp_path / "output" / "Slayhack" / "20260516_manual" / "job.json").read_text())
    applied = source["manual_post_kit"]["closeout"]["learning_applied"]
    assert applied["status"] == "applied"
    assert applied["applied_to_job_id"] == mission_id
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Applied accepted learning to daily slate mission" in work_activity

    page = client.get("/aurora/manual-posting?lane=tracking_complete", headers=_auth())
    assert page.status_code == 200
    assert "Learning applied" in page.text


def test_job_detail_confirm_learning_unlocks_generation_ready(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    daily_dir = tmp_path / "docs" / "learning" / "daily"
    daily_dir.mkdir(parents=True)
    (daily_dir / "2026-05-17-manual-posting-lessons.md").write_text(
        "---\n"
        "status: accepted\n"
        "source: manual_posting_closeout\n"
        "source_job_ids:\n"
        "  - 20260516_manual\n"
        "---\n\n"
        "# Daily Learning Brief\n\n"
        "## Manual Posting Lessons\n\n"
        "- Slayhack / instagram: closed manual mission\n"
        "  - Source job: 20260516_manual\n"
        "  - Lesson: Short CTA got more saves.\n"
    )
    apply_resp = client.post(
        "/aurora/daily-slate/apply-learning",
        data={"project_slug": "slay_hack"},
        headers=_auth(),
        follow_redirects=False,
    )
    mission_id = apply_resp.headers["location"].removeprefix("/jobs/")

    blocked = client.post(f"/jobs/{mission_id}/ready-for-generation", headers=_auth(), follow_redirects=False)
    assert blocked.status_code == 400
    assert "Confirm accepted learning before marking generation ready" in blocked.text

    resp = client.post(f"/jobs/{mission_id}/confirm-learning", headers=_auth(), follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/jobs/{mission_id}"
    saved = json.loads(next((tmp_path / "output").rglob(f"{mission_id}/job.json")).read_text())
    learning = saved["video_package"]["accepted_learning"]
    assert learning["status"] == "confirmed"
    assert learning["learning_confirmed_by"] == "admin"
    assert learning["learning_confirmed_at"]
    assert saved["generation_result"] is None
    assert saved["publish_result"] is None
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Generation ready blocked by unconfirmed learning" in work_activity
    assert "Confirmed accepted learning" in work_activity

    detail = client.get(f"/jobs/{mission_id}", headers=_auth())
    assert detail.status_code == 200
    assert "Learning ready for execution" in detail.text
    assert "Confirmed by admin" in detail.text
    assert "Mark ready for generation" in detail.text

    ready = client.post(f"/jobs/{mission_id}/ready-for-generation", headers=_auth(), follow_redirects=False)
    assert ready.status_code == 303
    updated = json.loads(next((tmp_path / "output").rglob(f"{mission_id}/job.json")).read_text())
    assert updated["generation_request"]["status"] == "ready_for_generation"


def test_job_detail_confirm_learning_requires_attached_learning(tmp_path, client):
    _write_job(tmp_path, "20260512_plain", brief="plain mission")

    resp = client.post("/jobs/20260512_plain/confirm-learning", headers=_auth(), follow_redirects=False)

    assert resp.status_code == 400
    assert "No accepted learning is attached to this mission" in resp.text


def test_daily_slate_apply_learning_requires_accepted_artifact(tmp_path, client):
    _write_slay_hack_project(tmp_path)

    resp = client.post(
        "/aurora/daily-slate/apply-learning",
        data={"project_slug": "slay_hack"},
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 400
    assert "No accepted learning artifacts are ready to apply" in resp.text
    assert not list((tmp_path / "output").rglob("job.json"))


def test_daily_slate_creates_project_specific_video_mission(tmp_path, client):
    _write_stadium_project(tmp_path)
    ticket_id = _project_ticket_id(tmp_path, "stadium_sweethearts", "short-video-1")

    resp = client.post(
        f"/aurora/daily-slate/stadium_sweethearts/video-packages/{ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/jobs/")
    job_id = resp.headers["location"].split("/")[-1]
    job_path = next((tmp_path / "output" / "Stadium Sweethearts").glob("*/job.json"))
    data = json.loads(job_path.read_text())
    assert data["id"] == job_id
    assert data["project"] == "stadium_sweethearts"
    assert data["pm"]["page_name"] == "Stadium Sweethearts"
    assert data["video_package"]["ticket_id"] == ticket_id
    assert data["stage"] == "video_package_ready"
    assert data["generation_request"]["status"] == "nora_review"

    queue = client.get("/aurora/approval-queue", headers=_auth())
    slate = client.get("/aurora/daily-slate", headers=_auth())

    assert queue.status_code == 200
    assert "Ready but Not Published" in queue.text
    assert "Command lanes" in queue.text
    assert "Approval route" in queue.text
    assert "Stadium Sweethearts" in queue.text
    assert "Needs review" in queue.text
    assert "review gate" in queue.text
    assert "Next action" in queue.text
    assert "Mark ready" in queue.text
    assert slate.status_code == 200
    assert "Mission exists" in slate.text
    assert "Open mission" in slate.text
    assert job_id in slate.text


def test_daily_slate_mission_index_is_project_scoped(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    _write_stadium_project(tmp_path)
    ticket_id = _project_ticket_id(tmp_path, "slay_hack", "short-video-1")
    created = client.post(
        f"/aurora/daily-slate/slay_hack/tickets/{ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    assert created.status_code == 303
    job_id = created.headers["location"].split("/")[-1]

    stadium_only = client.get("/aurora/daily-slate?project=stadium_sweethearts", headers=_auth())

    assert stadium_only.status_code == 200
    assert "Touchdown Reaction" in stadium_only.text
    assert "Create short video mission" in stadium_only.text
    assert job_id not in stadium_only.text


def test_daily_slate_primary_action_uses_next_uncreated_ticket(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    short_ticket_id = _project_ticket_id(tmp_path, "slay_hack", "short-video-1")
    long_ticket_id = _project_ticket_id(tmp_path, "slay_hack", "long-video")
    article_ticket_id = _project_ticket_id(tmp_path, "slay_hack", "article-1")
    client.post(
        f"/aurora/daily-slate/slay_hack/tickets/{short_ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    client.post(
        f"/aurora/daily-slate/slay_hack/tickets/{long_ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )

    slate = client.get("/aurora/daily-slate?project=slay_hack", headers=_auth())

    assert slate.status_code == 200
    assert "Guide one - Bella owns - Slay decides" in slate.text
    assert "Create article mission" in slate.text
    assert f"/aurora/daily-slate/slay_hack/tickets/{article_ticket_id}/create-mission" in slate.text


def test_daily_slate_creates_non_video_ticket_mission(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    ticket_id = _project_ticket_id(tmp_path, "slay_hack", "article-1")

    resp = client.post(
        f"/aurora/daily-slate/slay_hack/tickets/{ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    job_id = resp.headers["location"].split("/")[-1]
    job_path = next((tmp_path / "output" / "Slay Hack").glob("*/job.json"))
    data = json.loads(job_path.read_text())
    assert data["id"] == job_id
    assert data["content_type"] == "article"
    assert data["production_ticket"]["ticket_id"] == ticket_id
    assert data["production_ticket"]["project"] == "slay_hack"
    assert data["stage"] == "slate_ticket_ready"
    assert "video_package" not in data or data["video_package"] is None


def test_approval_queue_advances_generation_actions(tmp_path, client):
    _write_stadium_project(tmp_path)
    ticket_id = _project_ticket_id(tmp_path, "stadium_sweethearts", "short-video-1")
    created = client.post(
        f"/aurora/daily-slate/stadium_sweethearts/video-packages/{ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    job_id = created.headers["location"].split("/")[-1]

    ready = client.post(f"/jobs/{job_id}/ready-for-generation", headers=_auth(), follow_redirects=False)
    queue = client.get("/aurora/approval-queue", headers=_auth())

    assert ready.status_code == 303
    assert queue.status_code == 200
    assert "fleet-header-harbor" in queue.text
    assert "Generation" in queue.text
    assert "Ready" in queue.text
    assert "safe dry-run" in queue.text
    assert "Next action" in queue.text
    assert "Run generation dry-run" in queue.text
    assert f"/jobs/{job_id}/run-generation-dry-run" in queue.text

    dry_run = client.post(f"/jobs/{job_id}/run-generation-dry-run", headers=_auth(), follow_redirects=False)
    waiting_queue = client.get("/aurora/approval-queue", headers=_auth())

    assert dry_run.status_code == 303
    assert waiting_queue.status_code == 200
    assert "Waiting real video" in waiting_queue.text
    assert "Attach the final generated video before publish packaging." in waiting_queue.text
    assert "manual upload" in waiting_queue.text
    assert "Open action" in waiting_queue.text
    assert "Record real video" in waiting_queue.text
    assert "output/Stadium Sweethearts/" in waiting_queue.text

    recorded_generation = client.post(
        f"/jobs/{job_id}/record-generation-result",
        headers=_auth(),
        data={
            "video_path": f"output/Stadium Sweethearts/{job_id}/final-video.mp4",
            "provider": "manual_upload",
            "provider_request_id": "approval-queue",
            "note": "Recorded from approval queue.",
        },
        follow_redirects=False,
    )
    packaging_queue = client.get("/aurora/approval-queue", headers=_auth())

    assert recorded_generation.status_code == 303
    assert packaging_queue.status_code == 200
    assert "Ready packaging" in packaging_queue.text
    assert "manual package" in packaging_queue.text
    assert "Record publish package" in packaging_queue.text
    assert "Fictional adult fan-cam replay" in packaging_queue.text

    recorded_package = client.post(
        f"/jobs/{job_id}/record-publish-package",
        headers=_auth(),
        data={
            "caption": "Fictional adult fan-cam replay: best of the week.",
            "hashtags": "#StadiumSweethearts, #AIFanCam",
            "faq": "Q: Is this real?\nA: No, fictional AI-generated adults only.",
            "publish_notes": "Do not schedule without Captain approval.",
        },
        follow_redirects=False,
    )
    package_queue = client.get("/aurora/approval-queue", headers=_auth())

    assert recorded_package.status_code == 303
    assert package_queue.status_code == 200
    assert "Package complete" in package_queue.text
    assert "Create publish job" in package_queue.text

    ready_publish = client.post(f"/jobs/{job_id}/create-publish-job", headers=_auth(), follow_redirects=False)
    ready_queue = client.get("/aurora/approval-queue", headers=_auth())

    assert ready_publish.status_code == 303
    assert ready_queue.status_code == 200
    assert "Ready to publish" in ready_queue.text
    assert "locked live publish" in ready_queue.text
    assert "Captain approval required before schedule handoff" in ready_queue.text
    assert "Captain review" in ready_queue.text
    assert f'action="/jobs/{job_id}/schedule-publish"' not in ready_queue.text


def test_captain_approval_gate_holds_edits_and_approves_schedule_handoff(tmp_path, client):
    _write_stadium_project(tmp_path)
    ticket_id = _project_ticket_id(tmp_path, "stadium_sweethearts", "short-video-1")
    created = client.post(
        f"/aurora/daily-slate/stadium_sweethearts/video-packages/{ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    job_id = created.headers["location"].split("/")[-1]
    client.post(f"/jobs/{job_id}/ready-for-generation", headers=_auth(), follow_redirects=False)
    client.post(f"/jobs/{job_id}/run-generation-dry-run", headers=_auth(), follow_redirects=False)
    client.post(
        f"/jobs/{job_id}/record-generation-result",
        headers=_auth(),
        data={
            "video_path": f"output/Stadium Sweethearts/{job_id}/final-video.mp4",
            "provider": "manual_upload",
            "provider_request_id": "approval-queue",
        },
        follow_redirects=False,
    )
    client.post(
        f"/jobs/{job_id}/record-publish-package",
        headers=_auth(),
        data={
            "caption": "Fictional adult fan-cam replay.",
            "hashtags": "#StadiumSweethearts, #AIFanCam",
            "faq": "Q: Is this real?\nA: No, fictional AI-generated adults only.",
            "publish_notes": "Do not schedule without Captain approval.",
        },
        follow_redirects=False,
    )
    client.post(f"/jobs/{job_id}/create-publish-job", headers=_auth(), follow_redirects=False)

    approval = client.get(f"/jobs/{job_id}/captain-approval", headers=_auth())
    detail = client.get(f"/jobs/{job_id}", headers=_auth())

    assert approval.status_code == 200
    assert "fleet-header-harbor" in approval.text
    assert "Captain approval" in approval.text
    assert "Fictional adult fan-cam replay." in approval.text
    assert "Dashboard schedule handoff only" in approval.text
    assert "Approve schedule handoff" in approval.text
    assert detail.status_code == 200
    assert "Current next action" in detail.text
    assert "Live publish locked" in detail.text
    assert "Workflow stage" in detail.text
    assert "Captain approval" in detail.text
    assert f'action="/jobs/{job_id}/schedule-publish"' not in detail.text

    hold = client.post(
        f"/jobs/{job_id}/captain-review",
        headers=_auth(),
        data={"decision": "hold", "note": "Wait for final thumbnail."},
        follow_redirects=False,
    )
    assert hold.status_code == 303
    job_path = next((tmp_path / "output" / "Stadium Sweethearts").glob("*/job.json"))
    data = json.loads(job_path.read_text())
    assert data["stage"] == "captain_hold"
    assert data["publish_execution"]["status"] == "captain_hold"
    assert data["publish_execution"]["captain_review"]["note"] == "Wait for final thumbnail."

    edits = client.post(
        f"/jobs/{job_id}/captain-review",
        headers=_auth(),
        data={"decision": "needs_edits", "note": "Tighten disclosure copy."},
        follow_redirects=False,
    )
    assert edits.status_code == 303
    data = json.loads(job_path.read_text())
    assert data["stage"] == "publish_needs_edits"
    assert data["publish_execution"]["status"] == "needs_edits"

    approved = client.post(
        f"/jobs/{job_id}/captain-review",
        headers=_auth(),
        data={"decision": "approve_schedule_handoff", "note": "Approved for dashboard handoff only."},
        follow_redirects=False,
    )
    assert approved.status_code == 303
    data = json.loads(job_path.read_text())
    assert data["stage"] == "publish_scheduled"
    assert data["publish_execution"]["status"] == "scheduled"
    assert data["publish_result"]["tiktok"]["dry_run"] is True
    assert data["publish_result"]["tiktok"]["reason"] == "Dashboard schedule handoff only; no external platform API was called."
    assert data["publish_execution"]["captain_review"]["decision"] == "approve_schedule_handoff"

    approved_page = client.get(f"/jobs/{job_id}/captain-approval", headers=_auth())

    assert approved_page.status_code == 200
    assert "fleet-header-harbor" in approved_page.text
    assert "Scheduled handoff" in approved_page.text
    assert "Live publish lock" in approved_page.text
    assert "Live publishing remains locked" in approved_page.text
    assert "Captain review history" in approved_page.text
    assert "Handoff audit" in approved_page.text
    assert "Dashboard schedule handoff only; no external platform API was called." in approved_page.text
    assert "Tiktok handoff" in approved_page.text
    assert "Open live publish approval gate" in approved_page.text

    live_gate = client.get(f"/jobs/{job_id}/live-publish-approval", headers=_auth())

    assert live_gate.status_code == 200
    assert "fleet-header-harbor" in live_gate.text
    assert "Live publish approval" in live_gate.text
    assert "Real posting remains blocked" in live_gate.text
    assert "No real platform publisher API is called from this page." in live_gate.text
    assert "Dashboard handoff is dry-run evidence, not a live post approval." in live_gate.text
    assert "Tiktok" in live_gate.text
    assert "Dry-run" in live_gate.text
    assert f'action="/jobs/{job_id}/live-publish-approval"' not in live_gate.text


def test_create_video_package_mission_saves_job_and_detail(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    short_video_ticket_id = _slay_hack_ticket_id(tmp_path, "short-video-1")

    resp = client.post(
        f"/aurora/workflow/video-packages/{short_video_ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/jobs/")
    job_id = resp.headers["location"].split("/")[-1]
    job_files = list((tmp_path / "output" / "Slay Hack").glob("*/job.json"))
    assert len(job_files) == 1
    data = json.loads(job_files[0].read_text())
    assert data["id"] == job_id
    assert data["stage"] == "video_package_ready"
    assert data["status"] == "running"
    assert data["content_type"] == "video"
    assert data["video_package"]["ticket_id"] == short_video_ticket_id
    assert data["generation_request"]["status"] == "nora_review"
    assert data["generation_request"]["tool_hint"] == "veo3"

    detail = client.get(resp.headers["location"], headers=_auth())

    assert detail.status_code == 200
    assert "Video package mission: Quick hack" in detail.text
    assert "Package the Motion" in detail.text
    assert "Vera Reel" in detail.text
    assert "Video Producer" in detail.text
    assert "Mark ready for generation" in detail.text
    assert "Scene timing, prompts, and assets are attached." in detail.text
    assert "Waiting for Nora to mark ready for generation." in detail.text


def test_mark_video_package_mission_ready_for_generation(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    short_video_ticket_id = _slay_hack_ticket_id(tmp_path, "short-video-1")
    created = client.post(
        f"/aurora/workflow/video-packages/{short_video_ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    job_id = created.headers["location"].split("/")[-1]

    resp = client.post(f"/jobs/{job_id}/ready-for-generation", headers=_auth(), follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/jobs/{job_id}"
    job_path = next((tmp_path / "output" / "Slay Hack").glob("*/job.json"))
    data = json.loads(job_path.read_text())
    assert data["stage"] == "nora_done"
    assert data["status"] == "awaiting_approval"
    assert data["qa_result"]["passed"] is True
    assert data["generation_request"]["status"] == "ready_for_generation"
    assert data["generation_request"]["approved_by"] == "Nora"

    detail = client.get(f"/jobs/{job_id}", headers=_auth())

    assert detail.status_code == 200
    assert "Generation status:" in detail.text
    assert "ready for generation" in detail.text
    assert "Nora approved the package for generation." in detail.text
    assert "Mark ready for generation" not in detail.text


def test_generation_queue_shows_ready_video_mission(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    short_video_ticket_id = _slay_hack_ticket_id(tmp_path, "short-video-1")
    created = client.post(
        f"/aurora/workflow/video-packages/{short_video_ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    job_id = created.headers["location"].split("/")[-1]
    client.post(f"/jobs/{job_id}/ready-for-generation", headers=_auth(), follow_redirects=False)

    resp = client.get("/aurora/generation", headers=_auth())

    assert resp.status_code == 200
    assert "Generation queue" in resp.text
    assert "fleet-header-shipyard" in resp.text
    assert "station-generation" in resp.text
    assert "Ready" in resp.text
    assert "Run generation dry-run" in resp.text
    assert f"/jobs/{job_id}/run-generation-dry-run" in resp.text
    assert "veo3" in resp.text


def test_generation_dry_run_writes_artifact_and_updates_job(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    short_video_ticket_id = _slay_hack_ticket_id(tmp_path, "short-video-1")
    created = client.post(
        f"/aurora/workflow/video-packages/{short_video_ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    job_id = created.headers["location"].split("/")[-1]
    client.post(f"/jobs/{job_id}/ready-for-generation", headers=_auth(), follow_redirects=False)

    resp = client.post(f"/jobs/{job_id}/run-generation-dry-run", headers=_auth(), follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/jobs/{job_id}"
    job_path = next((tmp_path / "output" / "Slay Hack").glob("*/job.json"))
    data = json.loads(job_path.read_text())
    assert data["stage"] == "generation_dry_run"
    assert data["generation_request"]["status"] == "dry_run_completed"
    assert data["generation_request"]["attempt"] == 1
    assert data["generation_result"]["status"] == "dry_run_completed"
    assert data["generation_result"]["mode"] == "dry_run"
    assert data["generation_result"]["output_path"].endswith("/video_generation_dry_run.json")
    artifact_path = job_path.parent / "video_generation_dry_run.json"
    artifact = json.loads(artifact_path.read_text())
    assert artifact["job_id"] == job_id
    assert artifact["status"] == "dry_run_completed"
    assert artifact["message"] == "Dry run only; no external generation API was called."

    detail = client.get(f"/jobs/{job_id}", headers=_auth())

    assert detail.status_code == 200
    assert "dry run completed" in detail.text
    assert "Dry run only; no external generation API was called." in detail.text
    assert "Rerun generation dry-run" in detail.text
    assert "Generation dry-run artifact is saved." in detail.text
    assert "Record real generation result" in detail.text
    assert "Waiting for the real generated video attachment." in detail.text


def test_generation_dry_run_can_rerun_and_increments_attempt(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    short_video_ticket_id = _slay_hack_ticket_id(tmp_path, "short-video-1")
    created = client.post(
        f"/aurora/workflow/video-packages/{short_video_ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    job_id = created.headers["location"].split("/")[-1]
    client.post(f"/jobs/{job_id}/ready-for-generation", headers=_auth(), follow_redirects=False)
    client.post(f"/jobs/{job_id}/run-generation-dry-run", headers=_auth(), follow_redirects=False)

    resp = client.post(f"/jobs/{job_id}/run-generation-dry-run", headers=_auth(), follow_redirects=False)

    assert resp.status_code == 303
    job_path = next((tmp_path / "output" / "Slay Hack").glob("*/job.json"))
    data = json.loads(job_path.read_text())
    assert data["generation_request"]["attempt"] == 2
    assert data["generation_result"]["attempt"] == 2
    artifact = json.loads((job_path.parent / "video_generation_dry_run.json").read_text())
    assert artifact["attempt"] == 2


def test_generation_dry_run_rejects_mission_without_video_package(tmp_path, client):
    _write_job(tmp_path, "20260512_060000", brief="not video", status="running", page="Slay Hack")

    resp = client.post(
        "/jobs/20260512_060000/run-generation-dry-run",
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 400
    assert "No video package is attached" in resp.text


def test_record_generation_result_attaches_real_video_and_opens_publish_packaging(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    short_video_ticket_id = _slay_hack_ticket_id(tmp_path, "short-video-1")
    created = client.post(
        f"/aurora/workflow/video-packages/{short_video_ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    job_id = created.headers["location"].split("/")[-1]
    client.post(f"/jobs/{job_id}/ready-for-generation", headers=_auth(), follow_redirects=False)
    client.post(f"/jobs/{job_id}/run-generation-dry-run", headers=_auth(), follow_redirects=False)

    resp = client.post(
        f"/jobs/{job_id}/record-generation-result",
        headers=_auth(),
        data={
            "video_path": "output/Slay Hack/final-video.mp4",
            "provider": "manual_upload",
            "provider_request_id": "req-123",
            "note": "Captain attached final render.",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/jobs/{job_id}"
    job_path = next((tmp_path / "output" / "Slay Hack").glob("*/job.json"))
    data = json.loads(job_path.read_text())
    assert data["stage"] == "generation_completed"
    assert data["status"] == "awaiting_approval"
    assert data["video_path"] == "output/Slay Hack/final-video.mp4"
    assert data["generation_request"]["status"] == "completed"
    assert data["generation_request"]["provider"] == "manual_upload"
    assert data["generation_request"]["provider_request_id"] == "req-123"
    assert data["generation_result"]["status"] == "completed"
    assert data["generation_result"]["mode"] == "real"
    assert data["generation_result"]["output_path"] == "output/Slay Hack/final-video.mp4"
    assert data["generation_result"]["publish_packaging"]["status"] == "ready"
    assert data["generation_result"]["note"] == "Captain attached final render."

    detail = client.get(f"/jobs/{job_id}", headers=_auth())

    assert detail.status_code == 200
    assert "Real generated video is attached to this mission." in detail.text
    assert "Publish packaging:" in detail.text
    assert "Roxy and Emma can package caption, hashtags, FAQ, and publish prep." in detail.text
    assert "Record publish package" in detail.text
    assert "Waiting for the real generated video attachment." not in detail.text


def test_record_publish_package_saves_roxy_and_emma_handoff(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    short_video_ticket_id = _slay_hack_ticket_id(tmp_path, "short-video-1")
    created = client.post(
        f"/aurora/workflow/video-packages/{short_video_ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    job_id = created.headers["location"].split("/")[-1]
    client.post(f"/jobs/{job_id}/ready-for-generation", headers=_auth(), follow_redirects=False)
    client.post(f"/jobs/{job_id}/run-generation-dry-run", headers=_auth(), follow_redirects=False)
    client.post(
        f"/jobs/{job_id}/record-generation-result",
        headers=_auth(),
        data={
            "video_path": "output/Slay Hack/final-video.mp4",
            "provider": "manual_upload",
            "provider_request_id": "req-123",
        },
        follow_redirects=False,
    )

    resp = client.post(
        f"/jobs/{job_id}/record-publish-package",
        headers=_auth(),
        data={
            "caption": "The fastest Slay Hack fix for a chaotic routine.",
            "hashtags": "#slayhack, beautyhack",
            "faq": "Q: Where should this publish?\nA: Start with TikTok, then adapt to Instagram.",
            "publish_notes": "Schedule after final thumbnail check.",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/jobs/{job_id}"
    job_path = next((tmp_path / "output" / "Slay Hack").glob("*/job.json"))
    data = json.loads(job_path.read_text())
    assert data["stage"] == "publish_packaged"
    assert data["status"] == "awaiting_approval"
    assert data["publish_package"]["status"] == "completed"
    assert data["publish_package"]["owners"] == ["Roxy", "Emma"]
    assert data["publish_package"]["caption"] == "The fastest Slay Hack fix for a chaotic routine."
    assert data["publish_package"]["hashtags"] == ["#slayhack", "#beautyhack"]
    assert data["growth_strategy"]["caption"] == "The fastest Slay Hack fix for a chaotic routine."
    assert data["growth_strategy"]["hashtags"] == ["#slayhack", "#beautyhack"]
    assert data["community_faq_path"].endswith("/faq.md")
    assert (job_path.parent / "faq.md").read_text().startswith("Q: Where should this publish?")

    detail = client.get(f"/jobs/{job_id}", headers=_auth())
    queue = client.get("/aurora/generation", headers=_auth())

    assert detail.status_code == 200
    assert "Publish package complete" in detail.text
    assert "Publish package is recorded for Roxy and Emma." in detail.text
    assert "The fastest Slay Hack fix for a chaotic routine." in detail.text
    assert "#beautyhack" in detail.text
    assert "FAQ is available." in detail.text
    assert queue.status_code == 200
    assert "Publish package complete" in queue.text


def test_create_publish_job_and_schedule_publish_from_package(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    short_video_ticket_id = _slay_hack_ticket_id(tmp_path, "short-video-1")
    created = client.post(
        f"/aurora/workflow/video-packages/{short_video_ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    job_id = created.headers["location"].split("/")[-1]
    client.post(f"/jobs/{job_id}/ready-for-generation", headers=_auth(), follow_redirects=False)
    client.post(f"/jobs/{job_id}/run-generation-dry-run", headers=_auth(), follow_redirects=False)
    client.post(
        f"/jobs/{job_id}/record-generation-result",
        headers=_auth(),
        data={
            "video_path": "output/Slay Hack/final-video.mp4",
            "provider": "manual_upload",
            "provider_request_id": "req-123",
        },
        follow_redirects=False,
    )
    client.post(
        f"/jobs/{job_id}/record-publish-package",
        headers=_auth(),
        data={
            "caption": "The fastest Slay Hack fix for a chaotic routine.",
            "hashtags": "#slayhack, beautyhack",
            "faq": "Q: Where should this publish?\nA: Start with TikTok, then adapt to Instagram.",
            "publish_notes": "Schedule after final thumbnail check.",
        },
        follow_redirects=False,
    )

    created_publish = client.post(f"/jobs/{job_id}/create-publish-job", headers=_auth(), follow_redirects=False)

    assert created_publish.status_code == 303
    job_path = next((tmp_path / "output" / "Slay Hack").glob("*/job.json"))
    data = json.loads(job_path.read_text())
    assert data["stage"] == "ready_to_publish"
    assert data["publish_execution"]["status"] == "ready_to_publish"
    assert data["publish_execution"]["caption"] == "The fastest Slay Hack fix for a chaotic routine."
    assert data["publish_execution"]["video_path"] == "output/Slay Hack/final-video.mp4"

    detail = client.get(f"/jobs/{job_id}", headers=_auth())
    ready_filter = client.get("/aurora/missions?filter=ready_to_publish", headers=_auth())

    assert detail.status_code == 200
    assert "Ready to publish" in detail.text
    assert "Captain approval" in detail.text
    assert f'action="/jobs/{job_id}/schedule-publish"' not in detail.text
    assert ready_filter.status_code == 200
    assert "Video package mission: Quick hack" in ready_filter.text

    scheduled = client.post(f"/jobs/{job_id}/schedule-publish", headers=_auth(), follow_redirects=False)

    assert scheduled.status_code == 303
    data = json.loads(job_path.read_text())
    assert data["stage"] == "publish_scheduled"
    assert data["publish_execution"]["status"] == "scheduled"
    assert data["publish_result"]["tiktok"]["status"] == "scheduled"
    assert data["publish_result"]["instagram"]["status"] == "scheduled"
    assert data["publish_result"]["tiktok"]["dry_run"] is True
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Created video package mission" in work_activity
    assert "Marked generation ready" in work_activity
    assert "Generation dry-run completed" in work_activity
    assert "Recorded real generation result" in work_activity
    assert "Recorded publish package" in work_activity
    assert "Created publish job" in work_activity
    assert "Scheduled dashboard handoff" in work_activity

    scheduled_detail = client.get(f"/jobs/{job_id}", headers=_auth())
    scheduled_filter = client.get("/aurora/missions?filter=scheduled", headers=_auth())
    queue = client.get("/aurora/generation", headers=_auth())
    queue_scheduled = client.get("/aurora/generation?filter=scheduled", headers=_auth())
    queue_ready = client.get("/aurora/generation?filter=ready_to_publish", headers=_auth())
    approval_queue = client.get("/aurora/approval-queue?lane=handoff", headers=_auth())

    assert scheduled_detail.status_code == 200
    assert "Scheduled handoff" in scheduled_detail.text
    assert "Create publish job" not in scheduled_detail.text
    assert scheduled_filter.status_code == 200
    assert "Video package mission: Quick hack" in scheduled_filter.text
    assert queue.status_code == 200
    assert "Scheduled handoff" in queue.text
    assert "Generation and publish state" in queue.text
    assert queue_scheduled.status_code == 200
    assert "Video package mission: Quick hack" in queue_scheduled.text
    assert queue_ready.status_code == 200
    assert "Video package mission: Quick hack" not in queue_ready.text
    assert approval_queue.status_code == 200
    assert "All lanes" in approval_queue.text
    assert "Handoff" in approval_queue.text
    assert "Scheduled dashboard handoff, still not live publishing" in approval_queue.text
    assert "QA gate before generation" not in approval_queue.text
    assert "Inspect the locked live publish gate before any separate platform action." in approval_queue.text
    assert "Open live publish gate" in approval_queue.text
    assert f'href="/jobs/{job_id}/live-publish-approval"' in approval_queue.text
    assert approval_queue.text.count(">Open mission</a>") == 1


def test_create_publish_job_requires_publish_package(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    short_video_ticket_id = _slay_hack_ticket_id(tmp_path, "short-video-1")
    created = client.post(
        f"/aurora/workflow/video-packages/{short_video_ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    job_id = created.headers["location"].split("/")[-1]

    resp = client.post(f"/jobs/{job_id}/create-publish-job", headers=_auth(), follow_redirects=False)

    assert resp.status_code == 400
    assert "Publish package must be complete" in resp.text


def test_record_publish_package_requires_real_generation(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    short_video_ticket_id = _slay_hack_ticket_id(tmp_path, "short-video-1")
    created = client.post(
        f"/aurora/workflow/video-packages/{short_video_ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    job_id = created.headers["location"].split("/")[-1]

    resp = client.post(
        f"/jobs/{job_id}/record-publish-package",
        headers=_auth(),
        data={
            "caption": "Not ready",
            "hashtags": "#slayhack",
            "faq": "Not ready",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 400
    assert "Real generated video must be attached" in resp.text


def test_record_generation_result_rejects_blank_video_path(tmp_path, client):
    _write_slay_hack_project(tmp_path)
    short_video_ticket_id = _slay_hack_ticket_id(tmp_path, "short-video-1")
    created = client.post(
        f"/aurora/workflow/video-packages/{short_video_ticket_id}/create-mission",
        headers=_auth(),
        follow_redirects=False,
    )
    job_id = created.headers["location"].split("/")[-1]
    client.post(f"/jobs/{job_id}/ready-for-generation", headers=_auth(), follow_redirects=False)

    resp = client.post(
        f"/jobs/{job_id}/record-generation-result",
        headers=_auth(),
        data={"video_path": " ", "provider": "manual_upload"},
        follow_redirects=False,
    )

    assert resp.status_code == 400
    assert "Video path is required" in resp.text


def test_aurora_crew_pages_render(client):
    crew = client.get("/aurora/crew", headers=_auth())
    detail = client.get("/aurora/crew/robin", headers=_auth())
    assert crew.status_code == 200
    assert "Crew" in crew.text
    assert "fleet-hero-crew" in crew.text
    assert "Captain Nayz" in crew.text
    assert "Robin" in crew.text
    assert "Slay" in crew.text
    assert "Stadium" in crew.text
    assert "Vera Reel" in crew.text
    assert "Iris Gauge" in crew.text
    assert "Sage Ledger" in crew.text
    assert "Video Producer" in crew.text
    assert "/static/crew/captain-nayz.png" in crew.text
    assert "/static/crew/vera-reel.png" in crew.text
    assert "/static/crew/slay.png" in crew.text
    assert "/static/crew/stadium.png" in crew.text
    assert "/static/crew/iris-gauge.png" in crew.text
    assert "/static/crew/sage-ledger.png" in crew.text
    assert "Crew Stations" in crew.text
    assert "Aurora route map" in crew.text
    assert "Fleet Command" in crew.text
    assert "Page PMs" in crew.text
    assert "Aurora Production Route" in crew.text
    assert "Learning Loop" in crew.text
    assert "Captain direction" in crew.text
    assert "Island owners" in crew.text
    assert "Mission command" in crew.text
    assert "Captain&#39;s Bridge" in crew.text
    assert "video-producer.svg" not in crew.text
    assert detail.status_code == 200
    assert "Chief Officer" in detail.text
    assert "Back to crew deck" in detail.text
    assert "Station handoff" in detail.text
    assert "command coat" in detail.text
    vera = client.get("/aurora/crew/video-producer", headers=_auth())
    assert vera.status_code == 200
    assert "camera harness" in vera.text
    assert "/static/crew/vera-reel.png" in vera.text
    slay = client.get("/aurora/crew/slay", headers=_auth())
    assert slay.status_code == 200
    assert "American superstar fashion PM" in slay.text
    captain = client.get("/aurora/crew/captain-nayz", headers=_auth())
    assert captain.status_code == 200
    assert "black-gold fleet authority portrait" in captain.text
    stadium = client.get("/aurora/crew/stadium", headers=_auth())
    assert stadium.status_code == 200
    assert "sports-lifestyle PM" in stadium.text
    iris = client.get("/aurora/crew/iris-gauge", headers=_auth())
    assert iris.status_code == 200
    assert "lime-green underlight" in iris.text
    sage = client.get("/aurora/crew/sage-ledger", headers=_auth())
    assert sage.status_code == 200
    assert "silver-lavender rope braid" in sage.text


def test_aurora_all_crew_character_sheets_render(client):
    from crew_registry import CREW

    for member in CREW:
        resp = client.get(f"/aurora/crew/{member.slug}", headers=_auth())
        assert resp.status_code == 200
        text = html.unescape(resp.text)
        assert member.name in resp.text
        assert member.workflow_stage in resp.text
        assert member.station in text


def test_aurora_crew_detail_unknown_member_404(client):
    resp = client.get("/aurora/crew/unknown", headers=_auth())
    assert resp.status_code == 404


def test_aurora_learning_page_renders_latest_brief_and_review_note(tmp_path, client):
    daily_dir = tmp_path / "docs" / "learning" / "daily"
    daily_dir.mkdir(parents=True)
    (daily_dir / "2026-05-16-character-art-learning-brief.md").write_text(
        "# Daily Learning Brief\n\nMia needs a targeted review.\n"
    )
    review_dir = tmp_path / "review" / "crew_final_style_v7"
    review_dir.mkdir(parents=True)
    (review_dir / "review_notes.md").write_text(
        "# Crew Final Style v7 Review Notes\n\nDo not overwrite static/crew yet.\n"
    )
    latest_review_dir = tmp_path / "review" / "crew_final_style_v8"
    latest_review_dir.mkdir(parents=True)
    (latest_review_dir / "review_notes.md").write_text(
        "# Crew Final Style v8 Approved Production Notes\n\nMia keeps the blue signal-scout direction.\n"
    )
    audit_dir = tmp_path / "review" / "crew_static_production_2026-05-17"
    audit_dir.mkdir(parents=True)
    (audit_dir / "asset_audit.md").write_text(
        "# Crew Static Production Asset Audit\n\nCurrent `static/crew/` production portrait provenance.\n"
    )
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
    )
    static_crew = tmp_path / "static" / "crew"
    static_crew.mkdir(parents=True)
    (static_crew / "mia.png").write_bytes(png_bytes)
    (static_crew / "nami.png").write_bytes(png_bytes)
    v7_review = tmp_path / "review" / "crew_final_style_v7"
    (v7_review / "mia.png").write_bytes(png_bytes)

    resp = client.get("/aurora/learning", headers=_auth())

    assert resp.status_code == 200
    assert "Aurora Learning Desk" in resp.text
    assert "fleet-hero-learning" in resp.text
    assert "Daily Learning Brief" in resp.text
    assert "Mia needs a targeted review." in resp.text
    assert "Crew Final Style v8 Approved Production Notes" in resp.text
    assert "Mia keeps the blue signal-scout direction." in resp.text
    assert "Crew art" in resp.text
    assert "Production canon" in resp.text
    assert "workflow-rail-step active" in resp.text
    assert "Current crew asset provenance" in resp.text
    assert "2 PNG production assets; 1 match the v7 review folder by hash." in resp.text
    assert "static/crew/mia.png" in resp.text
    assert "Matches v7 review" in resp.text
    assert "Approved concept portrait" in resp.text
    assert "Crew Static Production Asset Audit" in resp.text
    assert "Deploy status" in resp.text
    assert "Live" in resp.text
    assert "Manual Posting Lessons" in resp.text
    assert "Daily Learning Brief intake" in resp.text
    assert "No closed manual posting lessons are ready for the daily brief yet." in resp.text
    assert "Daily brief review gate" in resp.text
    assert "Draft learning artifacts" in resp.text
    assert "current manual crew portrait set is approved production canon and has a production asset audit" in resp.text


def test_aurora_learning_page_surfaces_manual_closeout_lessons(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_lesson",
        brief="manual lesson mission",
        status="completed",
        manual_post_kit={
            "manual_post": {
                "instagram": {
                    "status": "posted",
                    "post_url": "https://www.instagram.com/p/lesson/",
                    "posted_at": "2026-05-17T14:00:00+00:00",
                }
            },
            "closeout": {
                "status": "closed",
                "closed_at": "2026-05-20T15:00:00+00:00",
                "closed_by": "admin",
                "learning_note": "Short CTA got more saves.",
                "proof_summary": {
                    "drive_synced": True,
                    "post_url_present": True,
                    "snapshot_24h_present": True,
                    "snapshot_72h_present": True,
                    "learning_note_captured": True,
                },
            },
        },
        performance=[
            {"platform": "instagram", "reach": 100, "recorded_at": "2026-05-18T14:00:00+00:00"},
            {"platform": "instagram", "reach": 180, "recorded_at": "2026-05-20T14:00:00+00:00"},
        ],
    )

    resp = client.get("/aurora/learning", headers=_auth())

    assert resp.status_code == 200
    assert "Manual Posting Lessons" in resp.text
    assert "Daily Learning Brief intake" in resp.text
    assert "manual lesson mission" in resp.text
    assert "Short CTA got more saves." in resp.text
    assert "Create daily brief draft" in resp.text
    assert "Draft preview" in resp.text
    assert "Daily brief review gate" in resp.text
    assert "Post URL" in resp.text
    assert "24h proof" in resp.text
    assert "72h proof" in resp.text
    assert "## Manual Posting Lessons" in resp.text
    assert "Slayhack / instagram: manual lesson mission" in resp.text
    assert "Source job: 20260512_lesson" in resp.text
    assert "Proof: post URL=True, 24h=True, 72h=True" in resp.text


def test_aurora_learning_daily_brief_draft_writes_unique_file(tmp_path, client):
    today = date.today().isoformat()
    daily_dir = tmp_path / "docs" / "learning" / "daily"
    daily_dir.mkdir(parents=True)
    (daily_dir / f"{today}-manual-posting-lessons.md").write_text("existing draft")
    _write_job(
        tmp_path,
        "20260512_lesson",
        brief="manual lesson mission",
        status="completed",
        manual_post_kit={
            "manual_post": {
                "instagram": {
                    "status": "posted",
                    "post_url": "https://www.instagram.com/p/lesson/",
                    "posted_at": "2026-05-17T14:00:00+00:00",
                }
            },
            "closeout": {
                "status": "closed",
                "closed_at": "2026-05-20T15:00:00+00:00",
                "closed_by": "admin",
                "learning_note": "Short CTA got more saves.",
                "proof_summary": {
                    "drive_synced": True,
                    "post_url_present": True,
                    "snapshot_24h_present": True,
                    "snapshot_72h_present": True,
                    "learning_note_captured": True,
                },
            },
        },
        performance=[
            {"platform": "instagram", "reach": 100, "recorded_at": "2026-05-18T14:00:00+00:00"},
            {"platform": "instagram", "reach": 180, "recorded_at": "2026-05-20T14:00:00+00:00"},
        ],
    )

    resp = client.post("/aurora/learning/daily-brief-draft", headers=_auth(), follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/aurora/learning?created_draft=docs/learning/daily/{today}-manual-posting-lessons-2.md"
    assert (daily_dir / f"{today}-manual-posting-lessons.md").read_text() == "existing draft"
    draft = (daily_dir / f"{today}-manual-posting-lessons-2.md").read_text()
    assert "status: draft" in draft
    assert "source: manual_posting_closeout" in draft
    assert "source_job_ids:" in draft
    assert "# Daily Learning Brief" in draft
    assert "## Manual Posting Lessons" in draft
    assert "manual lesson mission" in draft
    assert "Source job: 20260512_lesson" in draft
    assert "Short CTA got more saves." in draft
    assert "Proof: post URL=True, 24h=True, 72h=True" in draft
    assert "Do not touch: live publish APIs or existing daily learning files." in draft
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Created manual posting daily learning draft" in work_activity

    page = client.get(resp.headers["location"], headers=_auth())
    assert page.status_code == 200
    assert f"docs/learning/daily/{today}-manual-posting-lessons-2.md" in page.text
    assert "Drafts waiting review" in page.text
    assert "Promote to accepted" in page.text


def test_aurora_learning_daily_brief_draft_requires_lessons(tmp_path, client):
    resp = client.post("/aurora/learning/daily-brief-draft", headers=_auth(), follow_redirects=False)

    assert resp.status_code == 400
    assert "No closed manual posting lessons are ready for a draft" in resp.text


def test_aurora_learning_daily_brief_status_updates_front_matter_only(tmp_path, client):
    daily_dir = tmp_path / "docs" / "learning" / "daily"
    daily_dir.mkdir(parents=True)
    draft_path = daily_dir / "2026-05-17-manual-posting-lessons.md"
    body = "# Daily Learning Brief\n\nBody must stay exactly here.\n"
    draft_path.write_text(
        "---\n"
        "status: draft\n"
        "source: manual_posting_closeout\n"
        "source_job_ids:\n"
        "  - 20260512_lesson\n"
        "created_by: admin\n"
        "created_at: '2026-05-17T14:00:00+00:00'\n"
        "---\n\n"
        + body
    )

    resp = client.post(
        "/aurora/learning/daily-brief-draft/status",
        data={"draft_path": "docs/learning/daily/2026-05-17-manual-posting-lessons.md", "status": "accepted"},
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    updated = draft_path.read_text()
    assert "status: accepted" in updated
    assert "reviewed_by: admin" in updated
    assert updated.endswith(body)
    page = client.get("/aurora/learning", headers=_auth())
    assert page.status_code == 200
    assert "Accepted learning artifacts" in page.text
    assert "20260512_lesson" in page.text
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Updated daily learning draft status: accepted" in work_activity


def test_aurora_learning_daily_brief_accept_blocks_missing_source_ids(tmp_path, client):
    daily_dir = tmp_path / "docs" / "learning" / "daily"
    daily_dir.mkdir(parents=True)
    draft_path = daily_dir / "2026-05-17-manual-posting-lessons.md"
    draft_path.write_text(
        "---\n"
        "status: draft\n"
        "source: manual_posting_closeout\n"
        "source_job_ids: []\n"
        "---\n\n"
        "# Daily Learning Brief\n\nNo source IDs.\n"
    )

    resp = client.post(
        "/aurora/learning/daily-brief-draft/status",
        data={"draft_path": "docs/learning/daily/2026-05-17-manual-posting-lessons.md", "status": "accepted"},
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 400
    assert "Source job IDs are required before accepting a draft" in resp.text
    assert "status: draft" in draft_path.read_text()


def test_aurora_learning_daily_brief_status_rejects_path_escape(tmp_path, client):
    resp = client.post(
        "/aurora/learning/daily-brief-draft/status",
        data={"draft_path": "docs/learning/../secrets.md", "status": "reviewed"},
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 400
    assert "Draft path must stay under docs/learning/daily" in resp.text


def test_island_detail_renders(tmp_path, client, monkeypatch):
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    (tmp_path / "projects" / "nayzfreedom_fleet" / "pm_profile.yaml").write_text(
        'name: "Slay"\npage_name: "Slayhack"\npersona: "bold persona"\n'
    )
    (tmp_path / "projects" / "nayzfreedom_fleet" / "brand.yaml").write_text(
        'mission: "mission"\nvisual:\n  colors: ["#fff"]\n  style: "minimal"\n'
        'platforms: ["instagram"]\ntone: "sassy"\ntarget_audience: "women"\n'
        'script_style: "lowercase"\nallowed_content_types: ["video", "image"]\n'
    )
    _write_job(tmp_path, "20260512_060000", brief="island mission", status="completed")
    _write_job(tmp_path, "20260512_070000", brief="attention mission", status="failed")
    _write_job(tmp_path, "20260512_080000", brief="active island mission", status="running")
    monkeypatch.chdir(tmp_path)
    resp = client.get("/aurora/islands/nayzfreedom_fleet", headers=_auth())
    assert resp.status_code == 200
    assert "Slayhack" in resp.text
    assert "Island command" in resp.text
    assert "Open island priority" in resp.text
    assert "PM" in resp.text
    assert "Slay" in resp.text
    assert "mission" in resp.text
    assert "Launch island mission" in resp.text
    assert "/aurora/new-mission?project=nayzfreedom_fleet" in resp.text
    assert "island mission" in resp.text
    assert "active island mission" in resp.text
    assert "Needs attention" in resp.text
    assert "bold persona" in resp.text
    assert "video" in resp.text
    assert "image" in resp.text


def test_new_mission_preselects_project(tmp_path, client):
    for slug in ("alpha", "nayzfreedom_fleet"):
        (tmp_path / "projects" / slug).mkdir(parents=True)
        (tmp_path / "projects" / slug / "pm_profile.yaml").write_text("page_name: test\n")
    resp = client.get("/aurora/new-mission?project=nayzfreedom_fleet", headers=_auth())
    assert resp.status_code == 200
    assert '<option value="nayzfreedom_fleet" selected>test</option>' in resp.text


def test_placeholder_ship_pages_render(client):
    freedom = client.get("/freedom", headers=_auth())
    lyra = client.get("/lyra", headers=_auth())
    assert freedom.status_code == 200
    assert "Freedom Five" in freedom.text
    assert "Nami" in freedom.text
    assert "/static/crew/nami.png" in freedom.text
    assert "privacy and memory boundaries" in freedom.text
    assert lyra.status_code == 200
    assert "Song voyage" in lyra.text
    assert "Genie" in lyra.text
    assert "/static/crew/genie.png" in lyra.text
    assert "blonde American musician" in lyra.text
    assert "electric guitar" in lyra.text
    assert "music workflow data" in lyra.text


def test_readiness_page_renders_private_preflight(tmp_path, client):
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    (tmp_path / "projects" / "nayzfreedom_fleet" / "pm_profile.yaml").write_text("page_name: test\n")
    (tmp_path / "deploy").mkdir()
    for name in (
        "nayzfreedom-dashboard.service",
        "nayzfreedom-bot.service",
        "nayzfreedom-scheduler.service",
        "nayzfreedom-scheduler.timer",
        "nayzfreedom-reporter.service",
        "nayzfreedom-reporter.timer",
        "setup.sh",
        "update.sh",
    ):
        (tmp_path / "deploy" / name).write_text("unit")
    (tmp_path / "static" / "ships").mkdir(parents=True)
    (tmp_path / "static" / "style.css").write_text("css")
    (tmp_path / "static" / "htmx.min.js").write_text("htmx")
    (tmp_path / "static" / "ships" / "aurora-hero.png").write_bytes(b"png")

    resp = client.get("/readiness", headers=_auth())

    assert resp.status_code == 200
    assert "Readiness" in resp.text
    assert "fleet-hero-readiness" in resp.text
    assert "Dashboard auth" in resp.text
    assert "Project config" in resp.text
    assert "Deploy files" in resp.text
    assert "Privacy boundary" in resp.text


def test_ops_page_renders_status_and_errors(tmp_path, client, monkeypatch):
    _write_job(
        tmp_path,
        "20260512_060000",
        brief="publish failed",
        status="failed",
        performance=[
            {
                "platform": "instagram",
                "reach": 1500,
                "likes": 120,
                "saves": 25,
                "shares": 10,
                "recorded_at": "2026-05-16T06:10:00Z",
            }
        ],
        publish_result={
            "facebook": {
                "status": "failed",
                "error": "bad token",
                "meta_error": {"code": 190, "error_subcode": 460, "type": "OAuthException", "message": "bad token"},
            }
        },
    )
    _write_job(
        tmp_path,
        "20260512_070000",
        brief="published tracking candidate",
        stage="publish_done",
        publish_result={"instagram": {"status": "published", "id": "media-1"}},
    )
    _write_job(
        tmp_path,
        "20260512_080000",
        brief="handoff waiting candidate",
        publish_result={"instagram": {"status": "pending_queue"}},
    )
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "ops_reports.jsonl").write_text(json.dumps({
        "timestamp": "2026-05-16T05:30:00Z",
        "title": "Slayhack weekly Ops report",
        "line_count": 3,
        "report": "Slayhack weekly Ops report\njobs total=1 failed=1 latest=20260512_060000",
    }) + "\n")
    (logs / "instagram_queue_history.jsonl").write_text(json.dumps({
        "timestamp": "2026-05-16T06:20:00Z",
        "processed": 2,
        "published": 1,
        "retrying": 1,
        "failed": 0,
        "dry_run": False,
    }) + "\n")
    (tmp_path / "output").mkdir(exist_ok=True)
    (tmp_path / "output" / "track_queue.json").write_text(json.dumps([
        {
            "job_id": "20260512_060000",
            "page_name": "Slayhack",
            "track_at": "2026-05-16T06:00:00Z",
            "attempt": 1,
        }
    ]))
    (logs / "track_scheduler_history.jsonl").write_text(json.dumps({
        "timestamp": "2026-05-16T06:30:00Z",
        "state": "Missing",
        "processed": 1,
        "succeeded": 0,
        "retrying": 1,
        "failed": 0,
        "remaining": 1,
        "dry_run": False,
        "jobs": [{"job_id": "20260512_060000", "state": "retrying", "attempt": 1, "detail": "returncode=1"}],
    }) + "\n")
    monkeypatch.setattr(
        _dm,
        "_ops_unit_status",
        lambda: [{"name": "nayzfreedom-dashboard.service", "state": "Ready", "detail": "active"}],
    )
    monkeypatch.setattr(_dm, "_latest_backup_status", lambda: {"state": "Ready", "detail": "backup-ok"})

    resp = client.get("/ops", headers=_auth())

    assert resp.status_code == 200
    assert "Ops" in resp.text
    assert "fleet-header-engine" in resp.text
    assert "Services and timers" in resp.text
    assert "nayzfreedom-dashboard.service" in resp.text
    assert "backup-ok" in resp.text
    assert "publish failed" in resp.text
    assert "bad token" in resp.text
    assert "Run smoke test" in resp.text
    assert "Run backup now" in resp.text
    assert "Run due Instagram queue now" in resp.text
    assert "Run tracking queue now" in resp.text
    assert "Run production summary now" in resp.text
    assert "Restart dashboard" in resp.text
    assert "Recent Ops actions" in resp.text
    assert "ops_actions.jsonl" in resp.text
    assert "Add Ops note" in resp.text
    assert "Recent notes" in resp.text
    assert "Historical Ops snapshots" in resp.text
    assert "Current Ops state is shown above" in resp.text
    assert "Slayhack weekly Ops report" in resp.text
    assert "jobs total=1 failed=1 latest=20260512_060000" in resp.text
    assert "Ops summary" in resp.text
    assert "Mission attention" in resp.text
    assert "Queue state" in resp.text
    assert "Instagram queue history" in resp.text
    assert "processed 2 - published 1 - retrying 1 - failed 0" in resp.text
    assert "Tracking queue" in resp.text
    assert "Scheduler history" in resp.text
    assert "Learning signals" in resp.text
    assert "scale" in resp.text
    assert "Tracking failures" in resp.text
    assert "returncode=1" in resp.text
    assert "Tracking proof readiness" in resp.text
    assert "ready now" in resp.text
    assert "Published on instagram with no metrics recorded yet." in resp.text
    assert "waiting publish" in resp.text
    assert "live publish is still separate" in resp.text
    assert "Queued 1" in resp.text
    assert "Retrying 1" in resp.text
    assert "processed 1" in resp.text
    assert "Failure triage" in resp.text
    assert "Retry lane" in resp.text
    assert "Safe IG 0" in resp.text
    assert "facebook - auth or permission" in resp.text
    assert "/ops/publish-failures/20260512_060000/facebook/retry" in resp.text
    assert "Meta code=190 error_subcode=460 type=OAuthException message=bad token" in resp.text
    assert "Media missing" in resp.text
    assert "Caption missing" in resp.text
    assert "Public URL blocked" in resp.text
    assert "Crew ownership" in resp.text
    assert "Hygiene checks" in resp.text
    assert "System resources" in resp.text
    assert "Service events" in resp.text
    assert "Restore smoke history" in resp.text


def test_ops_publish_failure_triage_shows_media_and_caption_readiness(tmp_path, client, monkeypatch):
    media_path = tmp_path / "output" / "Slayhack" / "20260512_070000" / "image.png"
    _write_job(
        tmp_path,
        "20260512_070000",
        brief="image publish failed",
        status="failed",
        publish_result={"instagram": {"status": "failed", "error": "400 Client Error: Bad Request"}},
    )
    media_path.write_bytes(b"image-bytes")
    job_path = tmp_path / "output" / "Slayhack" / "20260512_070000" / "job.json"
    data = json.loads(job_path.read_text())
    data["content_type"] = "infographic"
    data["image_path"] = "output/Slayhack/20260512_070000/image.png"
    data["growth_strategy"] = {
        "hashtags": ["#slayhack"],
        "caption": "Ready caption",
        "best_post_time_utc": "14:00",
        "best_post_time_thai": "21:00",
        "editorial_guidance": {},
    }
    job_path.write_text(json.dumps(data))
    monkeypatch.setattr(
        _dm,
        "_ops_unit_status",
        lambda: [{"name": "nayzfreedom-dashboard.service", "state": "Ready", "detail": "active"}],
    )
    monkeypatch.setattr(_dm, "_latest_backup_status", lambda: {"state": "Ready", "detail": "backup-ok"})

    resp = client.get("/ops", headers=_auth())

    assert resp.status_code == 200
    assert "Media ready" in resp.text
    assert "Caption ready" in resp.text
    assert "Public URL ready" in resp.text
    assert "Safe IG 1" in resp.text
    assert "Retry safe IG failures" in resp.text
    assert "https://fleet.nayzfreedom.cloud/media/public/20260512_070000/image.png" in resp.text
    assert "retry can use public image_url fallback" in resp.text


def test_ops_smoke_test_renders_results(tmp_path, client, monkeypatch):
    monkeypatch.setattr(
        _dm,
        "_ops_unit_status",
        lambda: [{"name": "nayzfreedom-dashboard.service", "state": "Ready", "detail": "active"}],
    )
    monkeypatch.setattr(_dm, "_latest_backup_status", lambda: {"state": "Ready", "detail": "backup-ok"})
    monkeypatch.setattr(
        _dm,
        "_ops_smoke_results",
        lambda root: [{"name": "Health URL", "state": "Ready", "detail": "HTTP 200"}],
    )

    resp = client.post("/ops/smoke-test", headers=_auth())

    assert resp.status_code == 200
    assert "Latest smoke test" in resp.text
    assert "Health URL" in resp.text
    assert "HTTP 200" in resp.text
    audit_path = tmp_path / "logs" / "ops_actions.jsonl"
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text().splitlines()[-1])
    assert audit["user"] == "admin"
    assert audit["action"] == "smoke_test"
    assert audit["result_state"] == "Ready"
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Dashboard Ops smoke test" in work_activity


def test_ops_action_runs_selected_command(tmp_path, client, monkeypatch):
    monkeypatch.setattr(
        _dm,
        "_ops_unit_status",
        lambda: [{"name": "nayzfreedom-dashboard.service", "state": "Ready", "detail": "active"}],
    )
    monkeypatch.setattr(_dm, "_latest_backup_status", lambda: {"state": "Ready", "detail": "backup-ok"})
    calls = []

    def fake_run_action(action):
        calls.append(action)
        return {"name": "Run due Instagram queue now", "state": "Ready", "detail": "started"}

    monkeypatch.setattr(_dm, "_run_ops_action", fake_run_action)

    resp = client.post("/ops/actions/instagram_queue", headers=_auth())

    assert resp.status_code == 200
    assert calls == ["instagram_queue"]
    assert "Run due Instagram queue now" in resp.text
    assert "started" in resp.text
    assert "Recent Ops actions" in resp.text
    audit_path = tmp_path / "logs" / "ops_actions.jsonl"
    audit = json.loads(audit_path.read_text().splitlines()[-1])
    assert audit["user"] == "admin"
    assert audit["action"] == "instagram_queue"
    assert audit["result_state"] == "Ready"
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Dashboard Ops action: instagram_queue" in work_activity


def test_run_ops_action_rejects_unknown_action():
    result = _dm._run_ops_action("unknown")

    assert result["state"] == "Failed"
    assert "Unknown Ops action" in result["detail"]


def test_run_ops_action_uses_sudo_systemctl(monkeypatch):
    calls = []

    def fake_run_command(args, timeout=8):
        calls.append((args, timeout))
        return {"state": "ok", "detail": ""}

    monkeypatch.setattr(_dm, "_run_command", fake_run_command)

    result = _dm._run_ops_action("backup")

    assert result["state"] == "Ready"
    assert calls == [(["sudo", "-n", "systemctl", "start", "nayzfreedom-backup.service"], 30)]


def test_ops_audit_sanitizes_and_reads_recent_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "secret-token")

    _dm._write_ops_audit(
        tmp_path,
        "admin",
        "backup",
        {"name": "Run backup now", "state": "Ready", "detail": "ok secret-token"},
    )

    path = tmp_path / "logs" / "ops_actions.jsonl"
    raw = path.read_text()
    assert "secret-token" not in raw
    assert "<redacted>" in raw
    rows = _dm._recent_ops_audit(tmp_path)
    assert rows[0]["action"] == "backup"
    assert rows[0]["state"] == "Ready"
    assert "<redacted>" in rows[0]["detail"]


def test_ops_log_status_counts_entries_and_archives(tmp_path):
    log_dir = tmp_path / "logs"
    archive_dir = log_dir / "archive"
    archive_dir.mkdir(parents=True)
    (log_dir / "ops_actions.jsonl").write_text("{}\n{}\n")
    (archive_dir / "ops_actions-20260516T000000Z.jsonl").write_text("{}\n")

    result = _dm._ops_log_status(tmp_path)

    assert result["state"] == "Ready"
    assert result["line_count"] == 2
    assert result["archive_count"] == 1
    assert "2 entries" in result["detail"]


def test_ops_page_shows_work_activity_log(tmp_path, client):
    from work_activity import write_work_activity

    write_work_activity(
        tmp_path,
        "design_decision",
        "Add publish execution lane",
        result="Ready for production smoke",
    )

    resp = client.get("/ops", headers=_auth())

    assert resp.status_code == 200
    assert "Work Activity" in resp.text
    assert "work_activity.jsonl" in resp.text
    assert "Add publish execution lane" in resp.text
    assert "design decision" in resp.text


def test_ops_page_shows_job_state_write_health(tmp_path, client, monkeypatch):
    monkeypatch.setattr(
        _dm,
        "_job_state_write_health",
        lambda root: {
            "state": "Failed",
            "detail": "1 job state files need ownership attention; scanned 1.",
            "attention_count": 1,
            "scanned": 1,
            "rows": [
                {
                    "state": "Failed",
                    "name": "output/Slayhack/20260512_060000/job.json",
                    "detail": "job.json not writable",
                }
            ],
        },
    )

    resp = client.get("/ops", headers=_auth())

    assert resp.status_code == 200
    assert "Job state ownership" in resp.text
    assert "output/Slayhack/20260512_060000/job.json" in resp.text
    assert "job.json not writable" in resp.text


def test_ops_incident_note_saves_and_displays(tmp_path, client, monkeypatch):
    monkeypatch.setattr(
        _dm,
        "_ops_unit_status",
        lambda: [{"name": "nayzfreedom-dashboard.service", "state": "Ready", "detail": "active"}],
    )
    monkeypatch.setattr(_dm, "_latest_backup_status", lambda: {"state": "Ready", "detail": "backup-ok"})

    resp = client.post(
        "/ops/incidents",
        data={"title": "Backup checked", "severity": "warning", "note": "Reviewed restore smoke output."},
        headers=_auth(),
    )

    assert resp.status_code == 200
    assert "Saved incident: Backup checked" in resp.text
    assert "Backup checked" in resp.text
    assert "Reviewed restore smoke output." in resp.text
    path = tmp_path / "logs" / "ops_incidents.jsonl"
    record = json.loads(path.read_text().splitlines()[-1])
    assert record["user"] == "admin"
    assert record["severity"] == "warning"
    assert record["title"] == "Backup checked"
    assert record["status"] == "open"
    assert "Open 1" in resp.text


def test_ops_incident_note_requires_title_and_note(tmp_path, client, monkeypatch):
    monkeypatch.setattr(
        _dm,
        "_ops_unit_status",
        lambda: [{"name": "nayzfreedom-dashboard.service", "state": "Ready", "detail": "active"}],
    )
    monkeypatch.setattr(_dm, "_latest_backup_status", lambda: {"state": "Ready", "detail": "backup-ok"})

    resp = client.post(
        "/ops/incidents",
        data={"title": "", "severity": "critical", "note": ""},
        headers=_auth(),
    )

    assert resp.status_code == 400
    assert "Incident title is required" in resp.text


def test_ops_incident_status_updates_existing_note(tmp_path, client, monkeypatch):
    monkeypatch.setattr(
        _dm,
        "_ops_unit_status",
        lambda: [{"name": "nayzfreedom-dashboard.service", "state": "Ready", "detail": "active"}],
    )
    monkeypatch.setattr(_dm, "_latest_backup_status", lambda: {"state": "Ready", "detail": "backup-ok"})
    record = _dm._write_ops_incident(
        tmp_path,
        "admin",
        "Queue issue",
        "critical",
        "Instagram queue checked.",
    )

    resp = client.post(
        f"/ops/incidents/{record['id']}/status",
        data={"status": "investigating"},
        headers=_auth(),
    )

    assert resp.status_code == 200
    assert "Marked incident Queue issue as investigating" in resp.text
    assert "Investigating 1" in resp.text
    row = json.loads((tmp_path / "logs" / "ops_incidents.jsonl").read_text().splitlines()[-1])
    assert row["status"] == "investigating"
    assert row["updated_by"] == "admin"


def test_ops_incident_status_rejects_unknown_id(tmp_path, client, monkeypatch):
    monkeypatch.setattr(
        _dm,
        "_ops_unit_status",
        lambda: [{"name": "nayzfreedom-dashboard.service", "state": "Ready", "detail": "active"}],
    )
    monkeypatch.setattr(_dm, "_latest_backup_status", lambda: {"state": "Ready", "detail": "backup-ok"})

    resp = client.post(
        "/ops/incidents/missing/status",
        data={"status": "resolved"},
        headers=_auth(),
    )

    assert resp.status_code == 400
    assert "Incident not found" in resp.text


def test_ops_incident_sanitizes_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", "secret-value")

    record = _dm._write_ops_incident(
        tmp_path,
        "admin",
        "Secret check",
        "critical",
        "contains secret-value",
    )

    assert record["severity"] == "critical"
    assert record["status"] == "open"
    assert "secret-value" not in (tmp_path / "logs" / "ops_incidents.jsonl").read_text()
    rows = _dm._recent_ops_incidents(tmp_path)
    assert rows[0]["title"] == "Secret check"
    assert "<redacted>" in rows[0]["note"]


def test_recent_ops_reports_reads_latest_and_sanitizes(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret-value")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "ops_reports.jsonl").write_text(
        json.dumps({
            "timestamp": "2026-05-16T05:00:00Z",
            "title": "Older",
            "line_count": 1,
            "report": "old",
        }) + "\n"
        + json.dumps({
            "timestamp": "2026-05-16T06:00:00Z",
            "title": "Slayhack weekly Ops report",
            "line_count": 2,
            "report": "contains secret-value\nrecent_failed_jobs=old1,old2",
        }) + "\n"
    )

    rows = _dm._recent_ops_reports(tmp_path, limit=1)

    assert rows[0]["title"] == "Slayhack weekly Ops report"
    assert rows[0]["line_count"] == "2"
    assert rows[0]["timestamp"] == "2026-05-16T06:00:00Z"
    assert "secret-value" not in rows[0]["report"]
    assert "recent_failed_jobs" not in rows[0]["report"]
    assert "<redacted>" in rows[0]["report"]


def test_ops_publish_summary_counts_queue_states(tmp_path, monkeypatch):
    monkeypatch.setattr(_dm, "_ops_now_utc", lambda: _dm.datetime(2026, 5, 16, 6, 30, tzinfo=_dm.timezone.utc))
    _write_job(
        tmp_path,
        "20260512_060000",
        brief="future caption",
        publish_result={
            "facebook": {"status": "scheduled"},
            "instagram": {"status": "pending_queue", "due_at": "2026-05-16T07:00:00Z"},
        },
    )
    _write_job(
        tmp_path,
        "20260512_063000",
        brief="due caption",
        publish_result={"instagram": {"status": "pending_queue", "due_at": "2026-05-16T06:30:00Z"}},
    )
    _write_job(
        tmp_path,
        "20260512_060100",
        brief="stale caption",
        publish_result={"instagram": {"status": "pending_queue", "due_at": "2026-05-16T06:00:00Z"}},
    )
    _write_job(
        tmp_path,
        "20260513_060000",
        publish_result={"instagram": {"status": "retrying", "next_retry_at": "2026-05-16T06:15:00Z"}},
    )
    _write_job(
        tmp_path,
        "20260514_060000",
        publish_result={"instagram": {"status": "failed", "error": "blocked"}},
    )
    _write_job(
        tmp_path,
        "20260515_060000",
        publish_result={"instagram": {"status": "published", "published_at": "2026-05-16T06:05:00Z"}},
    )

    jobs = _dm.list_all_jobs(tmp_path)
    result = _dm._ops_publish_summary(jobs)

    assert result["counts"]["facebook_scheduled"] == 1
    assert result["counts"]["instagram_pending"] == 3
    assert result["counts"]["instagram_due_now"] == 1
    assert result["counts"]["instagram_future"] == 1
    assert result["counts"]["instagram_stale"] == 1
    assert result["counts"]["instagram_retrying"] == 1
    assert result["counts"]["instagram_failed"] == 1
    assert result["counts"]["instagram_published"] == 1
    assert [item["status"] for item in result["queue"]] == ["failed", "stale", "due now", "retrying", "future", "published"]
    assert result["queue"][2]["retry_count"] == 0
    assert result["queue"][2]["caption"] == "due caption"


def test_backup_history_reports_recent_archives(tmp_path, monkeypatch):
    backup_root = tmp_path / "backups"
    backup_dir = backup_root / "20260516T000000Z"
    backup_dir.mkdir(parents=True)
    (backup_dir / "state.tgz").write_bytes(b"backup")
    (backup_dir / "state.tgz.sha256").write_text("checksum")
    monkeypatch.setenv("BACKUP_ROOT", str(backup_root))

    rows = _dm._backup_history()

    assert rows[0]["state"] == "Ready"
    assert rows[0]["name"] == "20260516T000000Z"
    assert "age" in rows[0]["detail"]


def test_restore_smoke_history_reads_latest(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "restore_smoke.jsonl").write_text(
        json.dumps({
            "timestamp": "2026-05-16T06:00:00Z",
            "state": "Ready",
            "archive": "/opt/nayzfreedom-backups/20260516/state.tgz",
        }) + "\n"
    )

    rows = _dm._restore_smoke_history(tmp_path)

    assert rows[0]["state"] == "Ready"
    assert rows[0]["name"] == "/opt/nayzfreedom-backups/20260516/state.tgz"
    assert rows[0]["detail"] == "2026-05-16T06:00:00Z"


def test_system_resources_reports_disk(tmp_path):
    rows = _dm._system_resources(tmp_path)

    assert rows[0]["name"] == "Disk"
    assert rows[0]["state"] in {"Ready", "Missing", "Failed"}
    assert "used" in rows[0]["detail"]


def test_latest_backup_status_handles_permission_denied(monkeypatch, tmp_path):
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    monkeypatch.setenv("BACKUP_ROOT", str(backup_root))

    def deny_iterdir(self):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "iterdir", deny_iterdir)

    result = _dm._latest_backup_status()

    assert result["state"] == "Failed"
    assert "Permission denied" in result["detail"]


def test_jobs_partial_returns_fragment(tmp_path, client):
    _write_job(tmp_path, "20260512_060000")
    resp = client.get("/jobs/partial", headers=_auth())
    assert resp.status_code == 200
    assert "<html" not in resp.text
    assert "<tbody" in resp.text
    assert "Slayhack" in resp.text
    assert "nayzfreedom_fleet" not in resp.text


def test_jobs_page_shows_publish_indicators(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_060000",
        publish_result={
            "facebook": {"status": "scheduled"},
            "instagram": {"status": "pending_queue"},
        },
    )
    resp = client.get("/aurora/missions", headers=_auth())
    assert resp.status_code == 200
    assert "fleet-header-voyage-board" in resp.text
    assert "Facebook scheduled" in resp.text
    assert "Instagram pending queue" in resp.text


def test_jobs_page_filters_publish_states(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_060000",
        brief="queued mission",
        publish_result={"instagram": {"status": "pending_queue"}},
    )
    _write_job(
        tmp_path,
        "20260513_060000",
        brief="scheduled mission",
        publish_result={"facebook": {"status": "scheduled"}},
    )
    _write_job(tmp_path, "20260514_060000", brief="plain mission")

    queued = client.get("/aurora/missions?filter=queued", headers=_auth())
    scheduled = client.get("/aurora/missions?filter=scheduled", headers=_auth())

    assert queued.status_code == 200
    assert "queued mission" in queued.text
    assert "scheduled mission" not in queued.text
    assert "plain mission" not in queued.text
    assert 'class="filter-tab active" href="/aurora/missions?filter=queued"' in queued.text
    assert scheduled.status_code == 200
    assert "scheduled mission" in scheduled.text
    assert "queued mission" not in scheduled.text


def test_dashboard_refuses_start_without_env():
    saved_user = os.environ.pop("DASHBOARD_USER", None)
    saved_pass = os.environ.pop("DASHBOARD_PASSWORD", None)
    sys.modules.pop("dashboard", None)
    try:
        with pytest.raises(RuntimeError):
            import dashboard  # noqa: F401
    finally:
        if saved_user is not None:
            os.environ["DASHBOARD_USER"] = saved_user
        if saved_pass is not None:
            os.environ["DASHBOARD_PASSWORD"] = saved_pass
        sys.modules.pop("dashboard", None)
        import dashboard  # noqa: F401  # re-import cleanly for subsequent tests


def test_dashboard_script_mode_help_imports_routes_without_circular_error():
    env = os.environ.copy()
    env["DASHBOARD_USER"] = "admin"
    env["DASHBOARD_PASSWORD"] = "8888"
    import subprocess
    result = subprocess.run(
        [sys.executable, "dashboard.py", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "--host" in result.stdout


def test_job_detail_404(client):
    with patch.object(_dm, "find_job", side_effect=FileNotFoundError("not found")):
        resp = client.get("/jobs/nonexistent_id", headers=_auth())
    assert resp.status_code == 404


def test_job_detail_shows_brief(tmp_path, client):
    _write_job(tmp_path, "20260512_060000", brief="luxury brands are amazing")
    from models.content_job import ContentJob, ContentType, GrowthStrategy, Script
    job = ContentJob.model_validate_json(
        (tmp_path / "output" / "Slayhack" / "20260512_060000" / "job.json").read_text()
    )
    job.content_type = ContentType.VIDEO
    job.bella_output = Script(hook="hook", body="body", cta="cta", duration_seconds=15)
    job.visual_prompt = "visual direction"
    job.growth_strategy = GrowthStrategy(
        hashtags=["#test"],
        caption="caption",
        best_post_time_utc="12:00",
        best_post_time_thai="19:00",
    )
    job.publish_result = {"dry_run": True}
    (tmp_path / "output" / "Slayhack" / "20260512_060000" / "faq.md").write_text("faq ready")
    with patch.object(_dm, "find_job", return_value=job):
        resp = client.get("/jobs/20260512_060000", headers=_auth())
    assert resp.status_code == 200
    assert "luxury brands are amazing" in resp.text
    assert "Slayhack" in resp.text
    assert "nayzfreedom_fleet" not in resp.text
    assert "Voyage log" in resp.text
    assert "fleet-hero-log" in resp.text
    assert "Captain's Log" in resp.text
    assert "Mission command" in resp.text
    assert "Ship position" in resp.text
    assert "Review the publish result and record performance when results arrive." in resp.text
    assert "Return to island" in resp.text
    assert "Mission cargo" in resp.text
    assert "/jobs/20260512_060000/download" in resp.text
    assert "Manual Post Kit" in resp.text
    assert "Download manual kit" in resp.text
    assert "SlayHack / 04_Video_PreProduction" in resp.text
    assert "Drive sync not configured" in resp.text
    assert "Cargo checklist" in resp.text
    assert "Output readiness" in resp.text
    assert "Bella output is available." in resp.text
    assert "Visual direction is available." in resp.text
    assert "Caption, hashtags, and timing are available." in resp.text
    assert "FAQ is available." in resp.text
    assert "Publish result is recorded." in resp.text
    assert "Command the Brief" in resp.text
    assert "/aurora/crew/robin" in resp.text


def test_job_detail_downloads_artifact_zip(tmp_path, client):
    import zipfile
    from io import BytesIO
    from models.content_job import ContentJob, ContentType, GrowthStrategy, Script

    _write_job(tmp_path, "20260512_060000", brief="downloadable mission")
    job_dir = tmp_path / "output" / "Slayhack" / "20260512_060000"
    job = ContentJob.model_validate_json((job_dir / "job.json").read_text())
    job.content_type = ContentType.VIDEO
    job.bella_output = Script(hook="hook", body="body", cta="cta", duration_seconds=24)
    job.visual_prompt = "clean hero object on deck"
    job.video_path = "output/Slayhack/20260512_060000/video.mp4"
    job.growth_strategy = GrowthStrategy(
        hashtags=["#slayhack", "#beautyhack"],
        caption="manual caption",
        best_post_time_utc="14:00",
        best_post_time_thai="21:00",
    )
    job.video_package = {
        "title": "Downloadable mission",
        "format_name": "Veo3 storyboard package",
        "total_duration_seconds": 16,
        "asset_checklist": ["hero object"],
        "scenes": [
            {
                "number": 1,
                "start_second": 0,
                "end_second": 8,
                "purpose": "hook",
                "visual_direction": "Open with the problem",
                "prompt": "Open with the problem in a clean beauty setup.",
                "tool_hint": "veo3",
            },
            {
                "number": 2,
                "start_second": 8,
                "end_second": 16,
                "purpose": "payoff",
                "visual_direction": "Show the fix",
                "prompt": "Show the fix with smooth hand motion.",
                "tool_hint": "veo3",
            },
        ],
    }
    (job_dir / "job.json").write_text(job.model_dump_json(indent=2))
    (job_dir / "bella_output.md").write_text("script ready")
    (job_dir / "video.mp4").write_bytes(b"MP4")

    resp = client.get("/jobs/20260512_060000/download", headers=_auth())

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "20260512_060000_downloadable-mission_manual-kit.zip" in resp.headers["content-disposition"]
    with zipfile.ZipFile(BytesIO(resp.content)) as archive:
        names = sorted(archive.namelist())
        assert "SlayHack/04_Video_PreProduction/20260512_060000_downloadable-mission/README_MANUAL_POST.md" in names
        assert "SlayHack/04_Video_PreProduction/20260512_060000_downloadable-mission/caption.txt" in names
        assert "SlayHack/04_Video_PreProduction/20260512_060000_downloadable-mission/hashtags.txt" in names
        assert "SlayHack/04_Video_PreProduction/20260512_060000_downloadable-mission/script.md" in names
        assert "SlayHack/04_Video_PreProduction/20260512_060000_downloadable-mission/storyboard.md" in names
        assert "SlayHack/04_Video_PreProduction/20260512_060000_downloadable-mission/video_prompts/google_video_8s.md" in names
        assert "SlayHack/04_Video_PreProduction/20260512_060000_downloadable-mission/video_prompts/kling_detailed.md" in names
        assert "SlayHack/04_Video_PreProduction/20260512_060000_downloadable-mission/video_prompts/seedance2_detailed.md" in names
        assert "SlayHack/04_Video_PreProduction/20260512_060000_downloadable-mission/assets/video.mp4" in names
        assert "SlayHack/04_Video_PreProduction/20260512_060000_downloadable-mission/raw_output/bella_output.md" in names
        assert archive.read("SlayHack/04_Video_PreProduction/20260512_060000_downloadable-mission/caption.txt") == b"manual caption\n"
        assert b"Google Video / Veo" in archive.read(
            "SlayHack/04_Video_PreProduction/20260512_060000_downloadable-mission/video_prompts/google_video_8s.md"
        )


def test_job_detail_syncs_manual_kit_to_drive(tmp_path, client, monkeypatch, mocker):
    _write_job(tmp_path, "20260512_060000", brief="drive kit")
    monkeypatch.setenv("GOOGLE_DRIVE_MANUAL_KITS_FOLDER_ID", "root-folder")
    folder_mock = mocker.patch(
        "google_drive.ensure_drive_folder_path",
        return_value={"folder_id": "type-folder", "folders": []},
    )
    upload_mock = mocker.patch(
        "google_drive.upload_file_to_drive",
        return_value={
            "id": "file-123",
            "name": "kit.zip",
            "webViewLink": "https://drive.google.com/file/d/file-123/view",
            "webContentLink": "https://drive.google.com/uc?id=file-123",
        },
    )

    resp = client.post("/jobs/20260512_060000/sync-drive", headers=_auth(), follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/jobs/20260512_060000"
    folder_mock.assert_called_once()
    assert folder_mock.call_args.args[0] == "root-folder"
    assert folder_mock.call_args.args[1] == ["SlayHack", "05_Ready_To_Post"]
    upload_mock.assert_called_once()
    assert upload_mock.call_args.kwargs["replace_existing"] is True
    saved = json.loads((tmp_path / "output" / "Slayhack" / "20260512_060000" / "job.json").read_text())
    assert saved["manual_post_kit"]["drive_sync"]["status"] == "synced"
    assert saved["manual_post_kit"]["drive_sync"]["file_id"] == "file-123"
    assert saved["manual_post_kit"]["drive_sync"]["web_view_link"] == "https://drive.google.com/file/d/file-123/view"


def test_job_detail_sync_blocks_before_upload_when_job_state_unwritable(tmp_path, client, monkeypatch, mocker):
    _write_job(tmp_path, "20260512_060000", brief="drive kit")
    monkeypatch.setenv("GOOGLE_DRIVE_MANUAL_KITS_FOLDER_ID", "root-folder")
    monkeypatch.setattr("routes.jobs._manual_kit_state_write_issue", lambda root, job: "job.json not writable")
    upload_mock = mocker.patch("google_drive.upload_file_to_drive")

    resp = client.post("/jobs/20260512_060000/sync-drive", headers=_auth(), follow_redirects=False)

    assert resp.status_code == 409
    assert "blocked before upload" in resp.text
    upload_mock.assert_not_called()


def test_job_detail_sync_records_failed_drive_state(tmp_path, client, monkeypatch, mocker):
    _write_job(tmp_path, "20260512_060000", brief="drive kit")
    monkeypatch.setenv("GOOGLE_DRIVE_MANUAL_KITS_FOLDER_ID", "root-folder")
    mocker.patch(
        "google_drive.ensure_drive_folder_path",
        return_value={"folder_id": "type-folder", "folders": []},
    )
    mocker.patch("google_drive.upload_file_to_drive", side_effect=RuntimeError("Drive quota nope"))

    resp = client.post("/jobs/20260512_060000/sync-drive", headers=_auth(), follow_redirects=False)

    assert resp.status_code == 303
    saved = json.loads((tmp_path / "output" / "Slayhack" / "20260512_060000" / "job.json").read_text())
    assert saved["manual_post_kit"]["drive_sync"]["status"] == "failed"
    assert "Drive quota nope" in saved["manual_post_kit"]["drive_sync"]["detail"]


def test_job_detail_records_manual_post_and_queues_tracking(tmp_path, client, monkeypatch):
    _write_job(tmp_path, "20260512_060000", brief="manual post kit")
    monkeypatch.setenv("GOOGLE_DRIVE_MANUAL_KITS_FOLDER_ID", "root-folder")

    resp = client.post(
        "/jobs/20260512_060000/manual-post",
        data={
            "platform": "instagram",
            "post_url": "https://www.instagram.com/p/manual123/",
            "posted_at": "2026-05-17T14:00:00+00:00",
            "note": "Posted by Captain",
        },
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    saved = json.loads((tmp_path / "output" / "Slayhack" / "20260512_060000" / "job.json").read_text())
    manual_post = saved["manual_post_kit"]["manual_post"]["instagram"]
    assert manual_post["post_url"] == "https://www.instagram.com/p/manual123/"
    assert manual_post["status"] == "posted"
    assert saved["publish_result"]["instagram"]["status"] == "published"
    assert saved["publish_result"]["instagram"]["manual"] is True
    assert saved["stage"] == "publish_done"
    assert saved["status"] == "completed"
    queue = json.loads((tmp_path / "output" / "track_queue.json").read_text())
    assert [item["track_at"] for item in queue] == ["2026-05-18T14:00:00Z", "2026-05-20T14:00:00Z"]
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Recorded manual post for 20260512_060000" in work_activity


def test_manual_queue_record_post_redirects_with_tracking_feedback(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_synced",
        brief="synced kit mission",
        manual_post_kit={
            "drive_sync": {
                "status": "synced",
                "synced_at": "2026-05-17T13:00:00+00:00",
                "web_view_link": "https://drive.google.com/file/d/synced/view",
            }
        },
    )

    resp = client.post(
        "/jobs/20260512_synced/manual-post",
        data={
            "platform": "instagram",
            "post_url": "https://www.instagram.com/p/manual123/",
            "posted_at": "2026-05-17T14:00:00+00:00",
            "note": "Recorded from Manual Posting Queue.",
            "return_path": "/aurora/manual-posting?lane=waiting_tracking",
        },
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/aurora/manual-posting?lane=waiting_tracking&manual_result=")
    assert "Recorded+manual+post+for+20260512_synced" in resp.headers["location"]
    queue = json.loads((tmp_path / "output" / "track_queue.json").read_text())
    assert [item["track_at"] for item in queue] == ["2026-05-18T14:00:00Z", "2026-05-20T14:00:00Z"]
    page = client.get(resp.headers["location"], headers=_auth())
    assert page.status_code == 200
    assert "Manual post recorded" in page.text
    assert "queued 24h and 72h tracking" in page.text
    assert "Manual posted, waiting tracking" in page.text


def test_job_detail_rejects_manual_post_without_url(tmp_path, client):
    _write_job(tmp_path, "20260512_060000", brief="manual post kit")

    resp = client.post(
        "/jobs/20260512_060000/manual-post",
        data={"platform": "instagram", "post_url": "not-a-url"},
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 400
    assert not (tmp_path / "output" / "track_queue.json").exists()


def test_job_detail_blocks_manual_post_when_job_state_unwritable(tmp_path, client, monkeypatch):
    _write_job(tmp_path, "20260512_060000", brief="manual post kit")
    monkeypatch.setattr("routes.jobs._manual_kit_state_write_issue", lambda root, job: "job.json not writable")

    resp = client.post(
        "/jobs/20260512_060000/manual-post",
        data={
            "platform": "instagram",
            "post_url": "https://www.instagram.com/p/manual123/",
            "posted_at": "2026-05-17T14:00:00+00:00",
        },
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 409
    assert "blocked before tracking queue update" in resp.text
    assert not (tmp_path / "output" / "track_queue.json").exists()


def test_job_detail_shows_record_manual_post_form(tmp_path, client):
    _write_job(tmp_path, "20260512_060000", brief="manual post kit")

    resp = client.get("/jobs/20260512_060000", headers=_auth())

    assert resp.status_code == 200
    assert "Record manual post" in resp.text
    assert "/jobs/20260512_060000/manual-post" in resp.text


def test_manual_posting_queue_groups_synced_posted_tracking_and_attention(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_synced",
        brief="synced kit mission",
        manual_post_kit={
            "drive_sync": {
                "status": "synced",
                "synced_at": "2026-05-17T13:00:00+00:00",
                "web_view_link": "https://drive.google.com/file/d/synced/view",
            }
        },
    )
    _write_job(
        tmp_path,
        "20260512_waiting",
        brief="waiting tracking mission",
        manual_post_kit={
            "drive_sync": {"status": "synced"},
            "manual_post": {
                "instagram": {
                    "status": "posted",
                    "post_url": "https://www.instagram.com/p/waiting/",
                    "posted_at": "2026-05-17T14:00:00+00:00",
                }
            },
        },
        publish_result={
            "instagram": {
                "status": "published",
                "manual": True,
                "post_url": "https://www.instagram.com/p/waiting/",
            }
        },
        published_at="2026-05-17T14:00:00+00:00",
    )
    _write_job(
        tmp_path,
        "20260512_complete",
        brief="complete tracking mission",
        manual_post_kit={
            "manual_post": {
                "facebook": {
                    "status": "posted",
                    "post_url": "https://facebook.com/manual-post",
                    "posted_at": "2026-05-17T12:00:00+00:00",
                }
            }
        },
        publish_result={
            "facebook": {
                "status": "published",
                "manual": True,
                "post_url": "https://facebook.com/manual-post",
            }
        },
        performance=[
            {"platform": "facebook", "reach": 100, "recorded_at": "2026-05-18T12:00:00+00:00"},
            {"platform": "facebook", "reach": 180, "recorded_at": "2026-05-20T12:00:00+00:00"},
        ],
        published_at="2026-05-17T12:00:00+00:00",
    )
    _write_job(
        tmp_path,
        "20260512_attention",
        brief="attention mission",
        manual_post_kit={
            "manual_post": {
                "instagram": {
                    "status": "posted",
                    "post_url": "https://www.instagram.com/p/attention/",
                    "posted_at": "2026-05-17T11:00:00+00:00",
                }
            }
        },
        publish_result={
            "instagram": {
                "status": "published",
                "manual": True,
                "post_url": "https://www.instagram.com/p/attention/",
            }
        },
        published_at="2026-05-17T11:00:00+00:00",
    )
    (tmp_path / "output" / "track_queue.json").write_text(json.dumps([
        {
            "job_id": "20260512_waiting",
            "page_name": "Slayhack",
            "track_at": "2026-05-18T14:00:00Z",
            "attempt": 0,
        }
    ]))

    resp = client.get("/aurora/manual-posting?lane=all", headers=_auth())

    assert resp.status_code == 200
    assert "Manual Post Command Lane" in resp.text
    assert "Manual Posting Queue Overview" in resp.text
    assert "Queue direction" in resp.text
    assert "Manual posting status" in resp.text
    assert "Live publish locked" in resp.text
    assert "All" in resp.text
    assert "Captain posts from the Drive kit, then records the platform URL." in resp.text
    assert "Wait for queued tracking snapshot at 2026-05-18T14:00:00Z." in resp.text
    assert "Review the performance proof and capture the learning note." in resp.text
    assert "Manual post is recorded, but no snapshot checks are queued." in resp.text
    assert "Learning completion" in resp.text
    assert "Waiting manual post" in resp.text
    assert "Waiting tracking proof" in resp.text
    assert "Ready for closeout" in resp.text
    assert "Learning not ready" in resp.text
    assert "Kit synced, not posted" in resp.text
    assert "Manual posted, waiting tracking" in resp.text
    assert "Tracking complete" in resp.text
    assert "Tracking queue missing" in resp.text
    assert "Record manual post" in resp.text
    assert "Requeue tracking from posted time" in resp.text
    assert "Capture learning note" in resp.text
    assert "synced kit mission" in resp.text
    assert "waiting tracking mission" in resp.text
    assert "complete tracking mission" in resp.text
    assert "attention mission" in resp.text
    assert "Open Drive kit" in resp.text
    assert "Open manual post" in resp.text

    kit_lane = client.get(
        "/aurora/manual-posting?lane=kit_synced&focus=20260512_synced",
        headers=_auth(),
    )
    assert kit_lane.status_code == 200
    assert "Manual Kit Posting Checklist" in kit_lane.text
    assert "Post from kit, then record URL" in kit_lane.text
    assert "Open Drive kit" in kit_lane.text
    assert "Post manually" in kit_lane.text
    assert "Record post URL" in kit_lane.text
    assert "Tracking queued" in kit_lane.text
    assert 'id="manual-job-20260512_synced"' in kit_lane.text
    assert "focus-row" in kit_lane.text
    assert 'name="return_path" type="hidden" value="/aurora/manual-posting?lane=waiting_tracking"' in kit_lane.text

    waiting_lane = client.get("/aurora/manual-posting?lane=waiting_tracking", headers=_auth())
    assert waiting_lane.status_code == 200
    assert "Tracking Proof Assist" in waiting_lane.text
    assert "Waiting on 24h / 72h proof" in waiting_lane.text
    assert "Queued 1" in waiting_lane.text
    assert "24h snapshot" in waiting_lane.text
    assert "2026-05-18T14:00:00Z" in waiting_lane.text
    assert "Run tracking queue now" in waiting_lane.text

    complete_lane = client.get("/aurora/manual-posting?lane=tracking_complete", headers=_auth())
    assert complete_lane.status_code == 200
    assert "Closeout CTA" in complete_lane.text
    assert "Ready for closeout" in complete_lane.text
    assert "Capture the learning note after reviewing the 24h and 72h proof." in complete_lane.text

    default_resp = client.get("/aurora/manual-posting", headers=_auth())
    assert default_resp.status_code == 200
    assert "attention mission" in default_resp.text
    default_board = _section_after_eyebrow(default_resp.text, "Safe handoff board")
    assert "attention mission" in default_board
    assert "synced kit mission" not in default_board


def test_manual_posting_queue_ignores_unsynced_unposted_jobs(tmp_path, client):
    _write_job(tmp_path, "20260512_plain", brief="plain mission")

    resp = client.get("/aurora/manual-posting", headers=_auth())

    assert resp.status_code == 200
    assert "Manual Posting Queue Overview" in resp.text
    assert "No missions in this lane." in resp.text
    assert "No manual kits have been synced or posted yet." in resp.text
    assert "plain mission" not in resp.text


def test_manual_posting_queue_requeues_tracking_from_posted_time(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_attention",
        brief="attention mission",
        manual_post_kit={
            "manual_post": {
                "instagram": {
                    "status": "posted",
                    "post_url": "https://www.instagram.com/p/attention/",
                    "posted_at": "2026-05-17T11:00:00+00:00",
                }
            }
        },
        publish_result={
            "instagram": {
                "status": "published",
                "manual": True,
                "post_url": "https://www.instagram.com/p/attention/",
            }
        },
    )

    resp = client.post(
        "/aurora/manual-posting/20260512_attention/requeue-tracking",
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/aurora/manual-posting?lane=waiting_tracking&tracking_result=")
    assert "Requeued%2024h%20and%2072h%20tracking%20for%2020260512_attention" in resp.headers["location"]
    saved = json.loads((tmp_path / "output" / "Slayhack" / "20260512_attention" / "job.json").read_text())
    assert saved["published_at"] == "2026-05-17T11:00:00Z"
    queue = json.loads((tmp_path / "output" / "track_queue.json").read_text())
    assert [item["track_at"] for item in queue] == ["2026-05-18T11:00:00Z", "2026-05-20T11:00:00Z"]
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Requeued manual tracking for 20260512_attention" in work_activity


def test_manual_posting_queue_runs_tracking_scheduler_with_feedback(tmp_path, client, monkeypatch):
    monkeypatch.setattr(
        "routes.aurora._run_ops_action",
        lambda action: {"name": "Run tracking queue now", "state": "Ready", "detail": f"{action} started"},
    )

    resp = client.post(
        "/aurora/manual-posting/run-tracking",
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"] == (
        "/aurora/manual-posting?lane=waiting_tracking&tracking_result="
        "Tracking%20scheduler%20Ready%3A%20track_scheduler%20started"
    )
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Manual posting tracking scheduler requested" in work_activity
    page = client.get(resp.headers["location"], headers=_auth())
    assert page.status_code == 200
    assert "Tracking action result" in page.text
    assert "Tracking scheduler Ready: track_scheduler started" in page.text


def test_manual_posting_queue_closeout_records_learning_note(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_complete",
        brief="complete tracking mission",
        manual_post_kit={
            "drive_sync": {"status": "synced"},
            "manual_post": {
                "facebook": {
                    "status": "posted",
                    "post_url": "https://facebook.com/manual-post",
                    "posted_at": "2026-05-17T12:00:00+00:00",
                }
            },
        },
        publish_result={
            "facebook": {
                "status": "published",
                "manual": True,
                "post_url": "https://facebook.com/manual-post",
            }
        },
        performance=[
            {"platform": "facebook", "reach": 100, "recorded_at": "2026-05-18T12:00:00+00:00"},
            {"platform": "facebook", "reach": 180, "recorded_at": "2026-05-20T12:00:00+00:00"},
        ],
        published_at="2026-05-17T12:00:00+00:00",
    )

    resp = client.post(
        "/aurora/manual-posting/20260512_complete/closeout",
        data={"learning_note": "Hook worked; keep the shorter CTA."},
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/aurora/manual-posting?lane=tracking_complete"
    saved = json.loads((tmp_path / "output" / "Slayhack" / "20260512_complete" / "job.json").read_text())
    closeout = saved["manual_post_kit"]["closeout"]
    assert closeout["status"] == "closed"
    assert closeout["learning_note"] == "Hook worked; keep the shorter CTA."
    assert closeout["proof_summary"]["post_url_present"] is True
    assert closeout["proof_summary"]["snapshot_24h_present"] is True
    assert closeout["proof_summary"]["snapshot_72h_present"] is True

    page = client.get("/aurora/manual-posting?lane=tracking_complete", headers=_auth())
    assert page.status_code == 200
    assert "Needs Captain learning review" in page.text
    assert "Closeout captured" in page.text
    assert "Create the daily learning draft from this closed manual lesson." in page.text
    assert "Hook worked; keep the shorter CTA." in page.text
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Closed manual post for 20260512_complete" in work_activity


def test_manual_posting_queue_blocks_closeout_without_tracking_proof(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_waiting",
        brief="waiting tracking mission",
        manual_post_kit={
            "manual_post": {
                "instagram": {
                    "status": "posted",
                    "post_url": "https://www.instagram.com/p/waiting/",
                    "posted_at": "2026-05-17T14:00:00+00:00",
                }
            }
        },
        publish_result={
            "instagram": {
                "status": "published",
                "manual": True,
                "post_url": "https://www.instagram.com/p/waiting/",
            }
        },
        performance=[
            {"platform": "instagram", "reach": 100, "recorded_at": "2026-05-18T14:00:00+00:00"},
        ],
    )

    resp = client.post(
        "/aurora/manual-posting/20260512_waiting/closeout",
        data={"learning_note": "Needs second snapshot."},
        headers=_auth(),
        follow_redirects=False,
    )

    assert resp.status_code == 400
    assert "24h and 72h tracking proof are required" in resp.text


def test_manual_kit_adds_video_prompts_for_legacy_video_job(tmp_path, client):
    import zipfile
    from io import BytesIO
    from models.content_job import ContentJob, ContentType, Script

    _write_job(tmp_path, "20260512_060001", brief="legacy video mission")
    job_dir = tmp_path / "output" / "Slayhack" / "20260512_060001"
    job = ContentJob.model_validate_json((job_dir / "job.json").read_text())
    job.content_type = ContentType.VIDEO
    job.bella_output = Script(hook="legacy hook", body="legacy body", cta="legacy cta", duration_seconds=24)
    job.visual_prompt = "legacy visual prompt"
    (job_dir / "job.json").write_text(job.model_dump_json(indent=2))

    resp = client.get("/jobs/20260512_060001/download", headers=_auth())

    assert resp.status_code == 200
    with zipfile.ZipFile(BytesIO(resp.content)) as archive:
        base = "SlayHack/04_Video_PreProduction/20260512_060001_legacy-video-mission"
        assert f"{base}/storyboard.md" in archive.namelist()
        assert f"{base}/video_prompts/google_video_8s.md" in archive.namelist()
        google_prompt = archive.read(f"{base}/video_prompts/google_video_8s.md").decode()
        assert "legacy hook" in google_prompt
        assert "legacy visual prompt" in google_prompt


def test_job_detail_shows_tracking_queue_status(tmp_path, client):
    _write_job(tmp_path, "20260512_060000", brief="tracking mission")
    (tmp_path / "output" / "track_queue.json").write_text(json.dumps([
        {
            "job_id": "20260512_060000",
            "page_name": "Slayhack",
            "track_at": "2026-05-18T14:00:00Z",
            "attempt": 1,
        }
    ]))
    from models.content_job import ContentJob
    job = ContentJob.model_validate_json(
        (tmp_path / "output" / "Slayhack" / "20260512_060000" / "job.json").read_text()
    )
    with patch.object(_dm, "find_job", return_value=job):
        resp = client.get("/jobs/20260512_060000", headers=_auth())

    assert resp.status_code == 200
    assert "Performance snapshots:" in resp.text
    assert "Queued" in resp.text
    assert "1 queued snapshot checks" in resp.text
    assert "attempt 1" in resp.text


def test_job_detail_shows_manual_tracking_action_for_published_job(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_060000",
        stage="publish_done",
        publish_result={"instagram": {"status": "published", "id": "media-1"}},
    )
    from models.content_job import ContentJob
    job = ContentJob.model_validate_json(
        (tmp_path / "output" / "Slayhack" / "20260512_060000" / "job.json").read_text()
    )
    with patch.object(_dm, "find_job", return_value=job):
        resp = client.get("/jobs/20260512_060000", headers=_auth())

    assert resp.status_code == 200
    assert "Check performance now" in resp.text


def test_manual_tracking_action_spawns_track_only(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_060000",
        stage="publish_done",
        publish_result={"instagram": {"status": "published", "id": "media-1"}},
    )
    mock_popen = MagicMock()
    with patch("dashboard.subprocess.Popen", mock_popen):
        resp = client.post(
            "/jobs/20260512_060000/track-now",
            headers=_auth(),
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/jobs/20260512_060000"
    cmd = mock_popen.call_args.args[0]
    assert cmd[1:] == ["main.py", "--track", "20260512_060000"]
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Manual performance tracking requested for 20260512_060000" in work_activity


def test_manual_tracking_action_rejects_unpublished_job(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_060000",
        stage="publish_done",
        publish_result={"instagram": {"status": "pending_queue"}},
    )
    resp = client.post("/jobs/20260512_060000/track-now", headers=_auth())
    assert resp.status_code == 400


def test_job_detail_shows_publish_controls(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_060000",
        publish_result={
            "facebook": {"status": "failed", "error": "bad request"},
            "instagram": {"status": "pending_queue", "due_at": "2026-05-16T06:00:00Z"},
        },
    )
    from models.content_job import ContentJob
    job = ContentJob.model_validate_json(
        (tmp_path / "output" / "Slayhack" / "20260512_060000" / "job.json").read_text()
    )
    with patch.object(_dm, "find_job", return_value=job):
        resp = client.get("/jobs/20260512_060000", headers=_auth())

    assert resp.status_code == 200
    assert "Publish control" in resp.text
    assert "Facebook failed" in resp.text
    assert "Instagram pending queue" in resp.text
    assert "Retry publish" in resp.text
    assert "Publish Instagram now" in resp.text


def test_retry_publish_spawns_publish_only(tmp_path, client, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_job(
        tmp_path,
        "20260512_060000",
        status="failed",
        stage="publish_done",
        publish_result={"facebook": {"status": "failed", "error": "bad request"}},
    )
    mock_popen = MagicMock()
    with patch("dashboard.subprocess.Popen", mock_popen):
        resp = client.post(
            "/jobs/20260512_060000/retry-publish",
            headers=_auth(),
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/jobs/20260512_060000"
    cmd = mock_popen.call_args.args[0]
    assert cmd[1:] == [
        "main.py", "--publish-only", "20260512_060000", "--schedule", "--publish-platform", "facebook",
    ]


def test_ops_retry_publish_failure_validates_and_logs(tmp_path, client, monkeypatch):
    _write_job(
        tmp_path,
        "20260512_060000",
        status="failed",
        stage="publish_done",
        publish_result={"instagram": {"status": "failed", "error": "400 Client Error: Bad Request"}},
    )
    mock_popen = MagicMock()
    with patch("dashboard.subprocess.Popen", mock_popen):
        resp = client.post(
            "/ops/publish-failures/20260512_060000/instagram/retry",
            headers=_auth(),
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/ops"
    cmd = mock_popen.call_args.args[0]
    assert cmd[1:] == [
        "main.py", "--publish-only", "20260512_060000", "--schedule", "--publish-platform", "instagram",
    ]
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Ops retry requested for instagram publish failure on 20260512_060000" in work_activity
    assert "meta bad request" in work_activity


def test_ops_retry_safe_instagram_failures_runs_ready_rows(tmp_path, client, monkeypatch):
    media_path = tmp_path / "output" / "Slayhack" / "20260512_060000" / "image.png"
    _write_job(
        tmp_path,
        "20260512_060000",
        status="failed",
        stage="publish_done",
        publish_result={"instagram": {"status": "failed", "error": "400 Client Error: Bad Request"}},
    )
    media_path.write_bytes(b"PNG")
    job_path = tmp_path / "output" / "Slayhack" / "20260512_060000" / "job.json"
    data = json.loads(job_path.read_text())
    data["content_type"] = "infographic"
    data["image_path"] = "output/Slayhack/20260512_060000/image.png"
    data["growth_strategy"] = {
        "hashtags": ["#slayhack"],
        "caption": "Ready caption",
        "best_post_time_utc": "14:00",
        "best_post_time_thai": "21:00",
        "editorial_guidance": {},
    }
    job_path.write_text(json.dumps(data))
    mock_popen = MagicMock()
    with patch("dashboard.subprocess.Popen", mock_popen):
        resp = client.post(
            "/ops/publish-failures/retry-safe-instagram",
            headers=_auth(),
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/ops"
    cmd = mock_popen.call_args.args[0]
    assert cmd[1:] == [
        "main.py", "--publish-only", "20260512_060000", "--schedule", "--publish-platform", "instagram",
    ]
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Retry all safe Instagram publish failures" in work_activity


def test_ops_retry_publish_failure_rejects_non_failed_platform(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_060000",
        publish_result={"instagram": {"status": "pending_queue"}},
    )

    resp = client.post(
        "/ops/publish-failures/20260512_060000/instagram/retry",
        headers=_auth(),
    )

    assert resp.status_code == 400


def test_publish_instagram_now_marks_due_and_runs_queue(tmp_path, client, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_job(
        tmp_path,
        "20260512_060000",
        publish_result={
            "instagram": {
                "status": "pending_queue",
                "scheduled_publish_time": 9999999999,
                "due_at": "2286-11-20T17:46:39Z",
            }
        },
    )
    mock_popen = MagicMock()
    with patch("dashboard.subprocess.Popen", mock_popen):
        resp = client.post(
            "/jobs/20260512_060000/publish-instagram-now",
            headers=_auth(),
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/jobs/20260512_060000"
    cmd = mock_popen.call_args.args[0]
    assert cmd[1:] == ["instagram_queue.py"]
    data = json.loads((tmp_path / "output" / "Slayhack" / "20260512_060000" / "job.json").read_text())
    ig_result = data["publish_result"]["instagram"]
    assert ig_result["publish_now_requested"] is True
    assert ig_result["scheduled_publish_time"] < 9999999999


def test_job_detail_workflow_marks_current_crew_stage(tmp_path, client):
    _write_job(
        tmp_path,
        "20260512_070000",
        brief="visual stage mission",
        status="running",
        stage="lila_done",
    )
    from models.content_job import ContentJob
    job = ContentJob.model_validate_json(
        (tmp_path / "output" / "Slayhack" / "20260512_070000" / "job.json").read_text()
    )
    with patch.object(_dm, "find_job", return_value=job):
        resp = client.get("/jobs/20260512_070000", headers=_auth())
    assert resp.status_code == 200
    assert "Shape the Vision" in resp.text
    assert "Current stage" in resp.text
    assert "Lila Lens is holding the current stage." in resp.text
    assert "Waiting for written content." in resp.text
    assert "Waiting for visual direction." in resp.text
    assert "Lila Lens" in resp.text
    assert "Studio Deck" in resp.text
    assert "timeline-step current" in resp.text
    assert "/aurora/crew/lila" in resp.text


def test_metrics_no_data(client):
    resp = client.get("/metrics", headers=_auth())
    assert resp.status_code == 200
    assert "fleet-header-logbook" in resp.text
    assert "No performance data" in resp.text


def test_metrics_shows_data(client):
    from reporter import PlatformStats
    fake_data = {
        "Slayhack": {
            "facebook": PlatformStats(job_count=3, total_reach=5000, total_likes=120),
        }
    }
    with patch.object(_dm, "load_performance_all", return_value=fake_data):
        resp = client.get("/metrics", headers=_auth())
    assert resp.status_code == 200
    assert "Slayhack" in resp.text
    assert "5,000" in resp.text


def test_trigger_get_shows_form(tmp_path, client):
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    (tmp_path / "projects" / "nayzfreedom_fleet" / "pm_profile.yaml").write_text("page_name: test\n")
    resp = client.get("/trigger", headers=_auth())
    assert resp.status_code == 200
    assert "<form" in resp.text
    assert '<option value="nayzfreedom_fleet" selected>test</option>' in resp.text


def test_trigger_spawns_subprocess(tmp_path, client):
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    (tmp_path / "projects" / "nayzfreedom_fleet" / "pm_profile.yaml").write_text("page_name: test\n")
    mock_popen = MagicMock()
    with patch("dashboard.subprocess.Popen", mock_popen):
        resp = client.post(
            "/trigger",
            data={"project": "nayzfreedom_fleet", "brief": "test brief", "content_type": "video"},
            headers=_auth(),
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/aurora/missions"
    mock_popen.assert_called_once()
    cmd = mock_popen.call_args.args[0]
    assert "main.py" in cmd
    assert "--project" in cmd
    assert "nayzfreedom_fleet" in cmd
    assert "--unattended" in cmd
    assert "--dry-run" not in cmd


def test_trigger_dry_run_adds_flag(tmp_path, client):
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    (tmp_path / "projects" / "nayzfreedom_fleet" / "pm_profile.yaml").write_text("page_name: test\n")
    mock_popen = MagicMock()
    with patch("dashboard.subprocess.Popen", mock_popen):
        resp = client.post(
            "/trigger",
            data={"project": "nayzfreedom_fleet", "brief": "test", "content_type": "video", "dry_run": "1"},
            headers=_auth(),
            follow_redirects=False,
        )
    assert resp.status_code == 303
    cmd = mock_popen.call_args.args[0]
    assert "--dry-run" in cmd


def test_trigger_rejects_unknown_project(client):
    resp = client.post(
        "/trigger",
        data={"project": "nonexistent", "brief": "test", "content_type": "video"},
        headers=_auth(),
    )
    assert resp.status_code == 400
