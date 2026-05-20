from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from knowledge.embedder import Embedder
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore
from models.content_job import ContentJob, JobStatus


@pytest.fixture
def store(tmp_path):
    settings = KnowledgeSettings(root=tmp_path)
    embedder = Embedder("test", embed_fn=lambda texts: [[0.0] * 4 for _ in texts])
    return KnowledgeStore(settings, embedder)


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.openai_api_key = "test"
    cfg.openai_robin_model = "gpt-4o"
    return cfg


def _add_idea(store, title: str, status: str, n: int) -> ContentObject:
    obj = ContentObject(
        page="nayzfreedom_fleet", kind="idea", title=title,
        summary="test hook", dedup_text=f"{title}|20260519|{n}",
        tags=["video", "Tutorial", "nayzfreedom_fleet"], status=status,
    )
    return store.add(obj, embed=False)


def _mock_orchestrator_success(job: ContentJob, **kwargs) -> ContentJob:
    job.status = JobStatus.COMPLETED
    return job


def test_picks_up_approved_idea(store, config, tmp_path):
    from production_loop import run_production_loop
    idea = _add_idea(store, "Approved Idea", "approved", 1)
    with patch("production_loop.Orchestrator") as MockOrch:
        MockOrch.return_value.run.side_effect = _mock_orchestrator_success
        result = run_production_loop("nayzfreedom_fleet", config, store,
                                     dry_run=True, output_root=tmp_path)
    assert result.ideas_found == 1
    assert result.jobs_started == 1
    assert result.jobs_completed == 1
    assert store.get(idea.uid).status == "in_production"


def test_skips_new_ideas(store, config, tmp_path):
    from production_loop import run_production_loop
    _add_idea(store, "New Idea", "new", 2)
    with patch("production_loop.Orchestrator") as MockOrch:
        result = run_production_loop("nayzfreedom_fleet", config, store,
                                     dry_run=True, output_root=tmp_path)
    assert result.ideas_found == 0
    MockOrch.return_value.run.assert_not_called()


def test_skips_rejected_ideas(store, config, tmp_path):
    from production_loop import run_production_loop
    _add_idea(store, "Rejected Idea", "rejected", 3)
    result = run_production_loop("nayzfreedom_fleet", config, store,
                                  dry_run=True, output_root=tmp_path)
    assert result.ideas_found == 0


def test_empty_store_returns_immediately(store, config, tmp_path):
    from production_loop import run_production_loop
    result = run_production_loop("nayzfreedom_fleet", config, store,
                                  dry_run=True, output_root=tmp_path)
    assert result.ideas_found == 0
    assert result.jobs_started == 0


def test_orchestrator_failure_resets_status(store, config, tmp_path):
    from production_loop import run_production_loop
    idea = _add_idea(store, "Failing Idea", "approved", 4)
    with patch("production_loop.Orchestrator") as MockOrch:
        MockOrch.return_value.run.side_effect = RuntimeError("LLM error")
        result = run_production_loop("nayzfreedom_fleet", config, store,
                                     dry_run=True, output_root=tmp_path)
    assert result.jobs_failed == 1
    assert store.get(idea.uid).status == "approved"


def test_limit_one_per_run(store, config, tmp_path):
    from production_loop import run_production_loop
    _add_idea(store, "First Approved", "approved", 5)
    _add_idea(store, "Second Approved", "approved", 6)
    with patch("production_loop.Orchestrator") as MockOrch:
        MockOrch.return_value.run.side_effect = _mock_orchestrator_success
        result = run_production_loop("nayzfreedom_fleet", config, store,
                                     dry_run=True, output_root=tmp_path)
    assert result.jobs_started == 1
    remaining = store.recent(kind="idea", status="approved")
    assert len(remaining) == 1


def test_dry_run_sets_in_production(store, config, tmp_path):
    from production_loop import run_production_loop
    idea = _add_idea(store, "Dry Run Idea", "approved", 7)
    job_captured = []

    def capture(job, **kwargs):
        job_captured.append(job)
        return _mock_orchestrator_success(job)

    with patch("production_loop.Orchestrator") as MockOrch:
        MockOrch.return_value.run.side_effect = capture
        run_production_loop("nayzfreedom_fleet", config, store,
                             dry_run=True, output_root=tmp_path)
    assert job_captured[0].dry_run is True
    assert store.get(idea.uid).status == "in_production"
