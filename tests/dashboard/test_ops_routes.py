# ruff: noqa: F403,F405
from .helpers import *  # noqa: F401,F403



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
