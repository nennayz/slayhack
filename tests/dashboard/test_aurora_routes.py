# ruff: noqa: F403,F405
from .helpers import *  # noqa: F401,F403



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
    assert "SlayHack PM Knowledge" in resp.text
    assert "PM Knowledge certification pending" in resp.text
    assert "Drive retrieval is ready" in resp.text
    assert "Drive retrieval: PASS" in resp.text
    assert "Direct PM UI: PARTIAL" in resp.text
    assert "Smoke checklist: READY" in resp.text
    assert "Run PM smoke checklist" in resp.text
    assert "Knowledge map" in resp.text
    assert "Captain Attention Lane" in resp.text
    assert "Learning Runbook" in resp.text


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
    assert "Nami" in crew.text
    assert "Genie" in crew.text
    assert "Video Producer" in crew.text
    assert "/static/crew/captain-nayz.webp" in crew.text
    assert "/static/crew/vera-reel.webp" in crew.text
    assert "/static/crew/slay.webp" in crew.text
    assert "/static/crew/stadium.webp" in crew.text
    assert "/static/crew/iris-gauge.webp" in crew.text
    assert "/static/crew/sage-ledger.webp" in crew.text
    assert "/static/crew/nami.webp" in crew.text
    assert "/static/crew/genie.webp" in crew.text
    assert "/static/crew/fleet-crew-group-20260518.webp" in crew.text
    assert "Crew Stations" in crew.text
    assert "Full Fleet formation" in crew.text
    assert "Aurora route map" in crew.text
    assert "Fleet Command" in crew.text
    assert "Page PMs" in crew.text
    assert "Aurora Production Route" in crew.text
    assert "Learning Loop" in crew.text
    assert "Concept Ships" in crew.text
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
    assert "/static/crew/vera-reel.webp" in vera.text
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
    static_crew = tmp_path / "static" / "crew" / "original"
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
    assert "static/crew/original/mia.png" in resp.text
    assert "Matches v7 review" in resp.text
    assert "Approved concept portrait" in resp.text
    assert "Crew Static Production Asset Audit" in resp.text
    assert "Deploy status" in resp.text
    assert "Live" in resp.text
    assert "SlayHack PM Knowledge" in resp.text
    assert "PM Knowledge certification pending" in resp.text
    assert "Direct PM UI: PARTIAL" in resp.text
    assert "Run PM smoke checklist" in resp.text
    assert "What is the canonical SlayHack knowledge root?" in resp.text
    assert "Any answer that renames PM Slay to Nayz fails the identity gate." in resp.text
    assert "Record PM UI result" in resp.text
    assert "Read first" in resp.text
    assert "Knowledge map" in resp.text
    assert "Update runbook" in resp.text
    assert "Direct UI result" in resp.text
    assert "archived markdown duplicates are historical only" in resp.text
    assert "Manual Posting Lessons" in resp.text
    assert "Daily Learning Brief intake" in resp.text
    assert "No closed manual posting lessons are ready for the daily brief yet." in resp.text
    assert "Daily brief review gate" in resp.text
    assert "Draft learning artifacts" in resp.text
    assert "current manual crew portrait set is approved production canon and has a production asset audit" in resp.text


