import sys
from unittest.mock import patch, MagicMock
from checkpoint import pause, CheckpointResult
from models.content_job import ContentJob, PMProfile, BrandProfile, VisualIdentity, ContentType


def make_job():
    brand = BrandProfile(
        mission="m", visual=VisualIdentity(colors=[], style=""), platforms=[],
        tone="", target_audience="", script_style="", nora_max_retries=2,
    )
    pm = PMProfile(name="Test", page_name="Test Page", persona="", brand=brand)
    return ContentJob(project="test", pm=pm, brief="b", platforms=[])


def test_pause_approve(capsys):
    with patch("builtins.input", return_value="y"):
        result = pause("qa_review", "Script looks good.", [], make_job())
    assert result.decision == "y"
    assert result.stage == "qa_review"


def test_pause_records_to_checkpoint_log():
    job = make_job()
    with patch("builtins.input", return_value="skip"):
        result = pause("ideation", "Pick an idea.", ["1", "2", "3"], job)
    assert len(job.checkpoint_log) == 1
    assert job.checkpoint_log[0].stage == "ideation"
    assert job.checkpoint_log[0].decision == "skip"


def test_pause_unattended_idea_selection_returns_1():
    job = make_job()
    result = pause("idea_selection", "Pick an idea.", ["Idea A", "Idea B"], job, unattended=True)
    assert result.decision == "1"
    assert result.stage == "idea_selection"
    assert len(job.checkpoint_log) == 1
    assert job.checkpoint_log[0].decision == "1"


def test_pause_unattended_idea_selection_uses_first_option_number():
    job = make_job()
    result = pause("idea_selection", "Pick an idea.", ["3: Article idea", "5: Other"], job, unattended=True)
    assert result.decision == "3"


def test_pause_unattended_other_stages_returns_approved():
    job = make_job()
    for stage in ("content_review", "qa_review", "final_approval"):
        job.checkpoint_log.clear()
        result = pause(stage, "summary", [], job, unattended=True)
        assert result.decision == "approved"
        assert result.stage == stage


def test_pause_unattended_unknown_stage_returns_approved():
    job = make_job()
    result = pause("some_future_stage", "summary", [], job, unattended=True)
    assert result.decision == "approved"


def test_pause_unattended_does_not_call_input(monkeypatch):
    called = []
    monkeypatch.setattr("builtins.input", lambda _: called.append(1) or "x")
    job = make_job()
    pause("qa_review", "summary", [], job, unattended=True)
    assert called == []


def test_main_content_type_flag_sets_job_content_type(mocker, tmp_path, monkeypatch):
    import main as main_module
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main_module, "_LOCK_FILE", tmp_path / "pipeline.lock")
    returned_job = make_job()
    returned_job.status = __import__('models.content_job', fromlist=['JobStatus']).JobStatus.COMPLETED
    mock_orch = mocker.patch.object(main_module.Orchestrator, "run", return_value=returned_job)
    mocker.patch.object(main_module.Config, "from_env", return_value=mocker.MagicMock())
    mocker.patch("main.load_project", return_value=make_job().pm)
    sys.argv = ["main.py", "--project", "nayzfreedom_fleet", "--brief", "test brief", "--content-type", "article"]
    try:
        main_module.main()
    except SystemExit:
        pass
    assert mock_orch.called
    job_arg = mock_orch.call_args[0][0]
    assert job_arg.content_type == ContentType.ARTICLE


def test_main_unattended_flag_passed_to_orchestrator(mocker, tmp_path, monkeypatch):
    import main as main_module
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main_module, "_LOCK_FILE", tmp_path / "pipeline.lock")
    returned_job = make_job()
    returned_job.status = __import__('models.content_job', fromlist=['JobStatus']).JobStatus.COMPLETED
    mock_run = mocker.patch.object(main_module.Orchestrator, "run", return_value=returned_job)
    mocker.patch.object(main_module.Config, "from_env", return_value=mocker.MagicMock())
    mocker.patch("main.load_project", return_value=make_job().pm)
    sys.argv = ["main.py", "--project", "nayzfreedom_fleet", "--brief", "test brief", "--unattended"]
    try:
        main_module.main()
    except SystemExit:
        pass
    assert mock_run.called
    _, kwargs = mock_run.call_args
    assert kwargs.get("unattended") is True


