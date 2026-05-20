from __future__ import annotations
from datetime import datetime
from knowledge.embedder import Embedder
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore


def make_obj(dedup_text):
    return ContentObject(page="slayhack", kind="article", title="T", summary="S",
                         body="B", dedup_text=dedup_text, created_at=datetime(2026, 5, 19))


def test_drain_embeds_pending(tmp_path):
    def broken(texts):
        raise ConnectionError("offline")
    store = KnowledgeStore(KnowledgeSettings(root=tmp_path),
                           embedder=Embedder("m", embed_fn=broken))
    obj = store.add(make_obj("topic"))
    assert obj.uid in store.index.pending_uids()

    store.embedder = Embedder("m", embed_fn=lambda ts: [[1.0, 0.0] for _ in ts])
    count = store.drain_pending()
    assert count == 1
    assert store.index.pending_uids() == []
    assert store.index.get_vector(obj.uid) is not None


def test_drain_is_resumable_on_partial_failure(tmp_path):
    calls = {"n": 0}

    def flaky(texts):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ConnectionError("dropped mid-drain")
        return [[1.0, 0.0] for _ in texts]

    store = KnowledgeStore(KnowledgeSettings(root=tmp_path),
                           embedder=Embedder("m", embed_fn=lambda ts: (_ for _ in ()).throw(ConnectionError())))
    a = store.add(make_obj("topic a"))
    b = store.add(make_obj("topic b"))
    assert set(store.index.pending_uids()) == {a.uid, b.uid}

    # drain one at a time; second call fails
    store.embedder = Embedder("m", embed_fn=flaky)
    store.drain_pending()
    remaining = store.index.pending_uids()
    assert len(remaining) == 1            # one succeeded, one still pending
    # recover: a working embedder drains the rest
    store.embedder = Embedder("m", embed_fn=lambda ts: [[1.0, 0.0] for _ in ts])
    store.drain_pending()
    assert store.index.pending_uids() == []


def test_drain_reembeds_after_model_change(tmp_path):
    store = KnowledgeStore(
        KnowledgeSettings(root=tmp_path),
        embedder=Embedder("model-v1", embed_fn=lambda ts: [[1.0, 0.0] for _ in ts]),
    )
    obj = store.add(make_obj("topic"))
    assert store.index.pending_uids() == []  # embedded under model-v1

    # switch embedding model: the old vector must be re-embedded
    store.embedder = Embedder("model-v2", embed_fn=lambda ts: [[0.0, 1.0] for _ in ts])
    count = store.drain_pending()
    assert count == 1
    model, vector = store.index.get_vector(obj.uid)
    assert model == "model-v2"
    assert vector == [0.0, 1.0]
