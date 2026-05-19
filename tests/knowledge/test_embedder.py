from __future__ import annotations
from knowledge.embedder import Embedder, OfflineError


def fake_embed(texts):
    return [[float(len(t)), 1.0, 0.0] for t in texts]


def test_embed_returns_vector():
    emb = Embedder(model="test-model", embed_fn=fake_embed)
    vecs = emb.embed(["hello"])
    assert vecs == [[5.0, 1.0, 0.0]]


def test_embed_offline_raises():
    def broken(texts):
        raise ConnectionError("no network")
    emb = Embedder(model="test-model", embed_fn=broken)
    try:
        emb.embed(["hello"])
        assert False, "expected OfflineError"
    except OfflineError:
        pass
