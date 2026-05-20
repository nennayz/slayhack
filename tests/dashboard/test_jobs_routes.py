# ruff: noqa: F403,F405
from .helpers import *  # noqa: F401,F403



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
            "posted_at": "2099-05-17T14:00:00+00:00",
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
    assert [item["track_at"] for item in queue] == ["2099-05-18T14:00:00Z", "2099-05-20T14:00:00Z"]
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
            "posted_at": "2099-05-17T14:00:00+00:00",
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
    assert [item["track_at"] for item in queue] == ["2099-05-18T14:00:00Z", "2099-05-20T14:00:00Z"]
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
                    "posted_at": "2099-05-17T14:00:00+00:00",
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
        published_at="2099-05-17T14:00:00+00:00",
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
            "track_at": "2099-05-18T14:00:00Z",
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
    assert "Wait for queued tracking snapshot at 2099-05-18T14:00:00Z." in resp.text
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
    assert "2099-05-18T14:00:00Z" in waiting_lane.text
    assert "Run tracking queue now" in waiting_lane.text

    complete_lane = client.get("/aurora/manual-posting?lane=tracking_complete", headers=_auth())
    assert complete_lane.status_code == 200
    assert "Closeout-to-Learning Assist" in complete_lane.text
    assert "Tracking complete to learning loop" in complete_lane.text
    assert "Learning bridge" in complete_lane.text
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
    assert resp.headers["location"].startswith("/aurora/manual-posting?lane=tracking_complete&closeout_result=")
    assert "Closeout%20saved%20for%2020260512_complete" in resp.headers["location"]
    saved = json.loads((tmp_path / "output" / "Slayhack" / "20260512_complete" / "job.json").read_text())
    closeout = saved["manual_post_kit"]["closeout"]
    assert closeout["status"] == "closed"
    assert closeout["learning_note"] == "Hook worked; keep the shorter CTA."
    assert closeout["proof_summary"]["post_url_present"] is True
    assert closeout["proof_summary"]["snapshot_24h_present"] is True
    assert closeout["proof_summary"]["snapshot_72h_present"] is True

    page = client.get(resp.headers["location"], headers=_auth())
    assert page.status_code == 200
    assert "Closeout saved" in page.text
    assert "create the daily learning draft next" in page.text
    assert "Closeout-to-Learning Assist" in page.text
    assert "Learning bridge" in page.text
    assert "Needs Captain learning review" in page.text
    assert "Closeout captured" in page.text
    assert "Create daily learning draft" in page.text
    assert "Open Learning Runbook" in page.text
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
