from __future__ import annotations
from datetime import datetime, timezone


from activity_logger import _daily_log_path, log_action, log_command


def test_daily_log_path_uses_utc_date(monkeypatch):
    fixed_dt = datetime(2026, 5, 14, 23, 59, 59, tzinfo=timezone.utc)
    path = _daily_log_path(fixed_dt)
    assert path.name == "activity-2026-05-14.log"


def test_log_command_writes_message(tmp_path, monkeypatch):
    monkeypatch.setattr("activity_logger.LOG_DIR", tmp_path)

    log_command("test_command", {"foo": "bar", "count": 3})
    files = list(tmp_path.glob("*.log"))
    assert len(files) == 1

    content = files[0].read_text(encoding="utf-8").strip()
    assert "COMMAND" in content
    assert "test_command" in content
    assert 'foo="bar"' in content
    assert "count=3" in content


def test_log_action_writes_message(tmp_path, monkeypatch):
    monkeypatch.setattr("activity_logger.LOG_DIR", tmp_path)

    log_action("test_action", {"job_id": "20260514_001122"})
    files = list(tmp_path.glob("*.log"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8").strip()
    assert "ACTION" in content
    assert "test_action" in content
    assert "job_id=\"20260514_001122\"" in content
