from agents.publish import PublishAgent, has_publish_failures
from config import Config
from models.content_job import ContentType, ImageCaption, Article, Script, GrowthStrategy
from publish_control import AutoPostingDisabledError


def make_publish_config():
    return Config(
        brave_search_api_key="brave",
        openai_api_key="oai",
        meta_access_token="meta-token",
        meta_page_id="page-123",
        meta_ig_user_id="ig-456",
        public_base_url="",
        tiktok_access_token="tiktok-token",
        youtube_client_id="yt-client-id",
        youtube_client_secret="yt-client-secret",
        youtube_refresh_token="yt-refresh-token",
    )


def _make_growth_strategy():
    return GrowthStrategy(
        hashtags=["#glam"],
        caption="look of the day",
        best_post_time_utc="13:00",
        best_post_time_thai="20:00",
    )


def make_image_job(dry_run=True):
    from tests.test_bella import make_job_with_idea
    job = make_job_with_idea(dry_run=dry_run, content_type=ContentType.IMAGE)
    job.bella_output = ImageCaption(caption="Soft glam look", alt_text="Woman in gold")
    job.visual_prompt = "Gold lipstick on marble"
    job.image_path = "assets/placeholder.png"
    job.growth_strategy = _make_growth_strategy()
    return job


def make_video_job(dry_run=True, video_path=None):
    from tests.test_bella import make_job_with_idea
    job = make_job_with_idea(dry_run=dry_run, content_type=ContentType.VIDEO)
    job.bella_output = Script(hook="h", body="b", cta="c", duration_seconds=30)
    job.visual_prompt = "Cinematic gold close-up"
    job.video_path = video_path
    job.growth_strategy = _make_growth_strategy()
    return job


def make_article_job(dry_run=True):
    from tests.test_bella import make_job_with_idea
    job = make_job_with_idea(dry_run=dry_run, content_type=ContentType.ARTICLE)
    job.bella_output = Article(heading="The Look", body="Step 1...", cta="Shop now")
    job.growth_strategy = _make_growth_strategy()
    return job


def test_publish_dry_run_sets_result():
    agent = PublishAgent(make_publish_config())
    job = make_image_job(dry_run=True)
    job = agent.run(job)
    assert job.publish_result == {"dry_run": True, "platforms": job.platforms}
    assert job.stage == "publish_done"


def test_has_publish_failures_detects_failed_platform():
    assert has_publish_failures({"facebook": {"status": "failed"}}) is True
    assert has_publish_failures({"facebook": {"status": "published"}}) is False
    assert has_publish_failures(None) is False


