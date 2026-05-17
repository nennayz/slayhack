import json
from unittest.mock import MagicMock, patch
from orchestrator import Orchestrator
from tests.test_mia import make_config, make_job
from models.content_job import ContentType, Idea, JobStatus


def _make_tool_use_block(name, tool_id="t1", input_data=None):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.id = tool_id
    block.input = input_data or {}
    return block


def _make_end_turn_response():
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [MagicMock(type="text", text="All done!")]
    return resp


def test_orchestrator_dry_run_completes(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    # Robin calls agents in sequence then end_turn
    tool_sequence = [
        [_make_tool_use_block("run_mia", "t1")],
        [_make_tool_use_block("run_zoe", "t2")],
        [_make_tool_use_block("request_checkpoint", "t3",
            {"stage": "idea_selection", "summary": "Pick an idea", "options": ["1. Lip Hack"]})],
        [_make_tool_use_block("run_bella", "t4")],
        [_make_tool_use_block("run_lila", "t5")],
        [_make_tool_use_block("request_checkpoint", "t6",
            {"stage": "content_review", "summary": "Review script"})],
        [_make_tool_use_block("run_nora", "t7")],
        [_make_tool_use_block("request_checkpoint", "t8",
            {"stage": "qa_review", "summary": "QA passed"})],
        [_make_tool_use_block("run_roxy", "t9")],
        [_make_tool_use_block("run_emma", "t10")],
        [_make_tool_use_block("request_checkpoint", "t11",
            {"stage": "final_approval", "summary": "Ready to publish?"})],
    ]

    call_count = [0]
    def mock_create(**kwargs):
        i = call_count[0]
        call_count[0] += 1
        if i < len(tool_sequence):
            resp = MagicMock()
            resp.stop_reason = "tool_use"
            resp.content = tool_sequence[i]
            return resp
        return _make_end_turn_response()

    mocker.patch("orchestrator.anthropic.Anthropic").return_value.messages.create.side_effect = mock_create
    mocker.patch("builtins.input", return_value="1")

    orch = Orchestrator(make_config())
    job = make_job(dry_run=True)
    result = orch.run(job)

    assert result.status == JobStatus.COMPLETED
    assert result.trend_data is not None
    assert result.ideas is not None
    assert result.bella_output is not None
    assert len(result.checkpoint_log) == 4


def test_orchestrator_sets_content_type_at_idea_selection(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    orch = Orchestrator(make_config())
    job = make_job(dry_run=True)
    job.ideas = [
        Idea(number=1, title="Lip Hack", hook="h", angle="Tutorial", content_type=ContentType.VIDEO),
        Idea(number=2, title="Morning Routine", hook="h2", angle="Lifestyle", content_type=ContentType.ARTICLE),
    ]

    mock_checkpoint = MagicMock()
    mock_checkpoint.decision = "2"
    mocker.patch("orchestrator.pause", return_value=mock_checkpoint)

    orch._dispatch(
        "request_checkpoint",
        {"stage": "idea_selection", "summary": "pick one", "options": ["1", "2"]},
        job,
    )

    assert job.content_type == ContentType.ARTICLE
    assert job.selected_idea.number == 2


def test_orchestrator_unattended_selects_matching_content_type(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    orch = Orchestrator(make_config())
    orch._unattended = True
    job = make_job(dry_run=True)
    job.content_type = ContentType.ARTICLE
    job.ideas = [
        Idea(number=1, title="Video idea", hook="h", angle="Tutorial", content_type=ContentType.VIDEO),
        Idea(number=2, title="Article idea", hook="h2", angle="Editorial", content_type=ContentType.ARTICLE),
    ]

    orch._dispatch(
        "request_checkpoint",
        {"stage": "idea_selection", "summary": "pick one", "options": []},
        job,
    )

    assert job.selected_idea.number == 2
    assert job.content_type == ContentType.ARTICLE


def test_orchestrator_raises_on_unexpected_stop_reason(mocker, tmp_path, monkeypatch):
    import pytest
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    resp = MagicMock()
    resp.stop_reason = "max_tokens"
    resp.content = []
    mocker.patch("orchestrator.anthropic.Anthropic").return_value.messages.create.return_value = resp

    orch = Orchestrator(make_config())
    job = make_job(dry_run=True)
    with pytest.raises(RuntimeError, match="max_tokens"):
        orch.run(job)
    assert job.status == JobStatus.FAILED


def test_orchestrator_marks_publish_failures_failed(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    mocker.patch("orchestrator.anthropic.Anthropic").return_value.messages.create.return_value = _make_end_turn_response()
    orch = Orchestrator(make_config())
    job = make_job(dry_run=True)
    job.publish_result = {"facebook": {"status": "failed", "error": "blocked"}}
    result = orch.run(job)

    assert result.status == JobStatus.FAILED


def test_orchestrator_safe_prep_end_turn_without_handoff_awaits_approval(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    mocker.patch("orchestrator.anthropic.Anthropic").return_value.messages.create.return_value = _make_end_turn_response()
    orch = Orchestrator(make_config(), safe_prep=True)
    job = make_job(dry_run=False)
    job.stage = "zoe_done"

    result = orch.run(job, unattended=True)

    assert result.status == JobStatus.AWAITING_APPROVAL
    assert result.stage == "zoe_done"


def test_orchestrator_safe_prep_intercepts_publish(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    orch = Orchestrator(make_config(), safe_prep=True)
    job = make_job(dry_run=False)
    job.growth_strategy = __import__(
        "models.content_job", fromlist=["GrowthStrategy"]
    ).GrowthStrategy(
        hashtags=["#test"],
        caption="Safe caption",
        best_post_time_utc="12:00",
        best_post_time_thai="19:00",
    )
    publish_agent = MagicMock()
    orch.agents["publish"] = publish_agent

    result = orch._dispatch("run_publish", {"schedule": True}, job)

    publish_agent.run.assert_not_called()
    assert result == {"status": "safe_prep", "stage": "ready_to_publish"}
    assert job.stage == "ready_to_publish"
    assert job.publish_package["status"] == "completed"
    assert job.publish_execution["status"] == "ready_to_publish"
    assert job.publish_result["instagram"]["status"] == "ready_to_publish"
    assert job.publish_result["instagram"]["dry_run"] is True
