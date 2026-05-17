from unittest.mock import MagicMock, patch
from pathlib import Path
import json
import shutil
from orchestrator import Orchestrator
from project_loader import load_project
from models.content_job import ContentJob, JobStatus
from config import Config
from tests.test_mia import make_config


def _tool_block(name, tool_id, input_data=None):
    b = MagicMock()
    b.name = name
    b.id = tool_id
    b.input = input_data or {}
    return b


def _tool_call_response(blocks):
    calls = []
    for block in blocks:
        call = MagicMock()
        call.id = block.id
        call.function.name = block.name
        call.function.arguments = json.dumps(block.input)
        calls.append(call)
    message = MagicMock()
    message.content = ""
    message.tool_calls = calls
    resp = MagicMock()
    resp.choices = [MagicMock(finish_reason="tool_calls", message=message)]
    return resp


def _end_turn_response():
    message = MagicMock()
    message.content = "Job complete!"
    message.tool_calls = None
    resp = MagicMock()
    resp.choices = [MagicMock(finish_reason="stop", message=message)]
    return resp


def test_full_dry_run_pipeline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    # Copy projects/ into tmp_path so project_loader can find it
    shutil.copytree(Path(__file__).parent.parent / "projects", tmp_path / "projects")

    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave")
    monkeypatch.setenv("OPENAI_API_KEY", "oai")

    sequence = [
        [_tool_block("run_mia", "t1")],
        [_tool_block("run_zoe", "t2")],
        [_tool_block("request_checkpoint", "t3", {"stage": "idea_selection",
            "summary": "Ideas:\n1. Lip Hack\n2. Morning Routine", "options": ["1", "2", "3", "4", "5"]})],
        [_tool_block("run_bella", "t4")],
        [_tool_block("run_lila", "t5")],
        [_tool_block("request_checkpoint", "t6", {"stage": "content_review",
            "summary": "Script and visual ready for review."})],
        [_tool_block("run_nora", "t7")],
        [_tool_block("request_checkpoint", "t8", {"stage": "qa_review",
            "summary": "Nora says: PASSED ✓"})],
        [_tool_block("run_roxy", "t9")],
        [_tool_block("run_emma", "t10")],
        [_tool_block("request_checkpoint", "t11", {"stage": "final_approval",
            "summary": "Everything ready. Post to Instagram + Facebook?"})],
    ]

    call_count = [0]
    def mock_create(**kwargs):
        i = call_count[0]
        call_count[0] += 1
        if i < len(sequence):
            return _tool_call_response(sequence[i])
        return _end_turn_response()

    with patch("orchestrator.OpenAI") as mock_openai, \
         patch("builtins.input", return_value="1"):
        mock_openai.return_value.chat.completions.create.side_effect = mock_create

        pm = load_project("nayzfreedom_fleet")
        job = ContentJob(
            project="nayzfreedom_fleet", pm=pm,
            brief="lipstick that lasts all day",
            platforms=["instagram", "facebook"],
            dry_run=True,
        )
        orch = Orchestrator(make_config())
        result = orch.run(job)

    assert result.status == JobStatus.COMPLETED
    assert result.trend_data is not None
    assert result.ideas is not None and len(result.ideas) >= 3
    assert result.bella_output is not None
    assert result.qa_result is not None and result.qa_result.passed
    assert result.growth_strategy is not None
    assert result.community_faq_path is not None
    assert len(result.checkpoint_log) == 4

    job_file = tmp_path / "output" / "Slayhack" / result.id / "job.json"
    assert job_file.exists()

    faq_file = Path(result.community_faq_path)
    assert faq_file.exists()
