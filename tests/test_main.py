from __future__ import annotations

from unittest.mock import patch

from knowledge.embedder import Embedder
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore
from models.content_job import ContentJob, ContentType, PostPerformance


def _make_store(tmp_path):
    settings = KnowledgeSettings(root=tmp_path)
    embedder = Embedder("test", embed_fn=lambda texts: [[0.0] * 4 for _ in texts])
    return KnowledgeStore(settings, embedder), settings


def _add_idea(store, status: str) -> ContentObject:
    obj = ContentObject(
        page="nayzfreedom_fleet",
        kind="idea",
        title="Test Idea",
        summary="hook",
        dedup_text="Test Idea|nayzfreedom_fleet|20260519",
        tags=["video", "Tutorial", "nayzfreedom_fleet"],
        status=status,
    )
    return store.add(obj, embed=False)


def _make_job(idea_uid: str | None = None, has_performance: bool = True) -> ContentJob:
    from project_loader import load_project

    pm = load_project("nayzfreedom_fleet")
    job = ContentJob(
        project="nayzfreedom_fleet",
        pm=pm,
        brief="T",
        platforms=["instagram"],
        dry_run=True,
        content_type=ContentType.VIDEO,
        idea_uid=idea_uid,
    )
    if has_performance:
        job.performance = [PostPerformance(platform="instagram", likes=5, reach=50)]
    return job


def test_update_ks_published_transitions_status(tmp_path):
    """When idea_uid + performance both set, status transitions to published."""
    store, settings = _make_store(tmp_path)
    stored = _add_idea(store, "in_production")
    job = _make_job(idea_uid=stored.uid, has_performance=True)

    with patch("knowledge.settings.KnowledgeSettings.from_env", return_value=settings), \
         patch("knowledge.store.KnowledgeStore", return_value=store):
        from main import _update_ks_published
        _update_ks_published(job, root=tmp_path)

    assert store.get(stored.uid).status == "published"


def test_update_ks_published_noop_when_no_idea_uid(tmp_path):
    """Jobs without idea_uid (pre-SP-3) are silently skipped — no error."""
    store, settings = _make_store(tmp_path)
    job = _make_job(idea_uid=None, has_performance=True)

    with patch("knowledge.settings.KnowledgeSettings.from_env", return_value=settings), \
         patch("knowledge.store.KnowledgeStore", return_value=store):
        from main import _update_ks_published
        _update_ks_published(job, root=tmp_path)  # must not raise


def test_update_ks_published_noop_when_no_performance(tmp_path):
    """Jobs without performance data don't transition KS status."""
    store, settings = _make_store(tmp_path)
    stored = _add_idea(store, "in_production")
    job = _make_job(idea_uid=stored.uid, has_performance=False)

    with patch("knowledge.settings.KnowledgeSettings.from_env", return_value=settings), \
         patch("knowledge.store.KnowledgeStore", return_value=store):
        from main import _update_ks_published
        _update_ks_published(job, root=tmp_path)

    # status must remain unchanged
    assert store.get(stored.uid).status == "in_production"
