from __future__ import annotations
from unittest.mock import MagicMock, patch
from config import Config
from models.niche_opportunity import NicheOpportunity, ScoutJob, ScoutJobStatus


def _make_config() -> Config:
    return Config(brave_search_api_key="x", openai_api_key="test-openai")


def _make_opportunities() -> list[NicheOpportunity]:
    return [
        NicheOpportunity(
            niche_name="clean beauty", target_audience="Women USA 22-38",
            platforms=["instagram"], reach_score=91.0, trend_direction="rising",
            content_formats=["reel"], monetization_notes="High affiliate", signals={},
        )
    ]


def test_run_dry_scout_pipeline_returns_scout_job():
    from scout_pipeline import run_scout_pipeline
    job = run_scout_pipeline(_make_config(), triggered_by="test", dry_run=True)
    assert isinstance(job, ScoutJob)
    assert job.status == ScoutJobStatus.AWAITING_APPROVAL
    assert len(job.opportunities) >= 1


def test_run_scout_pipeline_saves_report(tmp_path):
    from scout_pipeline import run_scout_pipeline
    run_scout_pipeline(_make_config(), triggered_by="test", dry_run=True, output_root=tmp_path)
    reports = list((tmp_path / "scout_reports").glob("*.json"))
    assert len(reports) == 1


@patch("scout_pipeline.ArchitectAgent")
def test_approve_niche_creates_project(mock_arch_cls, tmp_path):
    from scout_pipeline import approve_niche
    mock_arch = MagicMock()
    mock_arch.run.return_value = "clean_beauty"
    mock_arch_cls.return_value = mock_arch

    job = ScoutJob(job_id="test_pipe_001", triggered_by="test")
    job.opportunities = _make_opportunities()

    slug = approve_niche(job, "clean beauty", _make_config(), projects_root=tmp_path)
    assert slug == "clean_beauty"
    assert job.approved_niche == "clean beauty"
    mock_arch.run.assert_called_once()
    assert job.status == ScoutJobStatus.COMPLETED
