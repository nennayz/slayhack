from __future__ import annotations
from pathlib import Path
import yaml
from config import Config
from models.niche_opportunity import NicheOpportunity, ScoutJob, ScoutJobStatus


def _make_config() -> Config:
    return Config(brave_search_api_key="x", openai_api_key="test-openai")


def _make_approved_job(tmp_path: Path) -> tuple[ScoutJob, NicheOpportunity]:
    opp = NicheOpportunity(
        niche_name="clean beauty",
        target_audience="Women USA 22-38",
        platforms=["instagram", "tiktok"],
        reach_score=91.0,
        trend_direction="rising",
        content_formats=["reel", "infographic"],
        monetization_notes="High affiliate potential",
        signals={},
    )
    job = ScoutJob(job_id="test_arch_001", triggered_by="test")
    job.approved_niche = "clean beauty"
    job.opportunities = [opp]
    return job, opp


def test_architect_dry_run_returns_slug(tmp_path):
    from agents.architect import ArchitectAgent
    agent = ArchitectAgent(_make_config())
    job, _ = _make_approved_job(tmp_path)
    slug = agent.run(job, projects_root=tmp_path, dry_run=True)
    assert slug == "clean_beauty"


def test_architect_dry_run_does_not_write_files(tmp_path):
    from agents.architect import ArchitectAgent
    agent = ArchitectAgent(_make_config())
    job, _ = _make_approved_job(tmp_path)
    agent.run(job, projects_root=tmp_path, dry_run=True)
    assert not (tmp_path / "clean_beauty").exists()


def test_architect_live_creates_project_files(tmp_path):
    from agents.architect import ArchitectAgent
    agent = ArchitectAgent(_make_config())
    job, _ = _make_approved_job(tmp_path)
    slug = agent.run(job, projects_root=tmp_path, dry_run=False)
    project_dir = tmp_path / slug
    assert project_dir.exists()
    for fname in [
        "brand.yaml",
        "pm_profile.yaml",
        "platform_specs.yaml",
        "weekly_calendar.yaml",
        "scout_activation.yaml",
    ]:
        assert (project_dir / fname).exists(), f"Missing {fname}"


def test_architect_brand_yaml_has_required_keys(tmp_path):
    from agents.architect import ArchitectAgent
    agent = ArchitectAgent(_make_config())
    job, _ = _make_approved_job(tmp_path)
    slug = agent.run(job, projects_root=tmp_path, dry_run=False)
    brand = yaml.safe_load((tmp_path / slug / "brand.yaml").read_text())
    assert "mission" in brand
    assert "target_audience" in brand
    assert "platforms" in brand


def test_architect_normalizes_content_formats_for_runtime(tmp_path):
    from agents.architect import ArchitectAgent
    agent = ArchitectAgent(_make_config())
    job, opp = _make_approved_job(tmp_path)
    opp.content_formats = ["short video", "reel", "listicle", "infographic"]
    slug = agent.run(job, projects_root=tmp_path, dry_run=False)

    project_dir = tmp_path / slug
    brand = yaml.safe_load((project_dir / "brand.yaml").read_text())
    specs = yaml.safe_load((project_dir / "platform_specs.yaml").read_text())
    calendar = yaml.safe_load((project_dir / "weekly_calendar.yaml").read_text())

    assert brand["allowed_content_types"] == ["video", "article", "infographic"]
    assert specs["instagram"]["content_types"] == ["video", "article", "infographic"]
    assert calendar["monday"]["short_video_1"] == "clean beauty hack"
    assert calendar["wednesday"]["article_1"] == "clean beauty story"
    assert calendar["sunday"]["infographic_1"] == "clean beauty tips"


def test_architect_marks_scout_project_pending_rotation(tmp_path):
    from agents.architect import ArchitectAgent
    agent = ArchitectAgent(_make_config())
    job, _ = _make_approved_job(tmp_path)
    slug = agent.run(job, projects_root=tmp_path, dry_run=False)

    activation = yaml.safe_load((tmp_path / slug / "scout_activation.yaml").read_text())

    assert activation["source"] == "scout"
    assert activation["source_report"] == job.job_id
    assert activation["niche_name"] == "clean beauty"
    assert activation["status"] == "captain_review"
    assert activation["scheduler_rotation_approved"] is False
