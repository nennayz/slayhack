from __future__ import annotations
from datetime import datetime
from knowledge.embedder import Embedder
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore


def fake_embed(texts):
    return [[float(len(t)), 1.0] for t in texts]


def make_store(tmp_path, embed_fn=fake_embed):
    settings = KnowledgeSettings(root=tmp_path)
    return KnowledgeStore(settings, embedder=Embedder("test-model", embed_fn=embed_fn))


def make_obj(dedup_text="quiet luxury basics"):
    return ContentObject(
        page="slayhack", kind="article", title="T", summary="S", body="B",
        dedup_text=dedup_text, created_at=datetime(2026, 5, 19),
    )


def test_add_writes_note_index_and_vector(tmp_path):
    store = make_store(tmp_path)
    obj = store.add(make_obj())
    assert obj.uid
    assert (tmp_path / "vault" / "08 Knowledge" / "slayhack" / "article" / f"{obj.uid}.md").exists()
    assert store.index.get(obj.uid) is not None
    assert store.index.get_vector(obj.uid) is not None  # embedded online


def test_add_offline_leaves_vector_pending(tmp_path):
    def broken(texts):
        raise ConnectionError("offline")
    store = make_store(tmp_path, embed_fn=broken)
    obj = store.add(make_obj())
    assert store.index.get(obj.uid) is not None      # note + index written
    assert store.index.get_vector(obj.uid) is None    # vector still pending
    assert obj.uid in store.index.pending_uids()
