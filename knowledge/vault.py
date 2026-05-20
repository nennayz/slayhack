from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import yaml

from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings

_FRONTMATTER_FIELDS = (
    "uid", "page", "kind", "title", "summary", "dedup_text",
    "status", "parent_uids", "tags", "created_at", "asset_path",
)


class VaultWriter:
    """Reads and writes ContentObjects as Markdown notes in the Obsidian vault."""

    def __init__(self, settings: KnowledgeSettings) -> None:
        self.settings = settings

    def note_path(self, page: str, kind: str, uid: str) -> Path:
        return self.settings.vault_knowledge_dir / page / kind / f"{uid}.md"

    def write(self, obj: ContentObject) -> Path:
        if not obj.uid:
            obj.assign_uid()
        path = self.note_path(obj.page, obj.kind, obj.uid)
        path.parent.mkdir(parents=True, exist_ok=True)
        front = {f: getattr(obj, f) for f in _FRONTMATTER_FIELDS}
        front["created_at"] = obj.created_at.isoformat()
        text = "---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False) + "---\n\n" + obj.body
        path.write_text(text, encoding="utf-8")
        obj.vault_path = str(path)
        return path

    def read(self, path: Path) -> ContentObject:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            raise ValueError(f"note missing frontmatter: {path}")
        _, front_raw, body = text.split("---\n", 2)
        front = yaml.safe_load(front_raw) or {}
        front["created_at"] = datetime.fromisoformat(front["created_at"])
        obj = ContentObject(**front, body=body.lstrip("\n"))
        obj.vault_path = str(path)
        return obj

    @staticmethod
    def note_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