def test_main_safe_prep_flag_passed_to_orchestrator(mocker, tmp_path, monkeypatch):
    import main as main_module
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main_module, "_LOCK_FILE", tmp_path / "pipeline.lock")
    returned_job = make_job()
    returned_job.status = __import__('models.content_job', fromlist=['JobStatus']).JobStatus.COMPLETED
    mock_orchestrator = mocker.patch("main.Orchestrator")
    mock_orchestrator.return_value.run.return_value = returned_job
    mocker.patch.object(main_module.Config, "from_env", return_value=mocker.MagicMock())
    mocker.patch("main.load_project", return_value=make_job().pm)
    sys.argv = ["main.py", "--project", "nayzfreedom_fleet", "--brief", "test brief", "--safe-prep"]
    try:
        main_module.main()
    except SystemExit:
        pass
    assert mock_orchestrator.call_args.kwargs["safe_prep"] is True


def test_main_marks_job_failed_when_orchestrator_raises(mocker, tmp_path, monkeypatch):
    import pytest
    import main as main_module
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main_module, "_LOCK_FILE", tmp_path / "pipeline.lock")
    mocker.patch.object(main_module.Config, "from_env", return_value=mocker.MagicMock())
    mocker.patch("main.load_project", return_value=make_job().pm)
    mocker.patch.object(main_module.Orchestrator, "run", side_effect=RuntimeError("quota exhausted"))
    mock_save = mocker.patch("main.save_job")
    sys.argv = ["main.py", "--project", "nayzfreedom_fleet", "--brief", "test brief", "--unattended"]

    with pytest.raises(RuntimeError, match="quota exhausted"):
        main_module.main()

    saved_job = mock_save.call_args_list[-1].args[0]
    assert saved_job.status == __import__('models.content_job', fromlist=['JobStatus']).JobStatus.FAILED
    assert not (tmp_path / "pipeline.lock").exists()



def test_pause_uses_telegram_when_env_set(monkeypatch):
    import checkpoint as cp
    monkeypatch.setattr(cp, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(cp, "TELEGRAM_CHAT_ID", "123456")
    monkeypatch.setattr(cp, "TELEGRAM_TIMEOUT_MINUTES", 30)

    mock_send = MagicMock(return_value="approved")
    monkeypatch.setattr(cp.telegram_checkpoint, "send_and_wait", mock_send)

    job = make_job()
    result = cp.pause("content_review", "Script ok.", ["approved", "rejected"], job)

    mock_send.assert_called_once_with(
        stage="content_review",
        summary="Script ok.",
        options=["approved", "rejected"],
        token="test-token",
        chat_id="123456",
        timeout_seconds=1800,
        fallback="approved",
    )
    assert result.decision == "approved"
    assert result.stage == "content_review"


def test_pause_falls_back_to_input_when_no_token(monkeypatch):
    import checkpoint as cp
    monkeypatch.setattr(cp, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(cp, "TELEGRAM_CHAT_ID", "")

    with patch("builtins.input", return_value="1"):
        result = cp.pause("idea_selection", "Pick an idea.", ["Idea A", "Idea B"], make_job())

    assert result.decision == "1"


def test_pause_skips_telegram_when_unattended(monkeypatch):
    import checkpoint as cp
    monkeypatch.setattr(cp, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(cp, "TELEGRAM_CHAT_ID", "123456")

    mock_send = MagicMock()
    monkeypatch.setattr(cp.telegram_checkpoint, "send_and_wait", mock_send)

    result = cp.pause("qa_review", "summary", [], make_job(), unattended=True)

    mock_send.assert_not_called()
    assert result.decision == "approved"
