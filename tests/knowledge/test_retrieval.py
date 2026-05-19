from __future__ import annotations
from datetime import datetime
from knowledge.embedder import Embedder
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore


def fake_embed(texts):
    return [[float(len(t)), 1.0] for t in texts]


def make_store(tmp_path):
    return KnowledgeStore(KnowledgeSettings(root=tmp_path),
                          embedder=Embedder("m", embed_fn=fake_embed))


def add(store, dedup_text, parent_uids=None):
    obj = ContentObject(page="slayhack", kind="article", title=dedup_text,
                        summary="S", body="B", dedup_text=dedup_text,
                        parent_uids=parent_uids or [], created_at=datetime(2026, 5, 19))
    return store.add(obj)


def test_get_returns_object(tmp_path):
    store = make_store(tmp_path)
    added = add(store, "quiet luxury basics")
    got = store.get(added.uid)
    assert got is not None and got.uid == added.uid and got.title == "quiet luxury basics"


def test_get_missing_returns_none(tmp_path):
    assert make_store(tmp_path).get("nope") is None


def test_search_finds_by_keyword(tmp_path):
    store = make_store(tmp_path)
    a = add(store, "quiet luxury wardrobe")
    add(store, "loud streetwear noise")
    hits = store.search("luxury")
    assert a.uid in [o.uid for o in hits]


def test_recent_returns_newest_first(tmp_path):
    store = make_store(tmp_path)
    first = add(store, "first article topic")
    second = add(store, "second article topic")
    recent = store.recent(page="slayhack", kind="article", limit=10)
    uids = [o.uid for o in recent]
    assert set(uids) >= {first.uid, second.uid}


def test_lineage_walks_parents(tmp_path):
    store = make_store(tmp_path)
    root = add(store, "root topic")
    child = add(store, "child topic", parent_uids=[root.uid])
    lineage = store.lineage(child.uid)
    assert [o.uid for o in lineage] == [child.uid, root.uid]
