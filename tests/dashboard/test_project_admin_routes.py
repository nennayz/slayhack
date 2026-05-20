# ruff: noqa: F403,F405
from .helpers import *  # noqa: F401,F403



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
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "--host" in result.stdout


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


def test_slayobjects_live_dashboard_empty_state(client):
    resp = client.get("/aurora/slayobjects/live", headers=_auth())
    assert resp.status_code == 200
    assert "SlayObjects Live Dashboard" in resp.text
    assert "TikTok" in resp.text
    assert "Instagram" in resp.text
    assert "Facebook" in resp.text
    assert "Manual-ready" in resp.text
    assert "Record first snapshot" in resp.text
    assert "Live publish stays locked" in resp.text


def test_slayobjects_live_dashboard_records_manual_snapshot(tmp_path, client):
    resp = client.post(
        "/aurora/slayobjects/live/snapshot",
        data={
            "platform": "tiktok",
            "content_url": "https://www.tiktok.com/@slayobjects/video/123",
            "views": "1,250",
            "reach": "0",
            "likes": "88",
            "comments": "9",
            "saves": "17",
            "shares": "11",
            "followers": "900",
            "note": "hook test",
        },
        headers=_auth(),
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/aurora/slayobjects/live?snapshot_result=")

    snapshot_path = tmp_path / "output" / "slayobjects_metrics" / "snapshots.jsonl"
    saved = json.loads(snapshot_path.read_text().splitlines()[0])
    assert saved["platform"] == "tiktok"
    assert saved["views"] == 1250
    assert saved["shares"] == 11

    page = client.get("/aurora/slayobjects/live", headers=_auth())
    assert page.status_code == 200
    assert "1,250" in page.text
    assert "Scale winning signal" in page.text
    assert "https://www.tiktok.com/@slayobjects/video/123" in page.text
    assert "Recorded SlayObjects tiktok metric snapshot" in (
        tmp_path / "logs" / "work_activity.jsonl"
    ).read_text()


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
