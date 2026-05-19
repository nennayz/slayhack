from __future__ import annotations
from datetime import datetime
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.vault import VaultWriter


def make_obj():
    obj = ContentObject(
        page="slayhack", kind="article", title="Quiet Luxury",
        summary="Intro.", body="Body text here.",
        dedup_text="Quiet Luxury Intro",
        created_at=datetime(2026, 5, 19, 10, 0, 0),
    )
    obj.assign_uid()
    return obj


def test_write_creates_note_with_frontmatter(tmp_path):
    writer = VaultWriter(KnowledgeSettings(root=tmp_path))
    obj = make_obj()
    path = writer.write(obj)
    assert path.exists()
    assert path.name == f"{obj.uid}.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "Body text here." in text
    assert obj.vault_path == str(path)


def test_read_roundtrips_object(tmp_path):
    writer = VaultWriter(KnowledgeSettings(root=tmp_path))
    obj = make_obj()
    writer.write(obj)
    loaded = writer.read(writer.note_path(obj.page, obj.kind, obj.uid))
    assert loaded.uid == obj.uid
    assert loaded.title == obj.title
    assert loaded.body == obj.body
    assert loaded.kind == obj.kind


def test_note_hash_changes_when_file_edited(tmp_path):
    writer = VaultWriter(KnowledgeSettings(root=tmp_path))
    obj = make_obj()
    path = writer.write(obj)
    h1 = writer.note_hash(path)
    path.write_text(path.read_text(encoding="utf-8") + "\nedited", encoding="utf-8")
    assert writer.note_hash(path) != h1
