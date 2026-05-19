from __future__ import annotations

import pytest

from knowledge.embedder import Embedder
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore


@pytest.fixture
def store(tmp_path):
    settings = KnowledgeSettings(root=tmp_path)
    embedder = Embedder("test", embed_fn=lambda texts: [[0.0] * 4 for _ in texts])
    return KnowledgeStore(settings, embedder)


def _make_idea(page: str, title: str, n: int) -> ContentObject:
    return ContentObject(
        page=page,
        kind="idea",
        title=title,
        dedup_text=f"{title}|{page}|20260519",
        body=f"## Idea {n}\n\nHook: test hook",
        tags=["video", page],
        status="new",
    )


def test_recent_status_filter_new(store):
    obj = store.add(_make_idea("nayzfreedom_fleet", "Idea Alpha", 1), embed=False)
    results = store.recent(kind="idea", status="new")
    assert any(o.uid == obj.uid for o in results)


def test_recent_status_filter_approved_excludes_new(store):
    store.add(_make_idea("nayzfreedom_fleet", "Idea Beta", 2), embed=False)
    results = store.recent(kind="idea", status="approved")
    assert results == []


def test_set_status_updates_to_approved(store):
    obj = store.add(_make_idea("nayzfreedom_fleet", "Idea Gamma", 3), embed=False)
    updated = store.set_status(obj.uid, "approved")
    assert updated.status == "approved"


def test_set_status_persists_in_index(store):
    obj = store.add(_make_idea("nayzfreedom_fleet", "Idea Delta", 4), embed=False)
    store.set_status(obj.uid, "rejected")
    reloaded = store.get(obj.uid)
    assert reloaded is not None
    assert reloaded.status == "rejected"


def test_set_status_persists_in_vault(store):
    obj = store.add(_make_idea("nayzfreedom_fleet", "Idea Epsilon", 5), embed=False)
    store.set_status(obj.uid, "approved")
    # Rebuild index from vault to verify vault is the source of truth
    store.rebuild_index()
    reloaded = store.get(obj.uid)
    assert reloaded is not None
    assert reloaded.status == "approved"


def test_set_status_unknown_uid_raises(store):
    with pytest.raises(KeyError):
        store.set_status("no-such-uid", "approved")


def test_recent_no_status_filter_returns_all(store):
    store.add(_make_idea("nayzfreedom_fleet", "Idea Zeta", 6), embed=False)
    obj2 = store.add(_make_idea("nayzfreedom_fleet", "Idea Eta", 7), embed=False)
    store.set_status(obj2.uid, "approved")
    results = store.recent(kind="idea")
    statuses = {o.status for o in results}
    assert "new" in statuses
    assert "approved" in statuses
