from __future__ import annotations
from job_store import find_job, load_job, load_recent_performance, save_job
from models.content_job import (
    ContentJob, PMProfile, BrandProfile, VisualIdentity, PostPerformance
)


def make_pm():
    brand = BrandProfile(
        mission="m", visual=VisualIdentity(colors=[], style=""), platforms=[],
        tone="", target_audience="", script_style="", nora_max_retries=2,
    )
    return PMProfile(name="Test", page_name="Test", persona="", brand=brand)


def make_job():
    return ContentJob(project="test", pm=make_pm(), brief="b", platforms=["instagram"])


def test_load_recent_performance_no_output_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_recent_performance("Test") == ""


def test_load_recent_performance_no_performance_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    job = make_job()
    save_job(job)
    assert load_recent_performance("Test") == ""


def test_load_recent_performance_with_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    job = make_job()
    job.performance = [PostPerformance(platform="instagram", likes=100, reach=5000, saves=20)]
    save_job(job)
    result = load_recent_performance("Test")
    assert "likes=100" in result
    assert "reach=5000" in result
    assert "instagram" in result


def test_load_recent_performance_respects_limit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Create 7 job.json files with distinct IDs manually (ContentJob ID is second-granularity)
    for i in range(7):
        job = make_job()
        job.id = f"2026050{i}_120000"
        job.performance = [PostPerformance(platform="instagram", likes=i)]
        out_dir = tmp_path / "output" / "Test" / job.id
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "job.json").write_text(job.model_dump_json())
    result = load_recent_performance("Test", limit=3)
    # Should contain at most 3 jobs worth of data
    assert result.count("instagram") == 3


def test_load_job_normalizes_legacy_project_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project_dir = tmp_path / "projects" / "slay_hack"
    project_dir.mkdir(parents=True)
    (project_dir / "pm_profile.yaml").write_text('page_name: "Slay Hack"\n')
    job = make_job()
    job.id = "20260512_060000"
    job.project = "nayzfreedom_fleet"
    job.pm.page_name = "Slayhack"
    out_dir = tmp_path / "output" / "Slay Hack" / job.id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "job.json").write_text(job.model_dump_json())

    loaded = load_job(job.id, "Slay Hack")
    found = find_job(job.id)

    assert loaded.project == "nayzfreedom_fleet"
    assert loaded.pm.page_name == "Slay Hack"
    assert found.project == "nayzfreedom_fleet"
    assert found.pm.page_name == "Slay Hack"
