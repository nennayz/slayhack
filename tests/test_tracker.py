from __future__ import annotations
from datetime import datetime, timezone
import main as main_module
from tracker import track_job
from config import Config


def _make_config():
    return Config(
        brave_search_api_key="brave",
        openai_api_key="oai",
        meta_access_token="meta-token",
        meta_page_id="page-123",
        meta_ig_user_id="ig-456",
        tiktok_access_token="tiktok-token",
    )


def _make_published_job(publish_result: dict):
    from tests.test_publish import make_image_job
    job = make_image_job(dry_run=False)
    job.stage = "publish_done"
    job.publish_result = publish_result
    return job


def test_track_fb_fetches_metrics(mocker):
    mock_get = mocker.patch("tracker.requests.get")
    mock_get.return_value.raise_for_status = mocker.MagicMock()
    mock_get.return_value.json.return_value = {
        "likes": {"summary": {"total_count": 142}},
        "shares": {"count": 18},
        "insights": {"data": [{"values": [{"value": 3200}]}]},
    }
    job = _make_published_job({"facebook": {"status": "published", "id": "post-1"}})
    result = track_job(job, _make_config())
    assert len(result.performance) == 1
    p = result.performance[0]
    assert p.platform == "facebook"
    assert p.likes == 142
    assert p.reach == 3200
    assert p.shares == 18
    assert p.recorded_at is not None


def test_track_ig_fetches_metrics(mocker):
    mock_get = mocker.patch("tracker.requests.get")
    mock_get.return_value.raise_for_status = mocker.MagicMock()
    mock_get.return_value.json.return_value = {
        "like_count": 89,
        "reach": 1100,
        "saved": 34,
    }
    job = _make_published_job({"instagram": {"status": "published", "id": "media-1"}})
    result = track_job(job, _make_config())
    assert len(result.performance) == 1
    p = result.performance[0]
    assert p.platform == "instagram"
    assert p.likes == 89
    assert p.reach == 1100
    assert p.saves == 34


def test_track_skips_non_published(mocker):
    mock_get = mocker.patch("tracker.requests.get")
    job = _make_published_job({
        "facebook": {"status": "failed", "error": "quota"},
        "instagram": {"status": "skipped", "reason": "no hosting"},
    })
    result = track_job(job, _make_config())
    assert result.performance == []
    assert not mock_get.called


def test_track_partial_failure_continues(mocker):
    mock_get = mocker.patch("tracker.requests.get")
    fb_resp = mocker.MagicMock()
    fb_resp.raise_for_status = mocker.MagicMock()
    fb_resp.json.return_value = {
        "likes": {"summary": {"total_count": 50}},
        "shares": {"count": 5},
        "insights": {},
    }
    ig_resp = mocker.MagicMock()
    ig_resp.raise_for_status.side_effect = Exception("IG quota exceeded")
    mock_get.side_effect = [fb_resp, ig_resp]
    job = _make_published_job({
        "facebook": {"status": "published", "id": "post-2"},
        "instagram": {"status": "published", "id": "media-2"},
    })
    result = track_job(job, _make_config())
    assert len(result.performance) == 1
    assert result.performance[0].platform == "facebook"


def test_track_accumulates_snapshots(mocker):
    mock_get = mocker.patch("tracker.requests.get")
    mock_get.return_value.raise_for_status = mocker.MagicMock()
    mock_get.return_value.json.return_value = {
        "likes": {"summary": {"total_count": 10}},
        "shares": {},
        "insights": {},
    }
    job = _make_published_job({"facebook": {"status": "published", "id": "post-3"}})
    config = _make_config()
    track_job(job, config)
    track_job(job, config)
    assert len(job.performance) == 2


def test_track_tiktok_resolves_video_id_and_fetches_metrics(mocker):
    mock_post = mocker.patch("tracker.requests.post")
    mock_post.return_value.raise_for_status = mocker.MagicMock()
    job = _make_published_job({"tiktok": {"status": "published", "publish_id": "pub-1"}})
    job.id = "20260513_120000"
    job_ts = int(
        datetime.strptime("20260513_120000", "%Y%m%d_%H%M%S")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    mock_post.return_value.json.return_value = {
        "data": {
            "videos": [
                {
                    "id": "vid-1",
                    "create_time": job_ts + 30,
                    "like_count": 211,
                    "view_count": 8400,
                    "share_count": 47,
                }
            ]
        }
    }
    result = track_job(job, _make_config())
    assert len(result.performance) == 1
    p = result.performance[0]
    assert p.platform == "tiktok"
    assert p.likes == 211
    assert p.reach == 8400
    assert p.shares == 47
    assert result.publish_result["tiktok"]["video_id"] == "vid-1"
    mock_post.assert_called_once()
    call_url = mock_post.call_args[0][0]
    assert "video/list" in call_url


def test_track_tiktok_uses_cached_video_id(mocker):
    mock_post = mocker.patch("tracker.requests.post")
    mock_post.return_value.raise_for_status = mocker.MagicMock()
    mock_post.return_value.json.return_value = {
        "data": {
            "videos": [
                {"id": "vid-2", "like_count": 300, "view_count": 9000, "share_count": 60}
            ]
        }
    }
    job = _make_published_job({
        "tiktok": {"status": "published", "publish_id": "pub-2", "video_id": "vid-2"}
    })
    result = track_job(job, _make_config())
    assert len(result.performance) == 1
    assert result.performance[0].likes == 300
    call_url = mock_post.call_args[0][0]
    assert "video/query" in call_url


def test_track_fb_missing_id_skips_gracefully(mocker):
    mock_get = mocker.patch("tracker.requests.get")
    job = _make_published_job({"facebook": {"status": "published"}})  # no "id" key
    result = track_job(job, _make_config())
    assert result.performance == []
    assert not mock_get.called


def test_track_tiktok_no_match_skips_gracefully(mocker):
    mock_post = mocker.patch("tracker.requests.post")
    mock_post.return_value.raise_for_status = mocker.MagicMock()
    mock_post.return_value.json.return_value = {"data": {"videos": []}}
    job = _make_published_job({"tiktok": {"status": "published", "publish_id": "pub-99"}})
    job.id = "20260513_120000"
    result = track_job(job, _make_config())
    assert result.performance == []


def test_main_track_flag_dispatches_tracker(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from tests.test_publish import make_image_job, make_publish_config
    from job_store import save_job
    import sys

    job = make_image_job(dry_run=False)
    job.stage = "publish_done"
    job.publish_result = {"facebook": {"status": "published", "id": "post-1"}}
    save_job(job)

    cfg = make_publish_config()
    mock_track = mocker.patch.object(main_module, "track_job", return_value=job)
    mocker.patch.object(main_module.Config, "from_env", return_value=cfg)

    sys.argv = ["main.py", "--track", job.id]
    main_module.main()

    mock_track.assert_called_once_with(job, cfg)
