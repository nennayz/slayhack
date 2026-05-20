# ruff: noqa: F403,F405
from .helpers import *  # noqa: F401,F403



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
    assert "Confirm before generation" in page.text
    assert "Open Learning Runbook" in page.text


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
