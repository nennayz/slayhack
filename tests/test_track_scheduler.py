from __future__ import annotations
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import sys
import pytest

_google = MagicMock()
sys.modules.setdefault("google", _google)
sys.modules.setdefault("google.genai", _google.genai)


def _past(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _future(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_empty_queue_returns_zero_and_runs_no_subprocess(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    mock_run = mocker.patch("track_scheduler.subprocess.run")
    from track_scheduler import run_track_scheduler
    result = run_track_scheduler(root=tmp_path)
    assert result == 0
    mock_run.assert_not_called()


def test_future_entries_are_skipped(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue
    write_queue([{"job_id": "abc", "page_name": "Test",
                  "track_at": _future(24), "attempt": 0}])
    mocker.patch("track_scheduler.subprocess.run")
    from track_scheduler import run_track_scheduler
    run_track_scheduler(root=tmp_path)
    from track_queue import read_queue
    assert len(read_queue()) == 1


def test_overdue_entry_fires_subprocess_with_correct_args(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue, read_queue
    write_queue([{"job_id": "job123", "page_name": "Test",
                  "track_at": _past(2), "attempt": 0}])
    mock_run = mocker.patch("track_scheduler.subprocess.run",
                            return_value=MagicMock(returncode=0))
    from track_scheduler import run_track_scheduler
    run_track_scheduler(root=tmp_path)
    cmd = mock_run.call_args[0][0]
    assert "--track" in cmd
    assert "job123" in cmd
    assert read_queue() == []
    from track_scheduler import recent_track_scheduler_history
    history = recent_track_scheduler_history(tmp_path)
    assert history[0]["state"] == "Ready"
    assert history[0]["processed"] == 1
    assert history[0]["succeeded"] == 1


def test_failed_track_increments_attempt_and_stays_in_queue(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue, read_queue
    write_queue([{"job_id": "abc", "page_name": "Test",
                  "track_at": _past(), "attempt": 0}])
    mocker.patch("track_scheduler.subprocess.run",
                 return_value=MagicMock(returncode=1))
    from track_scheduler import run_track_scheduler
    run_track_scheduler(root=tmp_path)
    entries = read_queue()
    assert len(entries) == 1
    assert entries[0]["attempt"] == 1


def test_second_failure_increments_attempt_to_2(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue, read_queue
    write_queue([{"job_id": "abc", "page_name": "Test",
                  "track_at": _past(), "attempt": 1}])
    mocker.patch("track_scheduler.subprocess.run",
                 return_value=MagicMock(returncode=1))
    from track_scheduler import run_track_scheduler
    run_track_scheduler(root=tmp_path)
    entries = read_queue()
    assert entries[0]["attempt"] == 2


def test_third_failure_alerts_and_removes_entry(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue, read_queue
    write_queue([{"job_id": "abc", "page_name": "Test",
                  "track_at": _past(), "attempt": 2}])
    mocker.patch("track_scheduler.subprocess.run",
                 return_value=MagicMock(returncode=1))
    mock_alert = mocker.patch("track_scheduler.send_healthcheck_alert")
    from track_scheduler import run_track_scheduler
    run_track_scheduler(root=tmp_path)
    mock_alert.assert_called_once()
    assert "abc" in mock_alert.call_args[0][0]
    assert read_queue() == []
    from track_scheduler import recent_track_scheduler_history
    history = recent_track_scheduler_history(tmp_path)
    assert history[0]["state"] == "Failed"
    assert history[0]["failed"] == 1


def test_timeout_counts_as_failure(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue, read_queue
    import subprocess
    write_queue([{"job_id": "abc", "page_name": "Test",
                  "track_at": _past(), "attempt": 0}])
    mocker.patch("track_scheduler.subprocess.run",
                 side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=60))
    from track_scheduler import run_track_scheduler
    run_track_scheduler(root=tmp_path)
    entries = read_queue()
    assert entries[0]["attempt"] == 1


def test_dry_run_skips_subprocess(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue, read_queue
    write_queue([{"job_id": "abc", "page_name": "Test",
                  "track_at": _past(), "attempt": 0}])
    mock_run = mocker.patch("track_scheduler.subprocess.run")
    from track_scheduler import run_track_scheduler
    run_track_scheduler(dry_run=True, root=tmp_path)
    mock_run.assert_not_called()
    assert len(read_queue()) == 1


def test_corrupt_queue_resets_and_continues(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "track_queue.json").write_text("not json ][")
    mock_run = mocker.patch("track_scheduler.subprocess.run")
    from track_scheduler import run_track_scheduler
    result = run_track_scheduler(root=tmp_path)
    assert result == 0
    mock_run.assert_not_called()


def test_empty_queue_records_history(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    mocker.patch("track_scheduler.subprocess.run")
    from track_scheduler import run_track_scheduler, recent_track_scheduler_history
    run_track_scheduler(root=tmp_path)
    history = recent_track_scheduler_history(tmp_path)
    assert history[0]["state"] == "Ready"
    assert history[0]["processed"] == 0
    assert history[0]["remaining"] == 0
