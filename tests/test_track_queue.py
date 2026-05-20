from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone


def _make_pm():
    from models.content_job import PMProfile, BrandProfile, VisualIdentity
    return PMProfile(
        name="Test",
        page_name="TestPage",
        persona="test pm",
        brand=BrandProfile(
            mission="test",
            visual=VisualIdentity(colors=["#FFF"], style="minimal"),
            platforms=["instagram"],
            tone="casual",
            target_audience="Gen Z",
            script_style="lowercase",
        ),
    )


def _make_job(published_at=None):
    from models.content_job import ContentJob
    job = ContentJob(project="test", pm=_make_pm(), brief="test", platforms=["instagram"])
    job.published_at = published_at
    return job


def test_read_queue_returns_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from track_queue import read_queue
    assert read_queue() == []


def test_write_and_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue, read_queue
    entries = [{"job_id": "abc", "page_name": "TestPage",
                "track_at": "2026-05-18T14:00:00Z", "attempt": 0}]
    write_queue(entries)
    assert read_queue() == entries


def test_write_and_read_support_explicit_root(tmp_path):
    from track_queue import write_queue, read_queue
    entries = [{"job_id": "rooted", "page_name": "TestPage",
                "track_at": "2026-05-18T14:00:00Z", "attempt": 0}]
    write_queue(entries, root=tmp_path)
    assert read_queue(root=tmp_path) == entries


def test_write_queue_is_atomic_no_tmp_file_left(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import write_queue
    write_queue([{"job_id": "abc", "page_name": "TestPage",
                  "track_at": "2026-05-18T14:00:00Z", "attempt": 0}])
    assert not (tmp_path / "output" / "track_queue.json.tmp").exists()
    data = json.loads((tmp_path / "output" / "track_queue.json").read_text())
    assert isinstance(data, list)


def test_read_queue_backs_up_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "track_queue.json").write_text("not valid json ][")
    from track_queue import read_queue
    assert read_queue() == []
    assert (tmp_path / "output" / "track_queue.json.corrupt").exists()


def test_enqueue_writes_two_entries_with_correct_offsets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import enqueue_track_snapshots, read_queue
    published_at = datetime(2026, 5, 17, 14, 0, 0, tzinfo=timezone.utc)
    job = _make_job(published_at=published_at)
    enqueue_track_snapshots(job)
    entries = read_queue()
    assert len(entries) == 2
    assert entries[0]["track_at"] == "2026-05-18T14:00:00Z"
    assert entries[1]["track_at"] == "2026-05-20T14:00:00Z"
    assert entries[0]["job_id"] == job.id
    assert entries[0]["page_name"] == "TestPage"
    assert entries[0]["attempt"] == 0


def test_enqueue_falls_back_to_now_when_published_at_is_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import enqueue_track_snapshots, read_queue
    before = datetime.now(timezone.utc)
    job = _make_job(published_at=None)
    enqueue_track_snapshots(job)
    after = datetime.now(timezone.utc)
    entries = read_queue()
    assert len(entries) == 2
    t24 = datetime.strptime(entries[0]["track_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    # track_at is truncated to whole seconds; compare against second-truncated bounds
    before_s = before.replace(microsecond=0)
    assert before_s + timedelta(hours=24) <= t24 <= after + timedelta(hours=24)


def test_enqueue_appends_to_existing_queue(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import enqueue_track_snapshots, read_queue
    published_at = datetime(2026, 5, 17, 14, 0, 0, tzinfo=timezone.utc)
    job1 = _make_job(published_at=published_at)
    job2 = _make_job(published_at=published_at)
    enqueue_track_snapshots(job1)
    enqueue_track_snapshots(job2)
    assert len(read_queue()) == 4


def test_enqueue_can_replace_existing_job_entries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    from track_queue import enqueue_track_snapshots, read_queue
    first_time = datetime(2026, 5, 17, 14, 0, 0, tzinfo=timezone.utc)
    second_time = datetime(2026, 5, 18, 16, 0, 0, tzinfo=timezone.utc)
    job = _make_job(published_at=first_time)
    enqueue_track_snapshots(job)
    job.published_at = second_time
    enqueue_track_snapshots(job, replace_existing=True)

    entries = read_queue()
    assert len(entries) == 2
    assert [entry["track_at"] for entry in entries] == ["2026-05-19T16:00:00Z", "2026-05-21T16:00:00Z"]


def test_summarize_track_queue_counts_due_overdue_and_retrying():
    from track_queue import summarize_track_queue
    now = datetime(2026, 5, 18, 14, 0, 0, tzinfo=timezone.utc)
    result = summarize_track_queue([
        {"job_id": "future", "page_name": "Test", "track_at": "2026-05-18T16:00:00Z", "attempt": 0},
        {"job_id": "due", "page_name": "Test", "track_at": "2026-05-18T13:30:00Z", "attempt": 1},
        {"job_id": "old", "page_name": "Test", "track_at": "2026-05-18T10:00:00Z", "attempt": 2},
        {"job_id": "bad", "page_name": "Test", "track_at": "not-a-date", "attempt": 0},
    ], now=now)

    assert result["counts"] == {
        "total": 4,
        "due_now": 2,
        "overdue": 1,
        "future": 1,
        "retrying": 2,
        "invalid": 1,
    }
    assert [row["job_id"] for row in result["rows"][:3]] == ["old", "bad", "due"]
