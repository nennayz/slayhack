from __future__ import annotations
import subprocess
import sys
from unittest.mock import patch, MagicMock
import scheduler as sched_module


MONDAY_CALENDAR = {
    "monday": {
        "short_video_1": "15-40sec Reel: morning routine",
        "short_video_2": "15-40sec Reel: 5 outfit ideas",
        "long_video": "1-3min video: wardrobe guide",
        "article_1": "quiet luxury brands",
        "article_2": "old money style",
        "infographic_1": "color palette guide",
        "infographic_2": "capsule wardrobe checklist",
    }
}


def _make_ok_result():
    r = MagicMock()
    r.returncode = 0
    return r


def _make_fail_result():
    r = MagicMock()
    r.returncode = 1
    return r


def test_run_job_skips_child_pipeline_lock(tmp_path):
    with patch("scheduler.subprocess.run", return_value=_make_ok_result()) as mock_run:
        result = sched_module._run_job([sys.executable, "main.py"], tmp_path, "proj", "article_1", "article")

    assert result["failed"] is False
    assert mock_run.call_args.kwargs["env"]["NAYZ_SKIP_PIPELINE_LOCK"] == "1"


def test_scheduler_lock_recovers_stale_pid(tmp_path, monkeypatch):
    lock_file = tmp_path / "output" / "nayz_pipeline.lock"
    lock_file.parent.mkdir(parents=True)
    lock_file.write_text("999999")
    monkeypatch.setattr("scheduler.acquire_pid_lock", lambda path: (True, 12345, True))

    resolved, acquired = sched_module._acquire_scheduler_lock(tmp_path)

    assert acquired is True
    assert resolved == lock_file


