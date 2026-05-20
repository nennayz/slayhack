from __future__ import annotations
from datetime import datetime
from knowledge.index import Index
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings


def make_obj(uid="slayhack-article-20260519-aaaa", page="slayhack", kind="article",
             dedup_text="quiet luxury basics"):
    obj = ContentObject(
        page=page, kind=kind, title="T", summary="S", body="B",
        dedup_text=dedup_text, created_at=datetime(2026, 5, 19),
    )
    obj.uid = uid
    obj.vault_path = f"/vault/{uid}.md"
    return obj


def test_upsert_then_get(tmp_path):
    idx = Index(KnowledgeSettings(root=tmp_path))
    obj = make_obj()
    idx.upsert(obj, note_hash="h1")
    row = idx.get(obj.uid)
    assert row is not None
    assert row["uid"] == obj.uid
    assert row["page"] == "slayhack"
    assert row["note_hash"] == "h1"


def test_upsert_is_idempotent(tmp_path):
    idx = Index(KnowledgeSettings(root=tmp_path))
    obj = make_obj()
    idx.upsert(obj, note_hash="h1")
    idx.upsert(obj, note_hash="h2")
    assert idx.get(obj.uid)["note_hash"] == "h2"
    assert len(idx.all_uids()) == 1


def test_fts_search_matches_dedup_text(tmp_path):
    idx = Index(KnowledgeSettings(root=tmp_path))
    idx.upsert(make_obj(uid="u1", dedup_text="quiet luxury wardrobe"), note_hash="h")
    idx.upsert(make_obj(uid="u2", dedup_text="loud streetwear trends"), note_hash="h")
    hits = idx.fts_search("luxury", page="slayhack")
    assert "u1" in hits and "u2" not in hits


def test_delete_removes_row(tmp_path):
    idx = Index(KnowledgeSettings(root=tmp_path))
    obj = make_obj()
    idx.upsert(obj, note_hash="h")
    idx.delete(obj.uid)
    assert idx.get(obj.uid) is None
