# ruff: noqa: F403,F405
from .helpers import *  # noqa: F401,F403



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
    assert "captain-deck-hero" in resp.text
    assert "captain-command-instruments" in resp.text
    assert "Command wheel" in resp.text
    assert "Route compass" in resp.text
    assert "Live publish locked" in resp.text
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
    assert 'data-station-icon="route-map"' in resp.text
    assert 'data-station-icon="shipyard"' in resp.text
    assert 'data-station-icon="harbor-gate"' in resp.text
    assert 'data-station-icon="captain-log"' in resp.text
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
    assert 'data-station-icon="route-map"' in deck.text
    assert 'data-station-icon="shipyard"' in deck.text
    assert 'data-station-icon="harbor-gate"' in deck.text
    assert 'data-station-icon="captain-log"' in deck.text
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
    assert 'data-station-icon="harbor-gate"' in aurora.text
    assert "Captain approval needed for handoff mission" in filtered.text
    assert 'value="harbor-gate" selected' in filtered.text
    assert 'value="nora" selected' in filtered.text
    assert "value=\"handoff\"" in filtered.text
    assert "checked" in filtered.text
    assert "Generation dry-run completed for console test" not in filtered.text
    assert "Tracking proof captured for published mission" not in filtered.text