def test_scheduler_loads_todays_brief(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    import yaml
    (tmp_path / "projects" / "nayzfreedom_fleet" / "weekly_calendar.yaml").write_text(
        yaml.dump(MONDAY_CALENDAR)
    )
    monkeypatch.setattr(sched_module, "_today_name", lambda: "monday")
    with patch("scheduler.subprocess.run", return_value=_make_ok_result()) as mock_run:
        exit_code = sched_module.run_scheduler(dry_run=False, root=tmp_path)
    assert exit_code == 0
    assert mock_run.call_count == 7
    calls_flat = [c.args[0] for c in mock_run.call_args_list]
    assert any("--content-type" in str(c) and "video" in str(c) for c in calls_flat)
    assert any("--content-type" in str(c) and "article" in str(c) for c in calls_flat)
    assert any("--content-type" in str(c) and "infographic" in str(c) for c in calls_flat)


def test_scheduler_skips_daily_scout_for_injected_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    import yaml
    (tmp_path / "projects" / "nayzfreedom_fleet" / "weekly_calendar.yaml").write_text(
        yaml.dump(MONDAY_CALENDAR)
    )
    monkeypatch.setattr(sched_module, "_today_name", lambda: "monday")
    with patch("scheduler.subprocess.run", return_value=_make_ok_result()), \
         patch("scheduler._run_daily_scout") as mock_scout:
        exit_code = sched_module.run_scheduler(dry_run=False, root=tmp_path)
    assert exit_code == 0
    mock_scout.assert_not_called()


def test_scheduler_can_run_daily_scout_when_requested(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    import yaml
    (tmp_path / "projects" / "nayzfreedom_fleet" / "weekly_calendar.yaml").write_text(
        yaml.dump(MONDAY_CALENDAR)
    )
    monkeypatch.setattr(sched_module, "_today_name", lambda: "monday")
    with patch("scheduler.subprocess.run", return_value=_make_ok_result()), \
         patch("scheduler._run_daily_scout") as mock_scout:
        exit_code = sched_module.run_scheduler(dry_run=True, root=tmp_path, run_scout=True)
    assert exit_code == 0
    mock_scout.assert_called_once_with(dry_run=True)


def test_scheduler_runs_social_packaging_after_production_loop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    import yaml
    (tmp_path / "projects" / "nayzfreedom_fleet" / "weekly_calendar.yaml").write_text(
        yaml.dump(MONDAY_CALENDAR)
    )
    monkeypatch.setattr(sched_module, "_today_name", lambda: "monday")
    with patch("scheduler.subprocess.run", return_value=_make_ok_result()), \
         patch("scheduler._run_daily_scout"), \
         patch("scheduler._run_daily_trend_scan"), \
         patch("scheduler._run_daily_idea_planner"), \
         patch("scheduler._run_daily_production_loop") as mock_production, \
         patch("scheduler._run_daily_social_packaging") as mock_social:
        exit_code = sched_module.run_scheduler(dry_run=True, root=tmp_path, run_scout=True)

    assert exit_code == 0
    mock_production.assert_called_once_with([], dry_run=True, root=tmp_path)
    mock_social.assert_called_once_with([], dry_run=True, root=tmp_path)


def test_scheduler_skips_missing_day(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    import yaml
    (tmp_path / "projects" / "nayzfreedom_fleet" / "weekly_calendar.yaml").write_text(
        yaml.dump({"monday": MONDAY_CALENDAR["monday"]})
    )
    monkeypatch.setattr(sched_module, "_today_name", lambda: "tuesday")
    with patch("scheduler.subprocess.run") as mock_run:
        exit_code = sched_module.run_scheduler(dry_run=False, root=tmp_path)
    assert mock_run.call_count == 0
    assert exit_code == 0


def test_scheduler_skips_blank_brief(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    import yaml
    calendar = {"monday": dict(MONDAY_CALENDAR["monday"])}
    calendar["monday"]["short_video_1"] = ""
    (tmp_path / "projects" / "nayzfreedom_fleet" / "weekly_calendar.yaml").write_text(
        yaml.dump(calendar)
    )
    monkeypatch.setattr(sched_module, "_today_name", lambda: "monday")
    with patch("scheduler.subprocess.run", return_value=_make_ok_result()) as mock_run:
        sched_module.run_scheduler(dry_run=False, root=tmp_path)
    assert mock_run.call_count == 6


def test_scheduler_uses_active_project_slugs_and_skips_alias_duplicates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import yaml
    for slug in ("nayzfreedom_fleet", "slay_hack", "stadium_sweethearts"):
        project_dir = tmp_path / "projects" / slug
        project_dir.mkdir(parents=True)
        (project_dir / "pm_profile.yaml").write_text(
            f'name: "PM"\npage_name: "{slug}"\npersona: "p"\n'
        )
        (project_dir / "brand.yaml").write_text(
            'mission: "m"\nvisual:\n  colors: []\n  style: ""\n'
            'platforms: ["instagram"]\ntone: ""\ntarget_audience: ""\nscript_style: ""\n'
        )
        (project_dir / "weekly_calendar.yaml").write_text(yaml.dump(MONDAY_CALENDAR))
    monkeypatch.setattr(sched_module, "_today_name", lambda: "monday")
    with patch("scheduler.subprocess.run", return_value=_make_ok_result()) as mock_run:
        exit_code = sched_module.run_scheduler(dry_run=False, root=tmp_path)
    assert exit_code == 0
    projects = [c.args[0][c.args[0].index("--project") + 1] for c in mock_run.call_args_list]
    assert projects.count("nayzfreedom_fleet") == 7
    assert "slay_hack" not in projects
    assert projects.count("stadium_sweethearts") == 7


def test_scheduler_continues_after_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    import yaml
    (tmp_path / "projects" / "nayzfreedom_fleet" / "weekly_calendar.yaml").write_text(
        yaml.dump(MONDAY_CALENDAR)
    )
    monkeypatch.setattr(sched_module, "_today_name", lambda: "monday")
    results = [_make_fail_result()] + [_make_ok_result()] * 6
    with patch("scheduler.subprocess.run", side_effect=results) as mock_run:
        exit_code = sched_module.run_scheduler(dry_run=False, root=tmp_path)
    assert mock_run.call_count == 7
    assert exit_code == 1


def test_scheduler_dry_run_passes_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    import yaml
    (tmp_path / "projects" / "nayzfreedom_fleet" / "weekly_calendar.yaml").write_text(
        yaml.dump(MONDAY_CALENDAR)
    )
    monkeypatch.setattr(sched_module, "_today_name", lambda: "monday")
    with patch("scheduler.subprocess.run", return_value=_make_ok_result()) as mock_run:
        sched_module.run_scheduler(dry_run=True, root=tmp_path)
    for c in mock_run.call_args_list:
        assert "--dry-run" in c.args[0]


def test_scheduler_safe_prep_passes_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    import yaml
    (tmp_path / "projects" / "nayzfreedom_fleet" / "weekly_calendar.yaml").write_text(
        yaml.dump(MONDAY_CALENDAR)
    )
    monkeypatch.setattr(sched_module, "_today_name", lambda: "monday")
    with patch("scheduler.subprocess.run", return_value=_make_ok_result()) as mock_run:
        sched_module.run_scheduler(safe_prep=True, root=tmp_path)
    for c in mock_run.call_args_list:
        assert "--safe-prep" in c.args[0]


def test_scheduler_exit_code_zero_on_all_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    import yaml
    (tmp_path / "projects" / "nayzfreedom_fleet" / "weekly_calendar.yaml").write_text(
        yaml.dump(MONDAY_CALENDAR)
    )
    monkeypatch.setattr(sched_module, "_today_name", lambda: "monday")
    with patch("scheduler.subprocess.run", return_value=_make_ok_result()):
        exit_code = sched_module.run_scheduler(dry_run=False, root=tmp_path)
    assert exit_code == 0


def test_scheduler_timeout_continues_and_sets_exit_1(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    import yaml
    (tmp_path / "projects" / "nayzfreedom_fleet" / "weekly_calendar.yaml").write_text(
        yaml.dump(MONDAY_CALENDAR)
    )
    monkeypatch.setattr(sched_module, "_today_name", lambda: "monday")
    mock_proc = MagicMock()
    timeout_exc = subprocess.TimeoutExpired(cmd=[], timeout=1800)
    timeout_exc.process = mock_proc
    side_effects = [timeout_exc] + [_make_ok_result()] * 6
    with patch("scheduler.subprocess.run", side_effect=side_effects) as mock_run:
        exit_code = sched_module.run_scheduler(dry_run=False, root=tmp_path)
    assert mock_run.call_count == 7
    assert exit_code == 1
    mock_proc.kill.assert_called_once()


def test_scheduler_calls_notifier_on_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    import yaml
    (tmp_path / "projects" / "nayzfreedom_fleet" / "weekly_calendar.yaml").write_text(
        yaml.dump(MONDAY_CALENDAR)
    )
    monkeypatch.setattr(sched_module, "_today_name", lambda: "monday")
    results = [_make_fail_result()] + [_make_ok_result()] * 6
    with patch("scheduler.subprocess.run", side_effect=results), \
         patch("scheduler.send_slack_alert") as mock_alert:
        sched_module.run_scheduler(dry_run=False, root=tmp_path)
    mock_alert.assert_called_once()
    failures = mock_alert.call_args.args[0]
    total = mock_alert.call_args.args[2]
    assert len(failures) == 1
    assert failures[0]["project"] == "nayzfreedom_fleet"
    assert failures[0]["brief"] == "short_video_1"
    assert failures[0]["content_type"] == "video"
    assert failures[0]["exit_code"] == 1
    assert total == 7


def test_scheduler_does_not_call_notifier_on_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    import yaml
    (tmp_path / "projects" / "nayzfreedom_fleet" / "weekly_calendar.yaml").write_text(
        yaml.dump(MONDAY_CALENDAR)
    )
    monkeypatch.setattr(sched_module, "_today_name", lambda: "monday")
    with patch("scheduler.subprocess.run", return_value=_make_ok_result()), \
         patch("scheduler.send_slack_alert") as mock_alert:
        sched_module.run_scheduler(dry_run=False, root=tmp_path)
    mock_alert.assert_not_called()


def test_scheduler_skips_production_video_jobs_without_google_credentials(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "nayzfreedom_fleet").mkdir(parents=True)
    import yaml
    (tmp_path / "projects" / "nayzfreedom_fleet" / "weekly_calendar.yaml").write_text(
        yaml.dump(MONDAY_CALENDAR)
    )
    monkeypatch.setattr(sched_module, "_ROOT", tmp_path)
    monkeypatch.setattr(sched_module, "_LOCK_FILE", tmp_path / "scheduler.lock")
    monkeypatch.setattr(sched_module, "_today_name", lambda: "monday")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with patch("scheduler.subprocess.run", return_value=_make_ok_result()) as mock_run:
        exit_code = sched_module.run_scheduler(dry_run=False, run_scout=False)
    assert exit_code == 0
    assert mock_run.call_count == 4
    for c in mock_run.call_args_list:
        assert "video" not in c.args[0]
