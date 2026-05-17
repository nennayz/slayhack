from __future__ import annotations

import json
import subprocess
import sys

import pytest

from work_activity import read_recent_work_activity, work_activity_status, write_work_activity


def test_write_work_activity_sanitizes_and_reads_recent(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")

    write_work_activity(
        tmp_path,
        "terminal_command",
        "Ran tests",
        command="pytest secret-token",
        files=["dashboard.py"],
        result="310 passed",
        next_action="Deploy",
        metadata={"token_echo": "secret-token", "count": 1},
    )

    path = tmp_path / "logs" / "work_activity.jsonl"
    raw = path.read_text()
    assert "secret-token" not in raw
    assert "<redacted>" in raw

    rows = read_recent_work_activity(tmp_path)

    assert rows[0]["event_type"] == "terminal_command"
    assert rows[0]["summary"] == "Ran tests"
    assert rows[0]["command"] == "pytest <redacted>"
    assert rows[0]["files"] == ["dashboard.py"]
    assert rows[0]["result"] == "310 passed"
    assert rows[0]["metadata"] == {"token_echo": "<redacted>", "count": 1}


def test_write_work_activity_rejects_invalid_event_type(tmp_path):
    with pytest.raises(ValueError, match="Invalid work activity event type"):
        write_work_activity(tmp_path, "unknown", "Nope")


def test_work_activity_status_counts_entries_and_archives(tmp_path):
    log_dir = tmp_path / "logs"
    archive_dir = log_dir / "archive"
    archive_dir.mkdir(parents=True)
    (log_dir / "work_activity.jsonl").write_text("{}\n{}\n")
    (archive_dir / "work_activity-20260516T000000Z.jsonl").write_text("{}\n")

    result = work_activity_status(tmp_path)

    assert result["state"] == "Ready"
    assert result["line_count"] == 2
    assert result["archive_count"] == 1
    assert "2 entries" in result["detail"]


def test_worklog_cli_writes_entry(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "worklog.py",
            "test",
            "--summary",
            "Full suite",
            "--result",
            "310 passed",
            "--root",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "work_activity=test_result" in result.stdout
    record = json.loads((tmp_path / "logs" / "work_activity.jsonl").read_text().splitlines()[-1])
    assert record["event_type"] == "test_result"
    assert record["summary"] == "Full suite"
    assert record["result"] == "310 passed"
