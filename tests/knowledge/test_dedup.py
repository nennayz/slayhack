from __future__ import annotations
from datetime import datetime
from knowledge.dedup import DedupChecker, DedupMatch  # noqa: F401
from knowledge.embedder import Embedder
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore


def vec_embed(texts):
    # deterministic 2-D vectors keyed by a leading tag word
    table = {"luxury": [1.0, 0.0], "luxxury": [0.99, 0.01], "streetwear": [0.0, 1.0]}
    return [table.get(t.split()[0], [0.5, 0.5]) for t in texts]


def make_store(tmp_path, embed_fn=vec_embed):
    settings = KnowledgeSettings(root=tmp_path, strong_threshold=0.9, soft_threshold=0.6)
    return KnowledgeStore(settings, embedder=Embedder("m", embed_fn=embed_fn))


def add(store, page, dedup_text):
    obj = ContentObject(page=page, kind="article", title="T", summary="S",
                        body="B", dedup_text=dedup_text, created_at=datetime(2026, 5, 19))
    return store.add(obj)


def test_strong_match_same_page(tmp_path):
    store = make_store(tmp_path)
    existing = add(store, "slayhack", "luxury wardrobe guide")
    checker = DedupChecker(store)
    matches = checker.check("luxxury wardrobe guide", page="slayhack", kind="article")
    assert any(m.uid == existing.uid and m.level == "STRONG" for m in matches)


def test_cross_page_is_soft(tmp_path):
    store = make_store(tmp_path)
    other = add(store, "stadium_sweethearts", "luxury wardrobe guide")
    checker = DedupChecker(store)
    matches = checker.check("luxxury wardrobe guide", page="slayhack", kind="article")
    assert any(m.uid == other.uid and m.level == "SOFT" for m in matches)


def test_no_match_for_unrelated(tmp_path):
    store = make_store(tmp_path)
    add(store, "slayhack", "streetwear trends")
    checker = DedupChecker(store)
    matches = checker.check("luxury wardrobe guide", page="slayhack", kind="article")
    assert matches == []


def test_offline_falls_back_to_keyword(tmp_path):
    store = make_store(tmp_path)
    existing = add(store, "slayhack", "luxury wardrobe guide")
    # simulate offline: drop the stored vector so cosine path finds nothing
    store.index.conn.execute("UPDATE vectors SET pending=1, vector=NULL")
    store.index.conn.commit()
    checker = DedupChecker(store)
    matches = checker.check("luxury basics", page="slayhack", kind="article", online=False)
    assert any(m.uid == existing.uid for m in matches)
    assert all(m.score is None for m in matches)  # keyword hits are unscored
