from __future__ import annotations

import json
import sqlite3

from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    uid TEXT PRIMARY KEY,
    page TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    dedup_text TEXT NOT NULL,
    status TEXT NOT NULL,
    parent_uids TEXT NOT NULL,
    created_at TEXT NOT NULL,
    vault_path TEXT NOT NULL,
    note_hash TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    uid UNINDEXED, page UNINDEXED, dedup_text
);
CREATE TABLE IF NOT EXISTS vectors (
    uid TEXT PRIMARY KEY,
    embed_model TEXT,
    vector TEXT,
    pending INTEGER NOT NULL DEFAULT 1
);
"""


class Index:
    """Derived, disposable SQLite index over the vault."""

    def __init__(self, settings: KnowledgeSettings) -> None:
        self.settings = settings
        self.conn = sqlite3.connect(str(settings.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def upsert(self, obj: ContentObject, note_hash: str) -> None:
        self.conn.execute(
            """INSERT INTO notes
               (uid, page, kind, title, dedup_text, status, parent_uids,
                created_at, vault_path, note_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(uid) DO UPDATE SET
                 page=excluded.page, kind=excluded.kind, title=excluded.title,
                 dedup_text=excluded.dedup_text, status=excluded.status,
                 parent_uids=excluded.parent_uids, created_at=excluded.created_at,
                 vault_path=excluded.vault_path, note_hash=excluded.note_hash""",
            (obj.uid, obj.page, obj.kind, obj.title, obj.dedup_text, obj.status,
             json.dumps(obj.parent_uids), obj.created_at.isoformat(),
             obj.vault_path, note_hash),
        )
        self.conn.execute("DELETE FROM notes_fts WHERE uid=?", (obj.uid,))
        self.conn.execute(
            "INSERT INTO notes_fts (uid, page, dedup_text) VALUES (?,?,?)",
            (obj.uid, obj.page, obj.dedup_text),
        )
        self.conn.execute(
            "INSERT INTO vectors (uid, pending) VALUES (?, 1) "
            "ON CONFLICT(uid) DO NOTHING",
            (obj.uid,),
        )
        self.conn.commit()

    def get(self, uid: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM notes WHERE uid=?", (uid,)).fetchone()

    def all_uids(self) -> list[str]:
        return [r["uid"] for r in self.conn.execute("SELECT uid FROM notes")]

    def fts_search(self, query: str, page: str | None = None, limit: int = 20) -> list[str]:
        sql = "SELECT uid FROM notes_fts WHERE notes_fts MATCH ?"
        params: list[object] = [query]
        if page:
            sql += " AND page=?"
            params.append(page)
        sql += f" LIMIT {int(limit)}"
        return [r["uid"] for r in self.conn.execute(sql, params)]

    def delete(self, uid: str) -> None:
        self.conn.execute("DELETE FROM notes WHERE uid=?", (uid,))
        self.conn.execute("DELETE FROM notes_fts WHERE uid=?", (uid,))
        self.conn.execute("DELETE FROM vectors WHERE uid=?", (uid,))
        self.conn.commit()

    def set_vector(self, uid: str, embed_model: str, vector: list[float]) -> None:
        self.conn.execute(
            "UPDATE vectors SET embed_model=?, vector=?, pending=0 WHERE uid=?",
            (embed_model, json.dumps(vector), uid),
        )
        self.conn.commit()

    def get_vector(self, uid: str) -> tuple[str, list[float]] | None:
        row = self.conn.execute(
            "SELECT embed_model, vector FROM vectors WHERE uid=? AND pending=0", (uid,)
        ).fetchone()
        if row is None or row["vector"] is None:
            return None
        return row["embed_model"], json.loads(row["vector"])

    def pending_uids(self) -> list[str]:
        return [r["uid"] for r in self.conn.execute(
            "SELECT uid FROM vectors WHERE pending=1")]

    def all_vectors(self) -> list[tuple[str, str, list[float]]]:
        rows = self.conn.execute(
            """SELECT v.uid, n.page, v.vector FROM vectors v JOIN notes n ON n.uid=v.uid
               WHERE v.pending=0 AND v.vector IS NOT NULL""")
        return [(r["uid"], r["page"], json.loads(r["vector"])) for r in rows]

    def close(self) -> None:
        self.conn.close()
