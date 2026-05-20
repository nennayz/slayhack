from agents.nora import NoraAgent
from tests.test_lila import make_job_with_bella_output
from tests.test_mia import make_config
from models.content_job import ContentType, Article


def make_job_for_nora(dry_run=True, video_path=None):
    job = make_job_with_bella_output(dry_run=dry_run)
    job.visual_prompt = "Gold lipstick, ivory background"
    job.image_path = "assets/placeholder.png"
    if video_path is not None:
        job.video_path = video_path
    return job


def test_nora_dry_run_passes():
    agent = NoraAgent(make_config())
    job = agent.run(make_job_for_nora(dry_run=True))
    assert job.qa_result is not None
    assert job.qa_result.passed is True
    assert job.stage == "nora_done"


def test_nora_live_fail_increments_retry(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"FAKE")
    qa_json = '{"passed":false,"script_feedback":"Hook too weak","visual_feedback":null,"send_back_to":"bella"}'
    mocker.patch.object(NoraAgent, "_call_claude", return_value=qa_json)
    agent = NoraAgent(make_config())
    job = make_job_for_nora(dry_run=False, video_path=str(video_file))
    job = agent.run(job)
    assert job.qa_result.passed is False
    assert job.qa_result.send_back_to == "bella"
    assert job.nora_retry_count == 1


def test_nora_live_pass(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"FAKE")
    qa_json = '{"passed":true,"script_feedback":null,"visual_feedback":null,"send_back_to":null}'
    mocker.patch.object(NoraAgent, "_call_claude", return_value=qa_json)
    agent = NoraAgent(make_config())
    job = make_job_for_nora(dry_run=False, video_path=str(video_file))
    job = agent.run(job)
    assert job.qa_result.passed is True
    assert job.nora_retry_count == 0


def make_article_job_for_nora(dry_run=True):
    from tests.test_bella import make_job_with_idea
    job = make_job_with_idea(dry_run=dry_run, content_type=ContentType.ARTICLE)
    job.bella_output = Article(heading="The Look", body="Step 1...", cta="Shop now")
    return job


def test_nora_live_article_skips_visual_qa(mocker):
    captured = {}
    def fake_call(system, user, **kwargs):
        captured["user"] = user
        return '{"passed":true,"script_feedback":null,"visual_feedback":null,"send_back_to":null}'
    agent = NoraAgent(make_config())
    mocker.patch.object(agent, "_call_claude", side_effect=fake_call)
    job = make_article_job_for_nora(dry_run=False)
    agent.run(job)
    assert "visual prompt:" not in captured["user"].lower()
    assert "The Look" in captured["user"]


def test_nora_live_video_includes_visual_in_prompt(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"FAKE")
    captured = {}
    def fake_call(system, user, **kwargs):
        captured["user"] = user
        return '{"passed":true,"script_feedback":null,"visual_feedback":null,"send_back_to":null}'
    agent = NoraAgent(make_config())
    mocker.patch.object(agent, "_call_claude", side_effect=fake_call)
    job = make_job_for_nora(dry_run=False, video_path=str(video_file))
    agent.run(job)
    assert "Script hook:" in captured["user"]
    assert "Gold lipstick, ivory background" in captured["user"]


def test_nora_video_qa_fails_if_no_video_path(mocker):
    mock_call = mocker.patch.object(NoraAgent, "_call_claude")
    agent = NoraAgent(make_config())
    job = make_job_for_nora(dry_run=False)  # video_path=None
    job = agent.run(job)
    mock_call.assert_not_called()
    assert job.qa_result.passed is False
    assert job.qa_result.script_feedback == "Video not generated"
    assert job.nora_retry_count == 1


def test_nora_video_qa_fails_if_video_file_missing(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_call = mocker.patch.object(NoraAgent, "_call_claude")
    agent = NoraAgent(make_config())
    job = make_job_for_nora(dry_run=False, video_path=str(tmp_path / "nonexistent.mp4"))
    job = agent.run(job)
    mock_call.assert_not_called()
    assert job.qa_result.passed is False
    assert job.qa_result.script_feedback == "Video file missing or empty"
    assert job.nora_retry_count == 1


def test_nora_video_qa_send_back_to_never_lila(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"FAKE")
    qa_json = '{"passed":false,"script_feedback":"Off-brand","visual_feedback":null,"send_back_to":"lila"}'
    mocker.patch.object(NoraAgent, "_call_claude", return_value=qa_json)
    agent = NoraAgent(make_config())
    job = make_job_for_nora(dry_run=False, video_path=str(video_file))
    job = agent.run(job)
    assert job.qa_result.send_back_to is None