def test_publish_live_fb_image_calls_photos_endpoint(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    img_file = tmp_path / "image.png"
    img_file.write_bytes(b"PNG")
    mock_post = mocker.patch("agents.publish.requests.post")
    mock_post.return_value.raise_for_status = mocker.MagicMock()
    mock_post.return_value.json.return_value = {"id": "post-1"}
    agent = PublishAgent(make_publish_config())
    job = make_image_job(dry_run=False)
    job.image_path = str(img_file)
    job.platforms = ["facebook"]
    job = agent.run(job)
    assert mock_post.called
    call_url = mock_post.call_args[0][0]
    assert "page-123/photos" in call_url
    assert job.publish_result["facebook"]["status"] == "published"


def test_publish_live_blocked_when_auto_posting_disabled(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NAYZ_AUTO_POSTING_DISABLED", "1")
    img_file = tmp_path / "image.png"
    img_file.write_bytes(b"PNG")
    mock_post = mocker.patch("agents.publish.requests.post")
    agent = PublishAgent(make_publish_config())
    job = make_image_job(dry_run=False)
    job.image_path = str(img_file)
    job.platforms = ["facebook"]

    try:
        agent.run(job)
        raised = None
    except AutoPostingDisabledError as exc:
        raised = exc

    assert raised is not None
    assert "NAYZ_AUTO_POSTING_DISABLED=1" in str(raised)
    mock_post.assert_not_called()


def test_publish_live_fb_video_calls_videos_endpoint(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vid_file = tmp_path / "video.mp4"
    vid_file.write_bytes(b"MP4")
    mock_post = mocker.patch("agents.publish.requests.post")
    mock_post.return_value.raise_for_status = mocker.MagicMock()
    mock_post.return_value.json.return_value = {"id": "vid-1"}
    agent = PublishAgent(make_publish_config())
    job = make_video_job(dry_run=False, video_path=str(vid_file))
    job.platforms = ["facebook"]
    job = agent.run(job)
    call_url = mock_post.call_args[0][0]
    assert "page-123/videos" in call_url
    assert job.publish_result["facebook"]["status"] == "published"


def test_publish_live_fb_article_calls_feed_endpoint(mocker):
    mock_post = mocker.patch("agents.publish.requests.post")
    mock_post.return_value.raise_for_status = mocker.MagicMock()
    mock_post.return_value.json.return_value = {"id": "feed-1"}
    agent = PublishAgent(make_publish_config())
    job = make_article_job(dry_run=False)
    job.platforms = ["facebook"]
    job = agent.run(job)
    call_url = mock_post.call_args[0][0]
    assert "page-123/feed" in call_url
    assert job.publish_result["facebook"]["status"] == "published"


def test_publish_live_fb_schedule_flag_sends_scheduled_time(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    img_file = tmp_path / "image.png"
    img_file.write_bytes(b"PNG")
    mock_post = mocker.patch("agents.publish.requests.post")
    mock_post.return_value.raise_for_status = mocker.MagicMock()
    mock_post.return_value.json.return_value = {"id": "post-sched"}
    agent = PublishAgent(make_publish_config())
    job = make_image_job(dry_run=False)
    job.image_path = str(img_file)
    job.platforms = ["facebook"]
    job = agent.run(job, schedule=True)
    assert "scheduled_publish_time" in str(mock_post.call_args)
    assert job.publish_result["facebook"]["status"] == "scheduled"


def test_publish_live_ig_image_creates_container_then_publishes(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    img_file = tmp_path / "image.png"
    img_file.write_bytes(b"PNG")
    mock_post = mocker.patch("agents.publish.requests.post")
    container_resp = mocker.MagicMock()
    container_resp.raise_for_status = mocker.MagicMock()
    container_resp.json.return_value = {"id": "container-1"}
    publish_resp = mocker.MagicMock()
    publish_resp.raise_for_status = mocker.MagicMock()
    publish_resp.json.return_value = {"id": "ig-post-1"}
    mock_post.side_effect = [container_resp, publish_resp]
    agent = PublishAgent(make_publish_config())
    job = make_image_job(dry_run=False)
    job.image_path = str(img_file)
    job.platforms = ["instagram"]
    job = agent.run(job)
    assert mock_post.call_count == 2
    container_url = mock_post.call_args_list[0][0][0]
    publish_url = mock_post.call_args_list[1][0][0]
    assert "ig-456/media" in container_url
    assert "ig-456/media_publish" in publish_url
    assert job.publish_result["instagram"]["status"] == "published"


def test_publish_article_skips_instagram(mocker):
    mock_post = mocker.patch("agents.publish.requests.post")
    mock_post.return_value.raise_for_status = mocker.MagicMock()
    mock_post.return_value.json.return_value = {"id": "fb-1"}
    agent = PublishAgent(make_publish_config())
    job = make_article_job(dry_run=False)
    job.platforms = ["instagram", "facebook"]
    job = agent.run(job)
    assert "instagram" not in job.publish_result
    assert job.publish_result["facebook"]["status"] == "published"
    call_url = mock_post.call_args[0][0]
    assert "ig-456" not in call_url


def test_publish_partial_failure_records_per_platform(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    img_file = tmp_path / "image.png"
    img_file.write_bytes(b"PNG")
    mock_post = mocker.patch("agents.publish.requests.post")
    fb_resp = mocker.MagicMock()
    fb_resp.raise_for_status = mocker.MagicMock()
    fb_resp.json.return_value = {"id": "fb-ok"}
    mock_post.side_effect = [fb_resp, Exception("IG quota exceeded")]
    agent = PublishAgent(make_publish_config())
    job = make_image_job(dry_run=False)
    job.image_path = str(img_file)
    job.platforms = ["facebook", "instagram"]
    job = agent.run(job)
    assert job.publish_result["facebook"]["status"] == "published"
    assert job.publish_result["instagram"]["status"] == "failed"
    assert "IG quota exceeded" in job.publish_result["instagram"]["error"]
    assert job.stage == "publish_done"


def test_publish_target_platform_preserves_other_results(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    img_file = tmp_path / "image.png"
    img_file.write_bytes(b"PNG")
    mock_post = mocker.patch("agents.publish.requests.post")
    fb_resp = mocker.MagicMock()
    fb_resp.raise_for_status = mocker.MagicMock()
    fb_resp.json.return_value = {"id": "fb-retry-ok"}
    mock_post.return_value = fb_resp
    agent = PublishAgent(make_publish_config())
    job = make_image_job(dry_run=False)
    job.image_path = str(img_file)
    job.platforms = ["facebook", "instagram"]
    job.publish_result = {
        "facebook": {"status": "failed", "error": "bad request"},
        "instagram": {"status": "published", "id": "ig-existing"},
    }

    job = agent.run(job, schedule=True, target_platforms=["facebook"])

    assert mock_post.call_count == 1
    assert job.publish_result["facebook"]["status"] == "scheduled"
    assert job.publish_result["instagram"]["id"] == "ig-existing"


def test_publish_missing_image_path_raises_value_error():
    import pytest
    agent = PublishAgent(make_publish_config())
    job = make_image_job(dry_run=False)
    job.image_path = None
    with pytest.raises(ValueError, match=job.id):
        agent.run(job)


def test_publish_missing_media_file_raises_value_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import pytest
    agent = PublishAgent(make_publish_config())
    job = make_image_job(dry_run=False)
    job.image_path = str(tmp_path / "nonexistent.png")
    with pytest.raises(ValueError, match=job.id):
        agent.run(job)


def test_publish_tool_registered_in_agent_tools():
    from tools.agent_tools import get_tool_definitions
    names = [t["name"] for t in get_tool_definitions()]
    assert "run_publish" in names


def test_publish_agent_registered_in_orchestrator():
    from orchestrator import Orchestrator
    from config import Config
    cfg = Config(brave_search_api_key="b", openai_api_key="o")
    orch = Orchestrator(cfg)
    assert "publish" in orch.agents


def test_publish_sets_published_at_for_immediate_post(mocker, tmp_path, monkeypatch):
    from datetime import datetime, timezone
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    img_file = tmp_path / "image.png"
    img_file.write_bytes(b"PNG")
    agent = PublishAgent(make_publish_config())
    job = make_image_job(dry_run=False)
    job.image_path = str(img_file)
    job.platforms = ["facebook", "instagram"]
    mocker.patch.object(agent, "_post_facebook", return_value={"id": "fb1"})
    mocker.patch.object(agent, "_post_instagram", return_value={"id": "ig1"})
    mocker.patch("agents.publish.enqueue_track_snapshots")
    before = datetime.now(timezone.utc)
    agent.run_live(job)
    after = datetime.now(timezone.utc)
    assert job.published_at is not None
    assert before <= job.published_at <= after


def test_publish_enqueues_track_snapshots_after_live_publish(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    img_file = tmp_path / "image.png"
    img_file.write_bytes(b"PNG")
    agent = PublishAgent(make_publish_config())
    job = make_image_job(dry_run=False)
    job.image_path = str(img_file)
    job.platforms = ["facebook"]
    mocker.patch.object(agent, "_post_facebook", return_value={"id": "fb1"})
    mock_enqueue = mocker.patch("agents.publish.enqueue_track_snapshots")
    agent.run_live(job)
    mock_enqueue.assert_called_once_with(job)


def test_publish_dry_run_does_not_enqueue(mocker):
    agent = PublishAgent(make_publish_config())
    job = make_image_job(dry_run=True)
    mock_enqueue = mocker.patch("agents.publish.enqueue_track_snapshots")
    agent.run_dry(job)
    mock_enqueue.assert_not_called()


def test_main_publish_only_flag_dispatches_publish_agent(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from job_store import save_job

    job = make_image_job(dry_run=False)
    img_file = tmp_path / "image.png"
    img_file.write_bytes(b"PNG")
    job.image_path = str(img_file)
    job.stage = "emma_done"
    save_job(job)

    mock_run = mocker.patch.object(PublishAgent, "run_live", return_value=job)
    mocker.patch("main.Config.from_env", return_value=make_publish_config())

    import sys
    sys.argv = ["main.py", "--publish-only", job.id, "--publish-platform", "facebook"]
    from main import main
    main()

    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["target_platforms"] == ["facebook"]


def test_publish_live_ig_reels_uses_resumable_upload(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vid_file = tmp_path / "video.mp4"
    vid_file.write_bytes(b"MP4")
    mock_post = mocker.patch("agents.publish.requests.post")
    mock_get = mocker.patch("agents.publish.requests.get")
    init_resp = mocker.MagicMock()
    init_resp.raise_for_status = mocker.MagicMock()
    init_resp.json.return_value = {"id": "container-2", "uri": "https://rupload.facebook.com/upload-123"}
    upload_resp = mocker.MagicMock()
    upload_resp.raise_for_status = mocker.MagicMock()
    upload_resp.json.return_value = {"success": True}
    status_resp = mocker.MagicMock()
    status_resp.raise_for_status = mocker.MagicMock()
    status_resp.json.return_value = {"status_code": "FINISHED"}
    mock_get.return_value = status_resp
    publish_resp = mocker.MagicMock()
    publish_resp.raise_for_status = mocker.MagicMock()
    publish_resp.json.return_value = {"id": "reel-1"}
    mock_post.side_effect = [init_resp, upload_resp, publish_resp]
    agent = PublishAgent(make_publish_config())
    job = make_video_job(dry_run=False, video_path=str(vid_file))
    job.platforms = ["instagram"]
    job = agent.run(job)
    assert mock_post.call_count == 3
    init_url = mock_post.call_args_list[0][0][0]
    upload_url = mock_post.call_args_list[1][0][0]
    publish_url = mock_post.call_args_list[2][0][0]
    assert "ig-456/media" in init_url
    assert "rupload.facebook.com" in upload_url
    assert mock_get.call_args[0][0].endswith("/container-2")
    assert mock_get.call_args[1]["params"] == {"fields": "status_code"}
    assert "ig-456/media_publish" in publish_url
    assert job.publish_result["instagram"]["status"] == "published"


def test_publish_live_ig_reels_schedule_publishes_without_scheduled_field(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vid_file = tmp_path / "video.mp4"
    vid_file.write_bytes(b"MP4")
    mock_post = mocker.patch("agents.publish.requests.post")
    agent = PublishAgent(make_publish_config())
    job = make_video_job(dry_run=False, video_path=str(vid_file))
    job.platforms = ["instagram"]
    job = agent.run(job, schedule=True)
    mock_post.assert_not_called()
    assert job.publish_result["instagram"]["status"] == "pending_queue"
    assert "due_at" in job.publish_result["instagram"]
    assert "just-in-time publish" in job.publish_result["instagram"]["reason"]


def test_publish_meta_error_includes_sanitized_body(mocker):
    mock_post = mocker.patch("agents.publish.requests.post")
    resp = mocker.MagicMock()
    resp.raise_for_status.side_effect = Exception("400 Client Error")
    resp.text = '{"error":{"message":"bad token access_token=secret-token"}}'
    resp.json.return_value = {"error": {"message": "bad token access_token=secret-token", "type": "OAuthException", "code": 190, "error_subcode": 460}}
    mock_post.return_value = resp
    agent = PublishAgent(make_publish_config())
    job = make_article_job(dry_run=False)
    job.platforms = ["facebook"]
    job = agent.run(job)
    error = job.publish_result["facebook"]["error"]
    assert "body=" in error
    assert "access_token=<redacted>" in error
    assert "secret-token" not in error
    meta_error = job.publish_result["facebook"]["meta_error"]
    assert meta_error["code"] == 190
    assert meta_error["error_subcode"] == 460
    assert meta_error["type"] == "OAuthException"
    assert "access_token=<redacted>" in meta_error["message"]
    assert "secret-token" not in meta_error["body"]


def test_publish_ig_image_falls_back_to_public_image_url(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    img_file = tmp_path / "image.png"
    img_file.write_bytes(b"PNG")
    source_resp = mocker.MagicMock()
    source_resp.raise_for_status.side_effect = Exception("400 Client Error")
    source_resp.text = '{"error":{"message":"source upload rejected","code":100}}'
    source_resp.json.return_value = {"error": {"message": "source upload rejected", "code": 100}}
    fallback_resp = mocker.MagicMock()
    fallback_resp.raise_for_status = mocker.MagicMock()
    fallback_resp.json.return_value = {"id": "container-url"}
    publish_resp = mocker.MagicMock()
    publish_resp.raise_for_status = mocker.MagicMock()
    publish_resp.json.return_value = {"id": "ig-post-url"}
    mock_post = mocker.patch("agents.publish.requests.post", side_effect=[source_resp, fallback_resp, publish_resp])
    config = make_publish_config()
    config.public_base_url = "https://fleet.nayzfreedom.cloud"
    agent = PublishAgent(config)
    job = make_image_job(dry_run=False)
    job.id = "job-123"
    job.image_path = str(img_file)
    job.platforms = ["instagram"]

    job = agent.run(job)

    assert mock_post.call_count == 3
    fallback_data = mock_post.call_args_list[1].kwargs["data"]
    assert fallback_data["image_url"] == "https://fleet.nayzfreedom.cloud/media/public/job-123/image.png"
    assert job.publish_result["instagram"]["status"] == "published"
    assert job.publish_result["instagram"]["upload_mode"] == "image_url"


def test_publish_tiktok_image_skips_with_reason(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    img_file = tmp_path / "image.png"
    img_file.write_bytes(b"PNG")
    agent = PublishAgent(make_publish_config())
    job = make_image_job(dry_run=False)
    job.image_path = str(img_file)
    job.platforms = ["tiktok"]
    job = agent.run(job)
    assert job.publish_result["tiktok"]["status"] == "skipped"
    assert "public URL" in job.publish_result["tiktok"]["reason"]


def test_publish_tiktok_article_excluded_from_platforms(mocker):
    mock_post = mocker.patch("agents.publish.requests.post")
    mock_post.return_value.raise_for_status = mocker.MagicMock()
    mock_post.return_value.json.return_value = {"id": "fb-1"}
    agent = PublishAgent(make_publish_config())
    job = make_article_job(dry_run=False)
    job.platforms = ["facebook", "tiktok"]
    job = agent.run(job)
    assert "tiktok" not in job.publish_result
    assert job.publish_result["facebook"]["status"] == "published"
    assert mock_post.call_count == 1
    assert "page-123/feed" in mock_post.call_args[0][0]


def test_publish_tiktok_video_init_upload_publish(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vid_file = tmp_path / "video.mp4"
    vid_file.write_bytes(b"MP4DATA")
    mock_post = mocker.patch("agents.publish.requests.post")
    mock_put = mocker.patch("agents.publish.requests.put")
    init_resp = mocker.MagicMock()
    init_resp.raise_for_status = mocker.MagicMock()
    init_resp.json.return_value = {
        "data": {"publish_id": "pub-1", "upload_url": "https://upload.tiktok.com/v1/upload"}
    }
    status_resp = mocker.MagicMock()
    status_resp.raise_for_status = mocker.MagicMock()
    status_resp.json.return_value = {"data": {"status": "PUBLISH_COMPLETE"}}
    mock_post.side_effect = [init_resp, status_resp]
    mock_put.return_value.raise_for_status = mocker.MagicMock()
    agent = PublishAgent(make_publish_config())
    job = make_video_job(dry_run=False, video_path=str(vid_file))
    job.platforms = ["tiktok"]
    job = agent.run(job)
    assert mock_post.call_count == 2
    init_url = mock_post.call_args_list[0][0][0]
    assert "video/init" in init_url
    assert mock_put.called
    assert job.publish_result["tiktok"]["status"] == "published"
    assert job.publish_result["tiktok"]["publish_id"] == "pub-1"


def test_publish_tiktok_video_poll_timeout(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vid_file = tmp_path / "video.mp4"
    vid_file.write_bytes(b"MP4DATA")
    mock_post = mocker.patch("agents.publish.requests.post")
    mock_put = mocker.patch("agents.publish.requests.put")
    mocker.patch("agents.publish.time.sleep")
    init_resp = mocker.MagicMock()
    init_resp.raise_for_status = mocker.MagicMock()
    init_resp.json.return_value = {
        "data": {"publish_id": "pub-2", "upload_url": "https://upload.tiktok.com/v1/upload"}
    }
    status_resp = mocker.MagicMock()
    status_resp.raise_for_status = mocker.MagicMock()
    status_resp.json.return_value = {"data": {"status": "PROCESSING"}}
    mock_post.side_effect = [init_resp] + [status_resp] * 60
    mock_put.return_value.raise_for_status = mocker.MagicMock()
    agent = PublishAgent(make_publish_config())
    job = make_video_job(dry_run=False, video_path=str(vid_file))
    job.platforms = ["tiktok"]
    job = agent.run(job)
    assert job.publish_result["tiktok"]["status"] == "failed"
    assert "timed out" in job.publish_result["tiktok"]["error"]


def test_publish_tiktok_failure_does_not_affect_meta(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vid_file = tmp_path / "video.mp4"
    vid_file.write_bytes(b"MP4DATA")
    mock_post = mocker.patch("agents.publish.requests.post")
    mock_put = mocker.patch("agents.publish.requests.put")
    fb_resp = mocker.MagicMock()
    fb_resp.raise_for_status = mocker.MagicMock()
    fb_resp.json.return_value = {"id": "fb-vid-1"}
    init_resp = mocker.MagicMock()
    init_resp.raise_for_status = mocker.MagicMock()
    init_resp.json.return_value = {
        "data": {"publish_id": "pub-3", "upload_url": "https://upload.tiktok.com/v1/upload"}
    }
    status_resp = mocker.MagicMock()
    status_resp.raise_for_status = mocker.MagicMock()
    status_resp.json.return_value = {"data": {"status": "FAILED", "fail_reason": "QUOTA_EXCEEDED"}}
    mock_post.side_effect = [fb_resp, init_resp, status_resp]
    mock_put.return_value.raise_for_status = mocker.MagicMock()
    agent = PublishAgent(make_publish_config())
    job = make_video_job(dry_run=False, video_path=str(vid_file))
    job.platforms = ["facebook", "tiktok"]
    job = agent.run(job)
    assert job.publish_result["facebook"]["status"] == "published"
    assert job.publish_result["tiktok"]["status"] == "failed"
    assert "QUOTA_EXCEEDED" in job.publish_result["tiktok"]["error"]


def test_publish_youtube_image_skips_with_reason(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    img_file = tmp_path / "image.png"
    img_file.write_bytes(b"PNG")
    agent = PublishAgent(make_publish_config())
    job = make_image_job(dry_run=False)
    job.image_path = str(img_file)
    job.platforms = ["youtube"]
    job = agent.run(job)
    assert job.publish_result["youtube"]["status"] == "skipped"
    assert "YouTube only supports video uploads" in job.publish_result["youtube"]["reason"]


def test_publish_youtube_article_excluded_from_platforms(mocker):
    mock_post = mocker.patch("agents.publish.requests.post")
    mock_post.return_value.raise_for_status = mocker.MagicMock()
    mock_post.return_value.json.return_value = {"id": "fb-1"}
    agent = PublishAgent(make_publish_config())
    job = make_article_job(dry_run=False)
    job.platforms = ["facebook", "youtube"]
    job = agent.run(job)
    assert "youtube" not in job.publish_result
    assert job.publish_result["facebook"]["status"] == "published"
    assert mock_post.call_count == 1
    assert "page-123/feed" in mock_post.call_args_list[0][0][0]


def test_publish_youtube_video_upload(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vid_file = tmp_path / "video.mp4"
    vid_file.write_bytes(b"MP4DATA")
    mock_post = mocker.patch("agents.publish.requests.post")
    mock_put = mocker.patch("agents.publish.requests.put")
    auth_resp = mocker.MagicMock()
    auth_resp.raise_for_status = mocker.MagicMock()
    auth_resp.json.return_value = {"access_token": "yt-token"}
    init_resp = mocker.MagicMock()
    init_resp.raise_for_status = mocker.MagicMock()
    init_resp.headers = {"Location": "https://upload.googleapis.com/v1/upload"}
    mock_post.side_effect = [auth_resp, init_resp]
    mock_put.return_value.raise_for_status = mocker.MagicMock()
    mock_put.return_value.json.return_value = {"id": "yt-1", "status": {"uploadStatus": "uploaded"}}
    agent = PublishAgent(make_publish_config())
    job = make_video_job(dry_run=False, video_path=str(vid_file))
    job.platforms = ["youtube"]
    job = agent.run(job)
    assert mock_post.call_count == 2
    auth_url = mock_post.call_args_list[0][0][0]
    assert "oauth2.googleapis.com/token" in auth_url
    init_url = mock_post.call_args_list[1][0][0]
    assert "youtube/v3/videos" in init_url
    assert mock_put.called
    assert mock_put.call_args[1]["headers"]["Content-Type"] == "video/mp4"
    assert job.publish_result["youtube"]["status"] == "published"
    assert job.publish_result["youtube"]["id"] == "yt-1"


def test_publish_youtube_scheduled(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vid_file = tmp_path / "video.mp4"
    vid_file.write_bytes(b"MP4DATA")
    mock_post = mocker.patch("agents.publish.requests.post")
    mock_put = mocker.patch("agents.publish.requests.put")
    auth_resp = mocker.MagicMock()
    auth_resp.raise_for_status = mocker.MagicMock()
    auth_resp.json.return_value = {"access_token": "yt-token"}
    init_resp = mocker.MagicMock()
    init_resp.raise_for_status = mocker.MagicMock()
    init_resp.headers = {"Location": "https://upload.googleapis.com/v1/upload"}
    mock_post.side_effect = [auth_resp, init_resp]
    mock_put.return_value.raise_for_status = mocker.MagicMock()
    mock_put.return_value.json.return_value = {"id": "yt-2", "status": {"uploadStatus": "uploaded"}}
    agent = PublishAgent(make_publish_config())
    job = make_video_job(dry_run=False, video_path=str(vid_file))
    job.platforms = ["youtube"]
    job = agent.run(job, schedule=True)
    init_body = mock_post.call_args_list[1][1]["json"]
    assert init_body["status"]["privacyStatus"] == "private"
    assert "publishAt" in init_body["status"]
    assert job.publish_result["youtube"]["status"] == "scheduled"


def test_publish_youtube_failure_does_not_affect_meta(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vid_file = tmp_path / "video.mp4"
    vid_file.write_bytes(b"MP4DATA")
    mock_post = mocker.patch("agents.publish.requests.post")
    mock_put = mocker.patch("agents.publish.requests.put")
    fb_resp = mocker.MagicMock()
    fb_resp.raise_for_status = mocker.MagicMock()
    fb_resp.json.return_value = {"id": "fb-vid-1"}
    auth_resp = mocker.MagicMock()
    auth_resp.raise_for_status = mocker.MagicMock()
    auth_resp.json.return_value = {"access_token": "yt-token"}
    init_resp = mocker.MagicMock()
    init_resp.raise_for_status.side_effect = Exception("QUOTA_EXCEEDED")
    mock_post.side_effect = [fb_resp, auth_resp, init_resp]
    mock_put.return_value.raise_for_status = mocker.MagicMock()
    agent = PublishAgent(make_publish_config())
    job = make_video_job(dry_run=False, video_path=str(vid_file))
    job.platforms = ["facebook", "youtube"]
    job = agent.run(job)
    assert job.publish_result["facebook"]["status"] == "published"
    assert job.publish_result["youtube"]["status"] == "failed"
    assert "QUOTA_EXCEEDED" in job.publish_result["youtube"]["error"]
