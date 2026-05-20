from pathlib import Path
import shutil

from models.content_job import CheckpointDecision, ContentJob, ContentType, JobStatus
from orchestrator import Orchestrator
from project_loader import load_project
from tests.test_mia import make_config


def test_full_dry_run_pipeline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    shutil.copytree(Path(__file__).parent.parent / "projects", tmp_path / "projects")

    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave")
    monkeypatch.setenv("OPENAI_API_KEY", "oai")
    monkeypatch.setattr(
        "orchestrator.pause",
        lambda *args, **kwargs: CheckpointDecision(
            stage=args[0],
            decision="approved",
        ),
    )

    pm = load_project("nayzfreedom_fleet")
    job = ContentJob(
        project="nayzfreedom_fleet",
        pm=pm,
        brief="lipstick that lasts all day",
        platforms=["instagram", "facebook"],
        dry_run=True,
        content_type=ContentType.VIDEO,
    )
    orch = Orchestrator(make_config())
    result = orch.run(job, unattended=True)

    assert result.status == JobStatus.COMPLETED
    assert result.bella_output is not None
    assert result.qa_result is not None and result.qa_result.passed
    assert result.growth_strategy is not None
    assert result.community_faq_path is not None
    assert len(result.checkpoint_log) == 3

    job_file = tmp_path / "output" / "Slayhack" / result.id / "job.json"
    assert job_file.exists()

    faq_file = Path(result.community_faq_path)
    assert faq_file.exists()