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


def add(store, dedup_text):
    obj = ContentObject(page="slayhack", kind="article", title=dedup_text,
                        summary="S", body="B", dedup_text=dedup_text,
                        created_at=datetime(2026, 5, 19))
    return store.add(obj)


def test_rebuild_reconstructs_all_rows(tmp_path):
    store = make_store(tmp_path)
    a, b = add(store, "topic one"), add(store, "topic two")
    store.index.conn.execute("DELETE FROM notes")  # corrupt the index
    store.index.conn.commit()
    store.rebuild_index()
    assert store.index.get(a.uid) is not None
    assert store.index.get(b.uid) is not None


def test_rebuild_sweeps_orphan_rows(tmp_path):
    store = make_store(tmp_path)
    a = add(store, "real topic")
    # inject an index row whose note does not exist
    ghost = ContentObject(page="slayhack", kind="article", title="ghost",
                          summary="", body="", dedup_text="ghost",
                          created_at=datetime(2026, 5, 19))
    ghost.uid = "slayhack-article-20260519-dead"
    ghost.vault_path = "/nonexistent/ghost.md"
    store.index.upsert(ghost, note_hash="x")
    store.rebuild_index()
    assert store.index.get("slayhack-article-20260519-dead") is None
    assert store.index.get(a.uid) is not None


def test_rebuild_reconciles_human_edit(tmp_path):
    store = make_store(tmp_path)
    a = add(store, "editable topic")
    path = store.vault.note_path(a.page, a.kind, a.uid)
    text = path.read_text(encoding="utf-8").replace("dedup_text: editable topic",
                                                    "dedup_text: human edited topic")
    path.write_text(text, encoding="utf-8")
    store.rebuild_index()
    assert store.index.get(a.uid)["dedup_text"] == "human edited topic"
