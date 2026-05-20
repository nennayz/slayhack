from __future__ import annotations
import yaml
from models.trend_scan_job import TrendHit, TrendScanJob, TrendScanJobStatus


def test_trend_hit_fields():
    hit = TrendHit(topic="beauty hacks", direction="rising", score=82.0, sources={"source": "dry-run"})
    assert hit.topic == "beauty hacks"
    assert hit.score == 82.0


def test_trend_scan_job_defaults():
    job = TrendScanJob(job_id="20260519_060000", page_slug="nayzfreedom_fleet", triggered_by="test")
    assert job.status == TrendScanJobStatus.PENDING
    assert job.signals_found == 0
    assert job.signals_stored == 0
    assert job.signals_skipped == 0


def test_load_scout_seed_topics_reads_yaml(tmp_path):
    from project_loader import load_scout_seed_topics
    proj_dir = tmp_path / "projects" / "test_page"
    proj_dir.mkdir(parents=True)
    brand = {"mission": "test", "scout_seed_topics": ["beauty hacks", "skincare"]}
    (proj_dir / "brand.yaml").write_text(yaml.dump(brand))
    topics = load_scout_seed_topics("test_page", root=tmp_path)
    assert topics == ["beauty hacks", "skincare"]


def test_load_scout_seed_topics_missing_field(tmp_path):
    from project_loader import load_scout_seed_topics
    proj_dir = tmp_path / "projects" / "test_page"
    proj_dir.mkdir(parents=True)
    (proj_dir / "brand.yaml").write_text(yaml.dump({"mission": "test"}))
    assert load_scout_seed_topics("test_page", root=tmp_path) == []


def test_load_scout_seed_topics_missing_file(tmp_path):
    from project_loader import load_scout_seed_topics
    assert load_scout_seed_topics("no_such_page", root=tmp_path) == []
