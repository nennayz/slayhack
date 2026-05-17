from __future__ import annotations
import json
from pathlib import Path

from instagram_queue import process_instagram_queue
from models.content_job import JobStatus
from tests.test_publish import make_publish_config, make_video_job


def _write_pending_job(root: Path, due: int = 1) -> str:
    job = make_video_job(dry_run=False, video_path=str(root / "video.mp4"))
    (root / "video.mp4").write_bytes(b"MP4")
    job.platforms = ["facebook", "instagram"]
    job.publish_result = {
        "facebook": {"status": "scheduled", "id": "fb-1"},
        "instagram": {
            "status": "pending_queue",
            "scheduled_publish_time": due,
            "due_at": "1970-01-01T00:00:01Z",
        },
    }
    job.status = JobStatus.COMPLETED
    out_dir = root / "output" / job.pm.page_name / job.id
    out_dir.mkdir(parents=True)
    (out_dir / "job.json").write_text(job.model_dump_json(indent=2))
    return job.id


def test_instagram_queue_publishes_due_job(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "b")
    job_id = _write_pending_job(tmp_path)
    published_job = make_video_job(dry_run=False, video_path=str(tmp_path / "video.mp4"))
    published_job.id = job_id  # must match so save_job writes to the right path
    published_job.publish_result = {"instagram": {"status": "published", "id": "ig-1"}}
    mocker.patch("instagram_queue.Config.from_env", return_value=make_publish_config())
    mock_run = mocker.patch("instagram_queue.PublishAgent.run", return_value=published_job)

    exit_code = process_instagram_queue(root=tmp_path)

    assert exit_code == 0
    mock_run.assert_called_once()
    saved = json.loads((tmp_path / "output" / "Slayhack" / job_id / "job.json").read_text())
    assert saved["publish_result"]["facebook"]["status"] == "scheduled"
    assert saved["publish_result"]["instagram"]["status"] == "published"
    assert saved["status"] == "completed"
    history = json.loads((tmp_path / "logs" / "instagram_queue_history.jsonl").read_text().splitlines()[-1])
    assert history["processed"] == 1
    assert history["published"] == 1
    assert history["retrying"] == 0
    assert history["failed"] == 0
    assert history["jobs"] == [{"job_id": job_id, "status": "published"}]
    work_activity = (tmp_path / "logs" / "work_activity.jsonl").read_text()
    assert "Instagram queue run completed" in work_activity


def test_instagram_queue_skips_future_job(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pending_job(tmp_path, due=4_102_444_800)
    mocker.patch("instagram_queue.Config.from_env", return_value=make_publish_config())
    mock_run = mocker.patch("instagram_queue.PublishAgent.run")

    exit_code = process_instagram_queue(root=tmp_path)

    assert exit_code == 0
    mock_run.assert_not_called()
    history = json.loads((tmp_path / "logs" / "instagram_queue_history.jsonl").read_text().splitlines()[-1])
    assert history["processed"] == 0
    assert history["published"] == 0


def test_instagram_queue_marks_failure_for_retry(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "b")
    job_id = _write_pending_job(tmp_path)
    failed_job = make_video_job(dry_run=False, video_path=str(tmp_path / "video.mp4"))
    failed_job.id = job_id
    failed_job.publish_result = {
        "instagram": {
            "status": "failed",
            "error": "Instagram failed access_token=secret-token",
        }
    }
    mocker.patch("instagram_queue._now_ts", return_value=100)
    mocker.patch("instagram_queue.Config.from_env", return_value=make_publish_config())
    mocker.patch("instagram_queue.PublishAgent.run", return_value=failed_job)

    exit_code = process_instagram_queue(root=tmp_path)

    assert exit_code == 0
    saved = json.loads((tmp_path / "output" / "Slayhack" / job_id / "job.json").read_text())
    ig_result = saved["publish_result"]["instagram"]
    assert saved["status"] == "completed"
    assert ig_result["status"] == "retrying"
    assert ig_result["retry_count"] == 1
    assert ig_result["next_retry_unix"] == 1000
    assert "secret-token" not in ig_result["error"]
    assert "<redacted>" in ig_result["error"]
    history = json.loads((tmp_path / "logs" / "instagram_queue_history.jsonl").read_text().splitlines()[-1])
    assert history["processed"] == 1
    assert history["retrying"] == 1
    assert history["failed"] == 0


def test_instagram_queue_fails_after_max_retries(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "b")
    job_id = _write_pending_job(tmp_path)
    path = tmp_path / "output" / "Slayhack" / job_id / "job.json"
    data = json.loads(path.read_text())
    data["publish_result"]["instagram"]["status"] = "retrying"
    data["publish_result"]["instagram"]["retry_count"] = 2
    data["publish_result"]["instagram"]["next_retry_unix"] = 1
    path.write_text(json.dumps(data))
    failed_job = make_video_job(dry_run=False, video_path=str(tmp_path / "video.mp4"))
    failed_job.id = job_id
    failed_job.publish_result = {"instagram": {"status": "failed", "error": "blocked"}}
    mocker.patch("instagram_queue._now_ts", return_value=100)
    mocker.patch("instagram_queue.Config.from_env", return_value=make_publish_config())
    mocker.patch("instagram_queue.PublishAgent.run", return_value=failed_job)

    exit_code = process_instagram_queue(root=tmp_path)

    assert exit_code == 1
    saved = json.loads(path.read_text())
    ig_result = saved["publish_result"]["instagram"]
    assert saved["status"] == "failed"
    assert ig_result["status"] == "failed"
    assert ig_result["retry_count"] == 3
    history = json.loads((tmp_path / "logs" / "instagram_queue_history.jsonl").read_text().splitlines()[-1])
    assert history["processed"] == 1
    assert history["failed"] == 1
