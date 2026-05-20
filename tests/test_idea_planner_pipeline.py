from __future__ import annotations

from datetime import datetime

import pytest

from knowledge.embedder import Embedder
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore
from models.idea_plan_job import IdeaPlanJobStatus


@pytest.fixture
def store(tmp_path):
    settings = KnowledgeSettings(root=tmp_path)
    embedder = Embedder("test", embed_fn=lambda texts: [[0.0] * 4 for _ in texts])
    return KnowledgeStore(settings, embedder)


@pytest.fixture
def config():
    from unittest.mock import MagicMock

    cfg = MagicMock()
    cfg.openai_api_key = ""
    cfg.openai_agent_model = "gpt-4o-mini"
    return cfg


def test_dry_run_stores_seven_ideas(store, config, tmp_path):
    from idea_planner_pipeline import run_idea_planner_pipeline

    job = run_idea_planner_pipeline(
        "nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path
    )
    assert job.status == IdeaPlanJobStatus.COMPLETED
    assert job.ideas_generated == 7
    assert job.ideas_stored == 7
    assert job.ideas_skipped == 0


def test_stored_ideas_have_correct_kind(store, config, tmp_path):
    from idea_planner_pipeline import run_idea_planner_pipeline

    run_idea_planner_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    ideas = store.recent(kind="idea", page="nayzfreedom_fleet")
    assert len(ideas) == 7
    assert all(obj.kind == "idea" for obj in ideas)


def test_stored_ideas_have_status_new(store, config, tmp_path):
    from idea_planner_pipeline import run_idea_planner_pipeline

    run_idea_planner_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    ideas = store.recent(kind="idea", page="nayzfreedom_fleet")
    assert all(obj.status == "new" for obj in ideas)


def test_dedup_idempotency(store, config, tmp_path):
    from idea_planner_pipeline import run_idea_planner_pipeline

    run_idea_planner_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    job2 = run_idea_planner_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    assert job2.ideas_stored == 0
    assert job2.ideas_skipped == 7


def test_digest_file_created(store, config, tmp_path):
    from idea_planner_pipeline import run_idea_planner_pipeline

    date_str = datetime.now().strftime("%Y%m%d")
    run_idea_planner_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    digest = tmp_path / "nayzfreedom_fleet" / "ideas" / date_str / "idea_digest.md"
    assert digest.exists()


def test_digest_contains_all_titles(store, config, tmp_path):
    from idea_planner_pipeline import run_idea_planner_pipeline

    date_str = datetime.now().strftime("%Y%m%d")
    run_idea_planner_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    digest = tmp_path / "nayzfreedom_fleet" / "ideas" / date_str / "idea_digest.md"
    content = digest.read_text()
    assert "Invisible Lip Liner Hack" in content
    assert "Quiet Luxury Morning Routine" in content


def test_empty_ks_still_generates_ideas(store, config, tmp_path):
    """No trend signals in KS → falls back to brand-only context, still stores 7."""
    from idea_planner_pipeline import run_idea_planner_pipeline

    job = run_idea_planner_pipeline(
        "nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path
    )
    # Dry-run always returns 7 regardless of KS state
    assert job.ideas_generated == 7


def test_job_digest_path_is_set(store, config, tmp_path):
    from idea_planner_pipeline import run_idea_planner_pipeline

    job = run_idea_planner_pipeline("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)
    assert job.digest_path is not None
    assert "idea_digest.md" in job.digest_path
