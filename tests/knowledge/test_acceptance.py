from __future__ import annotations
from datetime import datetime
from knowledge.embedder import Embedder
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore


def vec_embed(texts):
    table = {"luxury": [1.0, 0.0], "luxxury": [0.99, 0.01], "streetwear": [0.0, 1.0]}
    return [table.get(t.split()[0], [0.5, 0.5]) for t in texts]


def make_obj(page, dedup_text, parent_uids=None):
    return ContentObject(
        page=page, kind="article", title=dedup_text, summary="S", body="Body.",
        dedup_text=dedup_text, parent_uids=parent_uids or [],
        created_at=datetime(2026, 5, 19),
    )


def test_full_lifecycle(tmp_path):
    settings = KnowledgeSettings(root=tmp_path, strong_threshold=0.9, soft_threshold=0.6)
    store = KnowledgeStore(settings, embedder=Embedder("m", embed_fn=vec_embed))

    # 1. add — note, index, and vector all exist
    article = store.add(make_obj("slayhack", "luxury wardrobe guide"))
    assert store.get(article.uid) is not None
    assert store.index.get_vector(article.uid) is not None

    # 2. check_duplicate — a near-identical candidate gets a STRONG warning
    matches = store.check_duplicate("luxxury wardrobe guide", "slayhack", "article")
    assert any(m.uid == article.uid and m.level == "STRONG" for m in matches)

    # 3. extend — a branched child records lineage
    child = store.add(make_obj("slayhack", "luxury wardrobe for winter",
                               parent_uids=[article.uid]))
    lineage = store.lineage(child.uid)
    assert [o.uid for o in lineage] == [child.uid, article.uid]

    # 4. search + recent
    assert article.uid in [o.uid for o in store.search("luxury", page="slayhack")]
    assert store.recent(page="slayhack", kind="article", limit=10)

    # 5. archive — soft delete keeps the object in the store
    child.status = "archived"
    store.vault.write(child)
    store.index.upsert(child, note_hash=store.vault.note_hash(
        store.vault.note_path(child.page, child.kind, child.uid)))
    assert store.get(child.uid).status == "archived"

    # 6. rebuild_index — index reconstructs identically from the vault
    before = set(store.index.all_uids())
    store.rebuild_index()
    assert set(store.index.all_uids()) == before