def test_aurora_ebooks_page_renders_governed_product_factory(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.get("/aurora/ebooks", headers=_auth())

    assert resp.status_code == 200
    assert "E-book Product Factory" in resp.text
    assert "Registry-backed governance ready" in resp.text
    assert "projects/slay_hack/ebooks.yaml" in resp.text
    assert "Age Like Fine Wine" in resp.text
    assert "designed_pdf_ready" in resp.text
    assert "Live publish and checkout stay locked" in resp.text
    assert "PDF proof artifacts" in resp.text
    assert "Drive source verification" in resp.text
    assert "Registered artifacts: 5" in resp.text
    assert "Verified on this host: 5/5" in resp.text
    assert "Rendered PDF proof" in resp.text
    assert "Editable source document" in resp.text
    assert "E-book knowledge base" in resp.text
    assert "20260517-Age_Like_Fine_Wine_v1.pdf" in resp.text
    assert "Read-only proof check. Checkout, public sales, and live publish remain locked." in resp.text
    assert "docs/ebook_production_runbook.md" in resp.text
    assert "2026-05-17-ebook-production-dashboard-design.md" in resp.text
    assert "Content QA" in resp.text
    assert "Brand QA" in resp.text
    assert "Visual QA" in resp.text
    assert "PDF Technical QA" in resp.text
    assert "Monetization QA" in resp.text
    assert "0/5" in resp.text
    assert "Next missing QA gate: Content QA" in resp.text
    assert "Record QA" in resp.text
    assert "0/6" in resp.text
    assert "Next missing launch asset: sales page" in resp.text
    assert "Next non-copy launch asset:" not in resp.text
    assert "Record asset" in resp.text
    assert "Fine Wine 35-44 Monetization Lane" in resp.text
    assert "Slay Basics: 30 Hacks" in resp.text
    assert "Fine Wine 7-Day Glow Routine" in resp.text
    assert "The Glow Within" in resp.text
    assert "She&#39;s Got It Together" in resp.text
    assert "Sales source of truth" in resp.text
    assert "Start your Fine Wine glow-up" in resp.text
    assert "Checkout copy is draft-only and cannot be activated until Captain approval." in resp.text
    assert "Launch copy asset pack" in resp.text
    assert "Copy drafts review-ready: 2/2" in resp.text
    assert "Sales page draft" in resp.text
    assert "Checkout copy draft" in resp.text
    assert 'href="/aurora/ebooks/copy/sales_page?project_slug=slay_hack"' in resp.text
    assert 'href="/aurora/ebooks/assets/product_mockup?project_slug=slay_hack"' in resp.text
    assert 'href="/aurora/ebooks/assets/post_purchase_next_step?project_slug=slay_hack"' in resp.text
    assert 'href="/aurora/ebooks/assets/tracking_plan?project_slug=slay_hack"' in resp.text
    assert "age_like_fine_wine_sales_page.md" in resp.text
    assert "age_like_fine_wine_product_mockup.md" in resp.text
    assert "age_like_fine_wine_post_purchase_next_step.md" in resp.text
    assert "age_like_fine_wine_tracking_plan.md" in resp.text
    assert "Remove hardcoded API key fallback." in resp.text
    assert "7-day content push" in resp.text
    assert "tracking plan" in resp.text
    assert "Captain sale gate" in resp.text
    assert "Captain sale approval" in resp.text
    assert "Sale approval locked" in resp.text
    assert "Source integrity must be ready with a matching editable source and PDF proof." in resp.text
    assert "Checkout setup and delivery test" in resp.text
    assert "test setup packet ready checkout locked" in resp.text
    assert "Stripe Checkout Sessions or Payment Links" in resp.text
    assert "Captain price pending" in resp.text
    assert "Open protected PDF proof" in resp.text
    assert "Checkout smoke: 0/2" in resp.text
    assert "Next smoke check: Test-mode checkout setup" in resp.text
    assert "Public checkout gate: locked" in resp.text


def test_aurora_ebooks_launch_copy_asset_route_serves_registered_markdown(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.get("/aurora/ebooks/copy/sales_page?project_slug=slay_hack", headers=_auth())

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "Age Like Fine Wine - Sales Page Draft" in resp.text
    assert "Start your Fine Wine glow-up." in resp.text


def test_aurora_ebooks_page_surfaces_missing_drive_artifact(tmp_path, client):
    _write_ebook_registry(tmp_path)
    (
        tmp_path
        / "Drive"
        / "Slay Hack"
        / "Ebook Project"
        / "20260517-Slay-Ebook-Visual-Strategy.md"
    ).unlink()

    resp = client.get("/aurora/ebooks", headers=_auth())

    assert resp.status_code == 200
    assert "Registered artifacts: 5" in resp.text
    assert "Verified on this host: 4/5" in resp.text
    assert "Next missing artifact: Visual strategy" in resp.text
    assert "20260517-Slay-Ebook-Visual-Strategy.md" in resp.text


def test_aurora_ebooks_page_marks_drive_artifacts_external_when_drive_root_unmounted(tmp_path, client):
    _write_ebook_registry(tmp_path)
    project_bridge = tmp_path / "projects" / "slay_hack" / "project_bridge.yaml"
    project_bridge.write_text(
        'project: slay_hack\n'
        'display_name: "Slay Hack"\n'
        'pm: "Slay"\n'
        f'drive_root: "{tmp_path / "Missing Drive"}"\n'
    )

    resp = client.get("/aurora/ebooks", headers=_auth())

    assert resp.status_code == 200
    assert "Registered artifacts: 5" in resp.text
    assert "Verified on this host: 0/5" in resp.text
    assert "Drive root is registered but not mounted on this host." in resp.text
    assert "Next missing artifact:" not in resp.text
    assert "Rendered PDF proof" in resp.text


def test_aurora_ebooks_launch_copy_asset_route_rejects_unknown_asset(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.get("/aurora/ebooks/copy/not_registered?project_slug=slay_hack", headers=_auth())

    assert resp.status_code == 404
    assert "not_registered" in resp.json()["detail"]


def test_aurora_ebooks_launch_asset_route_serves_registered_markdown(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.get("/aurora/ebooks/assets/product_mockup?project_slug=slay_hack", headers=_auth())

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "Age Like Fine Wine - Product Mockup Draft" in resp.text
    assert "Sales page hero mockup." in resp.text


def test_aurora_ebooks_post_purchase_asset_route_serves_registered_markdown(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.get("/aurora/ebooks/assets/post_purchase_next_step?project_slug=slay_hack", headers=_auth())

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "Age Like Fine Wine - Post-Purchase Next Step Draft" in resp.text
    assert "Your Fine Wine glow-up guide is ready." in resp.text


def test_aurora_ebooks_tracking_plan_asset_route_serves_registered_markdown(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.get("/aurora/ebooks/assets/tracking_plan?project_slug=slay_hack", headers=_auth())

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "Age Like Fine Wine - Tracking Plan Draft" in resp.text
    assert "Measure traffic, conversion, delivery, support, and learning." in resp.text


def test_aurora_ebooks_delivery_proof_route_serves_protected_pdf(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.get(
        "/aurora/ebooks/delivery-proof/age_like_fine_wine?project_slug=slay_hack",
        headers=_auth(),
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content.startswith(b"%PDF-1.4 fine wine v3 proof")


def test_aurora_ebooks_records_qa_gate_result(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.post(
        "/aurora/ebooks/qa-gate",
        headers=_auth(),
        data={
            "project_slug": "slay_hack",
            "ebook_id": "age_like_fine_wine",
            "gate": "Content QA",
            "status": "PASS",
            "note": "Chapter value and claims checked.",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/aurora/ebooks?project=slay_hack&qa_result=Content%20QA%3A%20PASS")
    registry = yaml.safe_load((tmp_path / "projects" / "slay_hack" / "ebooks.yaml").read_text())
    gates = registry["ebooks"][0]["qa_gates"]
    content_gate = next(item for item in gates if item["gate"] == "Content QA")
    assert content_gate["status"] == "PASS"
    assert content_gate["note"] == "Chapter value and claims checked."
    assert content_gate["reviewed_by"] == "admin"
    assert content_gate["reviewed_at"]
    brand_gate = next(item for item in gates if item["gate"] == "Brand QA")
    assert brand_gate["status"] == "PARTIAL"

    page = client.get("/aurora/ebooks", headers=_auth())
    assert page.status_code == 200
    assert "1/5" in page.text
    assert "Next missing QA gate: Brand QA" in page.text
    assert "Chapter value and claims checked." in page.text


def test_aurora_ebooks_rejects_invalid_qa_status(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.post(
        "/aurora/ebooks/qa-gate",
        headers=_auth(),
        data={
            "project_slug": "slay_hack",
            "ebook_id": "age_like_fine_wine",
            "gate": "Content QA",
            "status": "READY",
            "note": "Invalid state.",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "QA status must be PASS, PARTIAL, or FAIL"


def test_aurora_ebooks_rejects_unknown_qa_gate(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.post(
        "/aurora/ebooks/qa-gate",
        headers=_auth(),
        data={
            "project_slug": "slay_hack",
            "ebook_id": "age_like_fine_wine",
            "gate": "Legal QA",
            "status": "PASS",
            "note": "Unknown gate.",
        },
    )

    assert resp.status_code == 400
    assert "is not registered" in resp.json()["detail"]


def test_aurora_ebooks_record_requires_registry(client):
    resp = client.post(
        "/aurora/ebooks/qa-gate",
        headers=_auth(),
        data={
            "project_slug": "slay_hack",
            "ebook_id": "age_like_fine_wine",
            "gate": "Content QA",
            "status": "PASS",
            "note": "No registry.",
        },
    )

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_aurora_ebooks_records_launch_asset_result(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.post(
        "/aurora/ebooks/launch-asset",
        headers=_auth(),
        data={
            "project_slug": "slay_hack",
            "ebook_id": "age_like_fine_wine",
            "asset": "sales page",
            "status": "review_ready",
            "note": "Offer stack draft is ready for review.",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"].startswith(
        "/aurora/ebooks?project=slay_hack&launch_result=sales%20page%3A%20review_ready"
    )
    registry = yaml.safe_load((tmp_path / "projects" / "slay_hack" / "ebooks.yaml").read_text())
    assets = registry["ebooks"][0]["launch_assets"]
    sales_page = next(item for item in assets if isinstance(item, dict) and item["name"] == "sales page")
    assert sales_page["status"] == "review_ready"
    assert sales_page["note"] == "Offer stack draft is ready for review."
    assert sales_page["reviewed_by"] == "admin"
    assert sales_page["reviewed_at"]
    seven_day = next(item for item in assets if isinstance(item, dict) and item["name"] == "7-day content push")
    assert seven_day["status"] == "review_ready"

    page = client.get("/aurora/ebooks", headers=_auth())
    assert page.status_code == 200
    assert "0/6" in page.text
    assert "Next missing launch asset: sales page" in page.text
    assert "Offer stack draft is ready for review." in page.text


def test_aurora_ebooks_records_approved_launch_asset_count(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.post(
        "/aurora/ebooks/launch-asset",
        headers=_auth(),
        data={
            "project_slug": "slay_hack",
            "ebook_id": "age_like_fine_wine",
            "asset": "sales page",
            "status": "approved",
            "note": "Sales page approved.",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 303
    page = client.get("/aurora/ebooks", headers=_auth())
    assert "1/6" in page.text
    assert "Next missing launch asset: product mockup" in page.text


def test_aurora_ebooks_records_checkout_smoke_when_sale_approved(tmp_path, client):
    _write_ebook_registry(tmp_path)
    registry_path = tmp_path / "projects" / "slay_hack" / "ebooks.yaml"
    registry = yaml.safe_load(registry_path.read_text())
    ebook = registry["ebooks"][0]
    ebook["source_integrity"]["status"] = "ready"
    ebook["captain_sale_gate"] = {"status": "approved", "approved_by": "Nayz"}
    for gate in ebook["qa_gates"]:
        gate["status"] = "PASS"
    for asset in ebook["launch_assets"]:
        asset["status"] = "approved"
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False))

    resp = client.post(
        "/aurora/ebooks/checkout-gate",
        headers=_auth(),
        data={
            "project_slug": "slay_hack",
            "ebook_id": "age_like_fine_wine",
            "check": "secure_delivery_link",
            "status": "PASS",
            "note": "Protected proof route opened.",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"].startswith(
        "/aurora/ebooks?project=slay_hack&checkout_result=Secure%20delivery%20link%3A%20PASS"
    )
    updated = yaml.safe_load(registry_path.read_text())
    checks = updated["ebooks"][0]["checkout_setup_gate"]["smoke_checks"]
    delivery_check = next(item for item in checks if item["key"] == "secure_delivery_link")
    assert delivery_check["status"] == "PASS"
    assert delivery_check["note"] == "Protected proof route opened."
    assert delivery_check["reviewed_by"] == "admin"
    assert delivery_check["reviewed_at"]
    assert updated["ebooks"][0]["checkout_setup_gate"]["status"] == "test_mode_in_progress_checkout_locked"

    page = client.get("/aurora/ebooks", headers=_auth())
    assert page.status_code == 200
    assert "Checkout smoke: 1/2" in page.text
    assert "Protected proof route opened." in page.text


def test_aurora_ebooks_rejects_checkout_smoke_before_sale_approval(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.post(
        "/aurora/ebooks/checkout-gate",
        headers=_auth(),
        data={
            "project_slug": "slay_hack",
            "ebook_id": "age_like_fine_wine",
            "check": "secure_delivery_link",
            "status": "PASS",
            "note": "Too early.",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Checkout setup is locked until Captain sale approval is recorded"


def test_aurora_ebooks_rejects_invalid_launch_asset_status(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.post(
        "/aurora/ebooks/launch-asset",
        headers=_auth(),
        data={
            "project_slug": "slay_hack",
            "ebook_id": "age_like_fine_wine",
            "asset": "sales page",
            "status": "live",
            "note": "Invalid state.",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Launch asset status must be missing, draft_ready, review_ready, or approved"


def test_aurora_ebooks_rejects_unknown_launch_asset(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.post(
        "/aurora/ebooks/launch-asset",
        headers=_auth(),
        data={
            "project_slug": "slay_hack",
            "ebook_id": "age_like_fine_wine",
            "asset": "checkout activation",
            "status": "approved",
            "note": "Unknown asset.",
        },
    )

    assert resp.status_code == 400
    assert "is not registered" in resp.json()["detail"]


def test_aurora_ebooks_rejects_sale_gate_approval_when_blocked(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.post(
        "/aurora/ebooks/sale-gate",
        headers=_auth(),
        data={"project_slug": "slay_hack", "ebook_id": "age_like_fine_wine"},
    )

    assert resp.status_code == 400
    assert "Captain sale approval is locked" in resp.json()["detail"]
    assert "QA gates still blocked" in resp.json()["detail"]
    assert "Launch assets still need approval" in resp.json()["detail"]
    assert "Source integrity must be ready" in resp.json()["detail"]


def test_aurora_ebooks_records_sale_gate_approval_when_ready(tmp_path, client):
    _write_ebook_registry(tmp_path)
    registry_path = tmp_path / "projects" / "slay_hack" / "ebooks.yaml"
    registry = yaml.safe_load(registry_path.read_text())
    ebook = registry["ebooks"][0]
    ebook["source_integrity"] = {"status": "ready"}
    ebook["captain_sale_gate"] = {
        "label": "Captain sale approval",
        "status": "locked",
        "action_label": "Captain Approve E-book For Sale",
        "approval_summary": {
            "heading": "Captain approval package",
            "note": "Approving this gate keeps checkout setup separate.",
            "items": ["Product: Age Like Fine Wine", "Checkout remains locked until setup testing."],
        },
    }
    for gate in ebook["qa_gates"]:
        gate["status"] = "PASS"
    for asset in ebook["launch_assets"]:
        asset["status"] = "approved"
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False))

    page = client.get("/aurora/ebooks", headers=_auth())
    assert page.status_code == 200
    assert "Captain Approve E-book For Sale" in page.text
    assert "Captain approval package" in page.text
    assert "Product: Age Like Fine Wine" in page.text
    assert "Checkout remains locked until setup testing." in page.text

    resp = client.post(
        "/aurora/ebooks/sale-gate",
        headers=_auth(),
        data={"project_slug": "slay_hack", "ebook_id": "age_like_fine_wine"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"].startswith(
        "/aurora/ebooks?project=slay_hack&launch_result=Captain%20sale%20approval%3A%20approved"
    )
    updated = yaml.safe_load(registry_path.read_text())
    gate = updated["ebooks"][0]["captain_sale_gate"]
    assert gate["status"] == "approved"
    assert gate["approved_by"] == "admin"
    assert gate["approved_at"]

    approved_page = client.get("/aurora/ebooks", headers=_auth())
    assert "Sale approved by admin" in approved_page.text
    assert "Sale approval recorded" in approved_page.text

    repeated = client.post(
        "/aurora/ebooks/sale-gate",
        headers=_auth(),
        data={"project_slug": "slay_hack", "ebook_id": "age_like_fine_wine"},
        follow_redirects=False,
    )
    assert repeated.status_code == 303
    assert repeated.headers["location"].startswith(
        "/aurora/ebooks?project=slay_hack&launch_result=Captain%20sale%20approval%3A%20already%20approved"
    )


def test_aurora_ebooks_page_renders_empty_state_without_registry(client):
    resp = client.get("/aurora/ebooks", headers=_auth())

    assert resp.status_code == 200
    assert "E-book Product Factory" in resp.text
    assert "No e-book registry is ready for this project" in resp.text
    assert "projects/nayzfreedom_fleet/ebooks.yaml" in resp.text
    assert "Live publish and checkout stay locked until Captain approval." in resp.text


def test_aurora_ebooks_link_is_in_navigation(tmp_path, client):
    _write_ebook_registry(tmp_path)

    resp = client.get("/aurora/ebooks", headers=_auth())

    assert resp.status_code == 200
    assert 'class="nav-group nav-dropdown"' in resp.text
    assert '<summary class="">More</summary>' in resp.text
    assert 'class="workflow-rail-step workflow-more active station-workflow"' in resp.text
    assert "<strong>More</strong>" in resp.text
    assert "Map + monetize" in resp.text
    assert 'href="/aurora/workflow"' in resp.text
    assert 'href="/aurora/ebooks">E-books</a>' in resp.text


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
    assert "/static/crew/nami.webp" in freedom.text
    assert "privacy and memory boundaries" in freedom.text
    assert lyra.status_code == 200
    assert "Song voyage" in lyra.text
    assert "Genie" in lyra.text
    assert "/static/crew/genie.webp" in lyra.text
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
    (tmp_path / "static" / "ships" / "aurora-hero.webp").write_bytes(b"png")

    resp = client.get("/readiness", headers=_auth())

    assert resp.status_code == 200
    assert "Readiness" in resp.text
    assert "fleet-hero-readiness" in resp.text
    assert "Dashboard auth" in resp.text
    assert "Project config" in resp.text
    assert "Deploy files" in resp.text
    assert "Privacy boundary" in resp.text
