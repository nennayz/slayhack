from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from knowledge.embedder import Embedder, OfflineError
from knowledge.index import Index
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.vault import VaultWriter

if TYPE_CHECKING:
    from knowledge.dedup import DedupMatch


class KnowledgeStore:
    """Public facade for the Knowledge Store."""

    def __init__(self, settings: KnowledgeSettings, embedder: Embedder) -> None:
        self.settings = settings
        self.vault = VaultWriter(settings)
        self.index = Index(settings)
        self.embedder = embedder

    def add(self, obj: ContentObject, embed: bool = True) -> ContentObject:
        """Persist an object: vault note first, then index, then embedding.

        With embed=False the vector is left pending (used by backfill to avoid a
        burst of API calls — drain it gradually afterwards).
        """
        taken = set(self.index.all_uids())
        obj.assign_uid(taken=taken)
        path = self.vault.write(obj)                       # 1. truth
        self.index.upsert(obj, note_hash=self.vault.note_hash(path))  # 2. index
        if embed:
            try:                                           # 3. embedding (best-effort)
                vector = self.embedder.embed([obj.dedup_text])[0]
                self.index.set_vector(obj.uid, self.embedder.model, vector)
            except OfflineError:
                pass  # stays pending; drained later
        return obj

    def check_duplicate(self, dedup_text: str, page: str, kind: str,
                        online: bool = True) -> list["DedupMatch"]:
        from knowledge.dedup import DedupChecker

        return DedupChecker(self).check(dedup_text, page, kind, online=online)

    def get(self, uid: str) -> ContentObject | None:
        row = self.index.get(uid)
        if row is None:
            return None
        return self.vault.read(Path(row["vault_path"]))

    def search(self, query: str, page: str | None = None,
               kind: str | None = None, limit: int = 20) -> list[ContentObject]:
        results: list[ContentObject] = []
        for uid in self.index.fts_search(query, page=page, limit=limit):
            obj = self.get(uid)
            if obj is not None and (kind is None or obj.kind == kind):
                results.append(obj)
        return results

    def recent(self, page: str | None = None, kind: str | None = None,
               limit: int = 20) -> list[ContentObject]:
        sql = "SELECT uid FROM notes"
        clauses: list[str] = []
        params: list[str] = []
        if page:
            clauses.append("page=?")
            params.append(page)
        if kind:
            clauses.append("kind=?")
            params.append(kind)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += f" ORDER BY created_at DESC, uid DESC LIMIT {int(limit)}"
        uids = [r["uid"] for r in self.index.conn.execute(sql, params)]
        return [o for o in (self.get(u) for u in uids) if o is not None]

    def lineage(self, uid: str) -> list[ContentObject]:
        """Return [obj, parent, grandparent, ...] following the first parent chain."""
        chain: list[ContentObject] = []
        seen: set[str] = set()
        cursor: str | None = uid
        while cursor and cursor not in seen:
            seen.add(cursor)
            obj = self.get(cursor)
            if obj is None:
                break
            chain.append(obj)
            cursor = obj.parent_uids[0] if obj.parent_uids else None
        return chain

    def rebuild_index(self) -> int:
        """Drop and rebuild the index from vault notes. Returns the note count.

        The vault is the source of truth: orphan rows (note missing) are dropped,
        and human-edited notes are re-indexed from their current content.
        """
        self.index.conn.execute("DELETE FROM notes")
        self.index.conn.execute("DELETE FROM notes_fts")
        # keep cached vectors; drop only vectors whose note is gone (done below)
        self.index.conn.commit()

        knowledge_dir = self.settings.vault_knowledge_dir
        live_uids: set[str] = set()
        if knowledge_dir.exists():
            for note in knowledge_dir.rglob("*.md"):
                obj = self.vault.read(note)
                self.index.upsert(obj, note_hash=self.vault.note_hash(note))
                live_uids.add(obj.uid)

        # sweep vectors for notes that no longer exist
        rows = self.index.conn.execute("SELECT uid FROM vectors").fetchall()
        for row in rows:
            if row["uid"] not in live_uids:
                self.index.conn.execute("DELETE FROM vectors WHERE uid=?", (row["uid"],))
        self.index.conn.commit()
        return len(live_uids)
