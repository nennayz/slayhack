# SP-0 Knowledge Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Knowledge Store — the content backbone that stores every pipeline artifact as Obsidian notes, indexes them in SQLite, detects near-duplicates, and retrieves content by id.

**Architecture:** The Obsidian vault holds canonical Markdown notes (source of truth). A derived, disposable SQLite file (`knowledge.db`) indexes them with full-text (FTS5) and embedding vectors. Semantic dedup warns on near-duplicates and suggests extending instead of blocking. Everything works offline; embeddings degrade to keyword search and backfill when online.

**Tech Stack:** Python 3.12, Pydantic 2, SQLite (stdlib `sqlite3`, FTS5), OpenAI embeddings (`text-embedding-3-small`), PyYAML, pytest + pytest-mock.

**Companion spec:** `docs/superpowers/specs/2026-05-19-knowledge-store-design.md` — read it before starting.

**Checkpoints:** This plan has 3 review checkpoints. Stop at each, hand work back to the Captain for review, and wait for approval before continuing.
- **CP1 — Data layer:** after Task 5
- **CP2 — Logic layer:** after Task 9
- **CP3 — Backfill + tests:** after Task 13

---

## File Structure

All new code lives in a new `knowledge/` package, consistent with the existing `models/`, `agents/`, `routes/` packages.

| File | Responsibility |
|------|----------------|
| `knowledge/__init__.py` | Package marker; re-exports `KnowledgeStore`. |
| `knowledge/object.py` | `ContentObject` Pydantic model + `make_uid()`. |
| `knowledge/settings.py` | `KnowledgeSettings` dataclass — paths, dedup thresholds, embed model. |
| `knowledge/vault.py` | `VaultWriter` — write/read Markdown notes with YAML frontmatter; note-hash for human-edit detection. |
| `knowledge/index.py` | `Index` — SQLite schema (metadata + FTS5 + vectors), upsert, query, orphan sweep. |
| `knowledge/embedder.py` | `Embedder` — OpenAI embeddings, vector cache, pending queue, offline-safe. |
| `knowledge/dedup.py` | `DedupChecker` — cosine similarity / FTS5 fallback, STRONG/SOFT classification. |
| `knowledge/store.py` | `KnowledgeStore` — public facade: `add`, `check_duplicate`, `get`, `search`, `recent`, `lineage`, `rebuild_index`, `drain_pending`. |
| `knowledge/backfill.py` | `backfill()` — import existing `output/` + vault content; `--dry-run` report. |
| `knowledge/cli.py` | CLI entrypoints: `rebuild`, `backfill`, `drain`. |
| `tests/knowledge/` | Test package mirroring the above. |
| `tests/knowledge/golden_corpus.yaml` | Labeled near/far content pairs for dedup regression. |
| `scripts/calibrate_dedup.py` | Reports false-positive/negative rates against the golden corpus. |

**Conventions to follow:** every module starts with `from __future__ import annotations`. Tests use `tmp_path` + `monkeypatch`, no live API calls (mock the embedder). Run `ruff check .` and `mypy .` clean before each commit.

---

# CHECKPOINT 1 — Data layer (Tasks 1–5)

---

### Task 1: ContentObject model + UID

**Files:**
- Create: `knowledge/__init__.py`
- Create: `knowledge/object.py`
- Create: `tests/knowledge/__init__.py`
- Test: `tests/knowledge/test_object.py`

- [ ] **Step 1: Write the failing test**

`tests/knowledge/test_object.py`:

```python
from __future__ import annotations
from datetime import datetime
from knowledge.object import ContentObject, make_uid


def make_obj(**kw):
    base = dict(
        page="slayhack", kind="article", title="Quiet Luxury Basics",
        summary="An intro to quiet luxury.", body="Full body text.",
        dedup_text="Quiet Luxury Basics — an intro to quiet luxury.",
        created_at=datetime(2026, 5, 19, 10, 0, 0),
    )
    base.update(kw)
    return ContentObject(**base)


def test_make_uid_format():
    uid = make_uid("slayhack", "article", datetime(2026, 5, 19), "some text")
    assert uid.startswith("slayhack-article-20260519-")
    assert len(uid.split("-")[-1]) == 4


def test_make_uid_is_deterministic():
    a = make_uid("slayhack", "article", datetime(2026, 5, 19), "same text")
    b = make_uid("slayhack", "article", datetime(2026, 5, 19), "same text")
    assert a == b


def test_make_uid_collision_extends_hash():
    taken = {make_uid("slayhack", "idea", datetime(2026, 5, 19), "text one")}
    uid = make_uid("slayhack", "idea", datetime(2026, 5, 19), "text two", taken=taken)
    assert uid not in taken


def test_content_object_defaults():
    obj = make_obj()
    assert obj.status == "new"
    assert obj.parent_uids == []
    assert obj.tags == []
    assert obj.asset_path is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/knowledge/test_object.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'knowledge'`

- [ ] **Step 3: Write minimal implementation**

`knowledge/__init__.py`:

```python
from __future__ import annotations
```

`tests/knowledge/__init__.py`: empty file.

`knowledge/object.py`:

```python
from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, Field

KNOWN_KINDS = ("trend", "idea", "plan", "article", "image", "video", "caption")
STATUS_VALUES = ("new", "approved", "done", "archived", "rejected")


def make_uid(
    page: str,
    kind: str,
    created_at: datetime,
    dedup_text: str,
    taken: set[str] | None = None,
) -> str:
    """Build a stable, collision-checked uid: <page>-<kind>-<YYYYMMDD>-<hashN>."""
    taken = taken or set()
    date = created_at.strftime("%Y%m%d")
    digest = hashlib.sha256(dedup_text.encode("utf-8")).hexdigest()
    for length in range(4, len(digest) + 1):
        uid = f"{page}-{kind}-{date}-{digest[:length]}"
        if uid not in taken:
            return uid
    raise ValueError("could not generate a unique uid")


class ContentObject(BaseModel):
    """The shared contract for every artifact in the content pipeline."""

    page: str
    kind: str  # open string; KNOWN_KINDS is advisory only
    title: str
    summary: str = ""
    body: str = ""
    dedup_text: str
    status: str = "new"
    parent_uids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    uid: str = ""
    vault_path: str = ""
    asset_path: str | None = None

    def assign_uid(self, taken: set[str] | None = None) -> str:
        """Set self.uid (if empty) from page/kind/created_at/dedup_text."""
        if not self.uid:
            self.uid = make_uid(
                self.page, self.kind, self.created_at, self.dedup_text, taken=taken
            )
        return self.uid
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/knowledge/test_object.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add knowledge/__init__.py knowledge/object.py tests/knowledge/__init__.py tests/knowledge/test_object.py
git commit -m "feat(knowledge): add ContentObject model and uid generator"
```

---

### Task 2: KnowledgeSettings

**Files:**
- Create: `knowledge/settings.py`
- Test: `tests/knowledge/test_settings.py`

- [ ] **Step 1: Write the failing test**

`tests/knowledge/test_settings.py`:

```python
from __future__ import annotations
from pathlib import Path
from knowledge.settings import KnowledgeSettings


def test_defaults(tmp_path):
    s = KnowledgeSettings(root=tmp_path)
    assert s.vault_knowledge_dir == tmp_path / "vault" / "08 Knowledge"
    assert s.db_path == tmp_path / "knowledge.db"
    assert 0.0 < s.soft_threshold < s.strong_threshold <= 1.0
    assert s.embed_model == "text-embedding-3-small"


def test_thresholds_override_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_STRONG_THRESHOLD", "0.9")
    monkeypatch.setenv("KNOWLEDGE_SOFT_THRESHOLD", "0.7")
    s = KnowledgeSettings.from_env(root=tmp_path)
    assert s.strong_threshold == 0.9
    assert s.soft_threshold == 0.7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/knowledge/test_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'knowledge.settings'`

- [ ] **Step 3: Write minimal implementation**

`knowledge/settings.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class KnowledgeSettings:
    """Paths and tunables for the Knowledge Store.

    `root` is the workspace root. In production this is the repo root and the
    vault is resolved relative to it; tests pass a tmp_path.
    """

    root: Path
    vault_subdir: Path = field(default_factory=lambda: Path("vault"))
    strong_threshold: float = 0.82
    soft_threshold: float = 0.68
    embed_model: str = "text-embedding-3-small"
    backfill_batch_size: int = 50

    @property
    def vault_knowledge_dir(self) -> Path:
        return self.root / self.vault_subdir / "08 Knowledge"

    @property
    def db_path(self) -> Path:
        return self.root / "knowledge.db"

    @classmethod
    def from_env(cls, root: Path) -> "KnowledgeSettings":
        return cls(
            root=root,
            strong_threshold=float(os.getenv("KNOWLEDGE_STRONG_THRESHOLD", "0.82")),
            soft_threshold=float(os.getenv("KNOWLEDGE_SOFT_THRESHOLD", "0.68")),
            embed_model=os.getenv("KNOWLEDGE_EMBED_MODEL", "text-embedding-3-small"),
        )
```

**Note:** In production the vault is `vaults/NayzFreedom Vault/`. The executor sets `vault_subdir=Path("vaults/NayzFreedom Vault")` when constructing settings for real runs; tests use the default `vault/`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/knowledge/test_settings.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add knowledge/settings.py tests/knowledge/test_settings.py
git commit -m "feat(knowledge): add KnowledgeSettings with tunable thresholds"
```

---

### Task 3: VaultWriter

**Files:**
- Create: `knowledge/vault.py`
- Test: `tests/knowledge/test_vault.py`

`VaultWriter` writes a `ContentObject` as `<knowledge_dir>/<page>/<kind>/<uid>.md` with YAML
frontmatter, reads it back, and computes a content hash so callers can detect human edits.

- [ ] **Step 1: Write the failing test**

`tests/knowledge/test_vault.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/knowledge/test_vault.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'knowledge.vault'`

- [ ] **Step 3: Write minimal implementation**

`knowledge/vault.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/knowledge/test_vault.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add knowledge/vault.py tests/knowledge/test_vault.py
git commit -m "feat(knowledge): add VaultWriter for Markdown note read/write"
```

---

### Task 4: Index (SQLite)

**Files:**
- Create: `knowledge/index.py`
- Test: `tests/knowledge/test_index.py`

The `Index` mirrors note frontmatter into SQLite: a `notes` table, an FTS5 `notes_fts`
virtual table for keyword search, and a `vectors` table for embeddings. It opens in WAL mode.

- [ ] **Step 1: Write the failing test**

`tests/knowledge/test_index.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/knowledge/test_index.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'knowledge.index'`

- [ ] **Step 3: Write minimal implementation**

`knowledge/index.py`:

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/knowledge/test_index.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add knowledge/index.py tests/knowledge/test_index.py
git commit -m "feat(knowledge): add SQLite Index with FTS5 and vectors tables"
```

---

### Task 5: Embedder + KnowledgeStore.add (CP1 close)

**Files:**
- Create: `knowledge/embedder.py`
- Create: `knowledge/store.py`
- Modify: `knowledge/__init__.py`
- Test: `tests/knowledge/test_embedder.py`
- Test: `tests/knowledge/test_store_add.py`

The `Embedder` wraps the OpenAI embeddings API and is offline-safe: it accepts an
injectable `embed_fn` so tests never hit the network. `KnowledgeStore.add` wires
vault → index → embedder in that order.

- [ ] **Step 1: Write the failing test**

`tests/knowledge/test_embedder.py`:

```python
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
```

`tests/knowledge/test_store_add.py`:

```python
from __future__ import annotations
from datetime import datetime
from knowledge.embedder import Embedder
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore


def fake_embed(texts):
    return [[float(len(t)), 1.0] for t in texts]


def make_store(tmp_path, embed_fn=fake_embed):
    settings = KnowledgeSettings(root=tmp_path)
    return KnowledgeStore(settings, embedder=Embedder("test-model", embed_fn=embed_fn))


def make_obj(dedup_text="quiet luxury basics"):
    return ContentObject(
        page="slayhack", kind="article", title="T", summary="S", body="B",
        dedup_text=dedup_text, created_at=datetime(2026, 5, 19),
    )


def test_add_writes_note_index_and_vector(tmp_path):
    store = make_store(tmp_path)
    obj = store.add(make_obj())
    assert obj.uid
    assert (tmp_path / "vault" / "08 Knowledge" / "slayhack" / "article" / f"{obj.uid}.md").exists()
    assert store.index.get(obj.uid) is not None
    assert store.index.get_vector(obj.uid) is not None  # embedded online


def test_add_offline_leaves_vector_pending(tmp_path):
    def broken(texts):
        raise ConnectionError("offline")
    store = make_store(tmp_path, embed_fn=broken)
    obj = store.add(make_obj())
    assert store.index.get(obj.uid) is not None      # note + index written
    assert store.index.get_vector(obj.uid) is None    # vector still pending
    assert obj.uid in store.index.pending_uids()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/knowledge/test_embedder.py tests/knowledge/test_store_add.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'knowledge.embedder'`

- [ ] **Step 3: Write minimal implementation**

`knowledge/embedder.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Sequence

EmbedFn = Callable[[Sequence[str]], list[list[float]]]


class OfflineError(Exception):
    """Raised when embeddings cannot be produced because the network is down."""


def openai_embed_fn(model: str, api_key: str) -> EmbedFn:
    """Build a real embed function backed by the OpenAI API."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    def _embed(texts: Sequence[str]) -> list[list[float]]:
        resp = client.embeddings.create(model=model, input=list(texts))
        return [d.embedding for d in resp.data]

    return _embed


class Embedder:
    """Turns text into vectors. Offline-safe: network failures raise OfflineError."""

    def __init__(self, model: str, embed_fn: EmbedFn) -> None:
        self.model = model
        self._embed_fn = embed_fn

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            return self._embed_fn(texts)
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise OfflineError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — API errors also degrade gracefully
            raise OfflineError(str(exc)) from exc
```

`knowledge/store.py`:

```python
from __future__ import annotations

from knowledge.embedder import Embedder, OfflineError
from knowledge.index import Index
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.vault import VaultWriter


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
```

`knowledge/__init__.py`:

```python
from __future__ import annotations

from knowledge.store import KnowledgeStore

__all__ = ["KnowledgeStore"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/knowledge/ -v`
Expected: PASS (all tests so far)

- [ ] **Step 5: Commit**

```bash
ruff check knowledge/ && mypy knowledge/
git add knowledge/embedder.py knowledge/store.py knowledge/__init__.py tests/knowledge/test_embedder.py tests/knowledge/test_store_add.py
git commit -m "feat(knowledge): add Embedder and KnowledgeStore.add (vault->index->embed)"
```

---

## ⛔ CHECKPOINT 1 — STOP

Hand back to the Captain. Report: `knowledge/` package created; `ContentObject`, settings,
`VaultWriter`, SQLite `Index`, `Embedder`, and `KnowledgeStore.add` are implemented and
tested. Run `pytest tests/knowledge/ -v` and paste the summary. **Wait for approval before Task 6.**

---

# CHECKPOINT 2 — Logic layer (Tasks 6–9)

---

### Task 6: DedupChecker

**Files:**
- Create: `knowledge/dedup.py`
- Test: `tests/knowledge/test_dedup.py`

`DedupChecker` returns near-duplicate matches classified `STRONG` (same page, above
strong threshold) or `SOFT` (other page, above soft threshold). Online it uses cosine
similarity; offline it falls back to FTS5 keyword hits (reported as SOFT, unscored).

- [ ] **Step 1: Write the failing test**

`tests/knowledge/test_dedup.py`:

```python
from __future__ import annotations
from datetime import datetime
from knowledge.dedup import DedupChecker, DedupMatch
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/knowledge/test_dedup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'knowledge.dedup'`

- [ ] **Step 3: Write minimal implementation**

`knowledge/dedup.py`:

```python
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from knowledge.embedder import OfflineError
from knowledge.store import KnowledgeStore


@dataclass
class DedupMatch:
    uid: str
    level: str           # "STRONG" or "SOFT"
    score: float | None  # cosine similarity, or None for keyword fallback
    page: str
    suggestion: str


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class DedupChecker:
    """Finds near-duplicates of a candidate and classifies STRONG / SOFT."""

    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store
        self.settings = store.settings

    def check(self, dedup_text: str, page: str, kind: str,
              online: bool = True) -> list[DedupMatch]:
        if online:
            try:
                return self._check_vector(dedup_text, page)
            except OfflineError:
                pass
        return self._check_keyword(dedup_text, page)

    def _check_vector(self, dedup_text: str, page: str) -> list[DedupMatch]:
        candidate = self.store.embedder.embed([dedup_text])[0]
        matches: list[DedupMatch] = []
        for uid, other_page, vector in self.store.index.all_vectors():
            score = cosine(candidate, vector)
            same_page = other_page == page
            if same_page and score >= self.settings.strong_threshold:
                matches.append(DedupMatch(
                    uid, "STRONG", score, other_page,
                    f"Very close to {uid} — extend it (set parent_uids=['{uid}'])."))
            elif not same_page and score >= self.settings.soft_threshold:
                matches.append(DedupMatch(
                    uid, "SOFT", score, other_page,
                    f"Page '{other_page}' already covered {uid} — reference it."))
        matches.sort(key=lambda m: m.score or 0.0, reverse=True)
        return matches

    def _check_keyword(self, dedup_text: str, page: str) -> list[DedupMatch]:
        terms = [t for t in re.findall(r"\w+", dedup_text.lower()) if len(t) > 2]
        if not terms:
            return []
        query = " OR ".join(terms)
        matches: list[DedupMatch] = []
        for uid in self.store.index.fts_search(query):
            row = self.store.index.get(uid)
            if row is None:
                continue
            same_page = row["page"] == page
            level = "STRONG" if same_page else "SOFT"
            matches.append(DedupMatch(
                uid, level, None, row["page"],
                f"Keyword-similar to {uid} (offline check — verify when online)."))
        return matches
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/knowledge/test_dedup.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add knowledge/dedup.py tests/knowledge/test_dedup.py
git commit -m "feat(knowledge): add DedupChecker with cosine and keyword fallback"
```

---

### Task 7: Retrieval API on KnowledgeStore

**Files:**
- Modify: `knowledge/store.py` (add methods to `KnowledgeStore`)
- Test: `tests/knowledge/test_retrieval.py`

Add `check_duplicate`, `get`, `search`, `recent`, and `lineage` to `KnowledgeStore`.

- [ ] **Step 1: Write the failing test**

`tests/knowledge/test_retrieval.py`:

```python
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


def add(store, dedup_text, parent_uids=None):
    obj = ContentObject(page="slayhack", kind="article", title=dedup_text,
                        summary="S", body="B", dedup_text=dedup_text,
                        parent_uids=parent_uids or [], created_at=datetime(2026, 5, 19))
    return store.add(obj)


def test_get_returns_object(tmp_path):
    store = make_store(tmp_path)
    added = add(store, "quiet luxury basics")
    got = store.get(added.uid)
    assert got is not None and got.uid == added.uid and got.title == "quiet luxury basics"


def test_get_missing_returns_none(tmp_path):
    assert make_store(tmp_path).get("nope") is None


def test_search_finds_by_keyword(tmp_path):
    store = make_store(tmp_path)
    a = add(store, "quiet luxury wardrobe")
    add(store, "loud streetwear noise")
    hits = store.search("luxury")
    assert a.uid in [o.uid for o in hits]


def test_recent_returns_newest_first(tmp_path):
    store = make_store(tmp_path)
    first = add(store, "first article topic")
    second = add(store, "second article topic")
    recent = store.recent(page="slayhack", kind="article", limit=10)
    uids = [o.uid for o in recent]
    assert set(uids) >= {first.uid, second.uid}


def test_lineage_walks_parents(tmp_path):
    store = make_store(tmp_path)
    root = add(store, "root topic")
    child = add(store, "child topic", parent_uids=[root.uid])
    lineage = store.lineage(child.uid)
    assert [o.uid for o in lineage] == [child.uid, root.uid]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/knowledge/test_retrieval.py -v`
Expected: FAIL — `AttributeError: 'KnowledgeStore' object has no attribute 'get'`

- [ ] **Step 3: Write minimal implementation**

Add these methods to the `KnowledgeStore` class in `knowledge/store.py` (append inside the class, after `add`). Also add `from pathlib import Path` and `from knowledge.dedup import DedupChecker, DedupMatch` to the imports:

```python
    def check_duplicate(self, dedup_text: str, page: str, kind: str,
                        online: bool = True) -> list["DedupMatch"]:
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
        clauses, params = [], []
        if page:
            clauses.append("page=?"); params.append(page)
        if kind:
            clauses.append("kind=?"); params.append(kind)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/knowledge/test_retrieval.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add knowledge/store.py tests/knowledge/test_retrieval.py
git commit -m "feat(knowledge): add retrieval API (check_duplicate/get/search/recent/lineage)"
```

---

### Task 8: rebuild_index

**Files:**
- Modify: `knowledge/store.py` (add `rebuild_index` to `KnowledgeStore`)
- Test: `tests/knowledge/test_rebuild.py`

`rebuild_index` discards the index and reconstructs it from vault notes — sweeping
orphan rows and reconciling human-edited notes (vault is truth).

- [ ] **Step 1: Write the failing test**

`tests/knowledge/test_rebuild.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/knowledge/test_rebuild.py -v`
Expected: FAIL — `AttributeError: 'KnowledgeStore' object has no attribute 'rebuild_index'`

- [ ] **Step 3: Write minimal implementation**

Add this method to `KnowledgeStore` in `knowledge/store.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/knowledge/test_rebuild.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add knowledge/store.py tests/knowledge/test_rebuild.py
git commit -m "feat(knowledge): add rebuild_index with orphan sweep and edit reconcile"
```

---

### Task 9: drain_pending (CP2 close)

**Files:**
- Modify: `knowledge/index.py` (add `mark_model_mismatch_pending`)
- Modify: `knowledge/store.py` (add `drain_pending` to `KnowledgeStore`)
- Test: `tests/knowledge/test_drain.py`

`drain_pending` embeds objects whose vector is still pending. It is resumable: if the
network drops mid-drain, already-embedded objects keep their vectors. It first reconciles
the embedding model — vectors stored under a different `embed_model` are marked pending so
they get re-embedded (spec decision D12: a model change must not silently break dedup).

- [ ] **Step 1: Write the failing test**

`tests/knowledge/test_drain.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/knowledge/test_drain.py -v`
Expected: FAIL — `AttributeError: 'KnowledgeStore' object has no attribute 'drain_pending'`

- [ ] **Step 3: Write minimal implementation**

First add this method to the `Index` class in `knowledge/index.py`:

```python
    def mark_model_mismatch_pending(self, current_model: str) -> int:
        """Mark vectors embedded under a different model as pending. Returns the count."""
        cur = self.conn.execute(
            "UPDATE vectors SET pending=1 WHERE embed_model IS NOT NULL "
            "AND embed_model != ?",
            (current_model,),
        )
        self.conn.commit()
        return cur.rowcount
```

Then add this method to `KnowledgeStore` in `knowledge/store.py`:

```python
    def drain_pending(self) -> int:
        """Embed objects whose vector is still pending. Returns the count embedded.

        Resumable: each object is committed individually, so a mid-drain network
        failure leaves already-embedded objects done and the rest still pending.
        Vectors stored under a different embed model are reconciled to pending first
        (spec D12), so changing the embedding model never silently breaks dedup.
        """
        self.index.mark_model_mismatch_pending(self.embedder.model)
        embedded = 0
        for uid in self.index.pending_uids():
            row = self.index.get(uid)
            if row is None:
                continue
            try:
                vector = self.embedder.embed([row["dedup_text"]])[0]
            except OfflineError:
                break  # stop; the rest stay pending for a later run
            self.index.set_vector(uid, self.embedder.model, vector)
            embedded += 1
        return embedded
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/knowledge/ -v`
Expected: PASS (all tests so far)

- [ ] **Step 5: Commit**

```bash
ruff check knowledge/ && mypy knowledge/
git add knowledge/store.py tests/knowledge/test_drain.py
git commit -m "feat(knowledge): add resumable drain_pending for offline embeddings"
```

---

## ⛔ CHECKPOINT 2 — STOP

Hand back to the Captain. Report: dedup classification (STRONG/SOFT + offline keyword
fallback), full retrieval API, `rebuild_index`, and `drain_pending` are implemented and
tested. Run `pytest tests/knowledge/ -v` and paste the summary. **Wait for approval before Task 10.**

---

# CHECKPOINT 3 — Backfill + tests (Tasks 10–13)

---

### Task 10: Backfill importer

**Files:**
- Create: `knowledge/backfill.py`
- Test: `tests/knowledge/test_backfill.py`

`backfill()` scans `output/<page>/<job_id>/` directories, builds `ContentObject`s from the
artifact files, and imports them. `dry_run=True` returns a report without writing.

Existing output layout (see CLAUDE.md): `output/<page_name>/<job_id>/` containing
`script.md`, `ideas.md`, `growth.md`, `image.png`, `video.mp4`, `job.json`.

- [ ] **Step 1: Write the failing test**

`tests/knowledge/test_backfill.py`:

```python
from __future__ import annotations
from knowledge.backfill import backfill
from knowledge.embedder import Embedder
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore


def fake_embed(texts):
    return [[float(len(t)), 1.0] for t in texts]


def make_store(tmp_path):
    return KnowledgeStore(KnowledgeSettings(root=tmp_path),
                          embedder=Embedder("m", embed_fn=fake_embed))


def seed_output(tmp_path):
    job = tmp_path / "output" / "Slayhack" / "20260512_143022"
    job.mkdir(parents=True)
    (job / "script.md").write_text("# Quiet Luxury Script\nHook body cta.", encoding="utf-8")
    (job / "ideas.md").write_text("Idea: minimalist wardrobe.", encoding="utf-8")
    return tmp_path / "output"


def test_dry_run_reports_without_writing(tmp_path):
    seed_output(tmp_path)
    store = make_store(tmp_path)
    report = backfill(store, output_root=tmp_path / "output", dry_run=True)
    assert report.found == 2
    assert store.index.all_uids() == []  # nothing written


def test_backfill_imports_artifacts(tmp_path):
    seed_output(tmp_path)
    store = make_store(tmp_path)
    report = backfill(store, output_root=tmp_path / "output", dry_run=False)
    assert report.imported == 2
    assert len(store.index.all_uids()) == 2


def test_backfill_is_idempotent(tmp_path):
    seed_output(tmp_path)
    store = make_store(tmp_path)
    backfill(store, output_root=tmp_path / "output", dry_run=False)
    backfill(store, output_root=tmp_path / "output", dry_run=False)
    assert len(store.index.all_uids()) == 2  # no duplicates on second run
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/knowledge/test_backfill.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'knowledge.backfill'`

- [ ] **Step 3: Write minimal implementation**

`knowledge/backfill.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from knowledge.object import ContentObject
from knowledge.store import KnowledgeStore

# maps an output artifact filename to a content kind
_ARTIFACT_KINDS = {
    "script.md": "video",
    "ideas.md": "idea",
    "growth.md": "caption",
    "faq.md": "caption",
    "article.md": "article",
}


@dataclass
class BackfillReport:
    found: int = 0
    imported: int = 0
    items: list[str] = field(default_factory=list)


def _parse_job_dir(job_dir: Path, page: str) -> list[ContentObject]:
    """Build ContentObjects from one output/<page>/<job_id>/ directory."""
    objs: list[ContentObject] = []
    # job_id looks like 20260512_143022 -> use its date for created_at
    try:
        created = datetime.strptime(job_dir.name.split("_")[0], "%Y%m%d")
    except ValueError:
        created = datetime.now()
    for artifact, kind in _ARTIFACT_KINDS.items():
        f = job_dir / artifact
        if not f.exists():
            continue
        body = f.read_text(encoding="utf-8", errors="replace")
        title = body.lstrip("#").strip().splitlines()[0][:80] if body.strip() else artifact
        objs.append(ContentObject(
            page=page, kind=kind, title=title, summary=title,
            body=body, dedup_text=f"{title} {body[:200]}",
            status="done", created_at=created,
        ))
    return objs


def backfill(store: KnowledgeStore, output_root: Path,
             dry_run: bool = False) -> BackfillReport:
    """Import existing output/ artifacts into the Knowledge Store.

    With dry_run=True, scans and reports without writing anything.
    Idempotent: uids are derived from content, so re-running adds no duplicates.
    """
    report = BackfillReport()
    if not output_root.exists():
        return report

    existing = set(store.index.all_uids())
    for page_dir in sorted(p for p in output_root.iterdir() if p.is_dir()):
        page = page_dir.name.lower()
        for job_dir in sorted(p for p in page_dir.iterdir() if p.is_dir()):
            for obj in _parse_job_dir(job_dir, page):
                obj.assign_uid(taken=existing)
                report.found += 1
                report.items.append(f"{obj.kind}: {obj.title}")
                if obj.uid in existing:
                    continue
                if not dry_run:
                    store.add(obj, embed=False)  # leave embeddings pending — drain later
                    report.imported += 1
                existing.add(obj.uid)
    return report
```

**Note:** Backfill imports notes + index rows but passes `embed=False`, so a bulk import
does not fire a burst of embedding API calls. Vectors stay pending; run
`python -m knowledge.cli drain` afterwards (or let the scheduled drain catch up) to embed
them gradually. `store.add` re-derives the uid via `assign_uid` from stable content, so a
re-run produces the same uid — the `existing` set guards against duplicate imports.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/knowledge/test_backfill.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add knowledge/backfill.py tests/knowledge/test_backfill.py
git commit -m "feat(knowledge): add backfill importer with dry-run report"
```

---

### Task 11: CLI entrypoints

**Files:**
- Create: `knowledge/cli.py`
- Test: `tests/knowledge/test_cli.py`

A small `argparse` CLI: `python -m knowledge.cli rebuild | backfill [--dry-run] | drain`.

- [ ] **Step 1: Write the failing test**

`tests/knowledge/test_cli.py`:

```python
from __future__ import annotations
from datetime import datetime
from knowledge.cli import main
from knowledge.embedder import Embedder
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore


def fake_embed(texts):
    return [[float(len(t)), 1.0] for t in texts]


def make_store(tmp_path):
    return KnowledgeStore(KnowledgeSettings(root=tmp_path),
                          embedder=Embedder("m", embed_fn=fake_embed))


def test_cli_rebuild_runs(tmp_path, capsys):
    store = make_store(tmp_path)
    obj = ContentObject(page="slayhack", kind="article", title="T", summary="S",
                        body="B", dedup_text="topic", created_at=datetime(2026, 5, 19))
    store.add(obj)
    rc = main(["rebuild"], store=store)
    assert rc == 0
    assert "1" in capsys.readouterr().out


def test_cli_backfill_dry_run(tmp_path, capsys):
    store = make_store(tmp_path)
    (tmp_path / "output" / "Slayhack" / "20260512_1").mkdir(parents=True)
    (tmp_path / "output" / "Slayhack" / "20260512_1" / "ideas.md").write_text(
        "an idea", encoding="utf-8")
    rc = main(["backfill", "--dry-run"], store=store, output_root=tmp_path / "output")
    assert rc == 0
    assert "dry-run" in capsys.readouterr().out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/knowledge/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'knowledge.cli'`

- [ ] **Step 3: Write minimal implementation**

`knowledge/cli.py`:

```python
from __future__ import annotations

import argparse
import os
from pathlib import Path

from knowledge.backfill import backfill
from knowledge.embedder import Embedder, openai_embed_fn
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore


def _default_store() -> KnowledgeStore:
    root = Path.cwd()
    settings = KnowledgeSettings.from_env(root=root)
    settings.vault_subdir = Path("vaults/NayzFreedom Vault")
    api_key = os.getenv("OPENAI_API_KEY", "")
    embed_fn = openai_embed_fn(settings.embed_model, api_key)
    return KnowledgeStore(settings, embedder=Embedder(settings.embed_model, embed_fn))


def main(argv: list[str] | None = None, store: KnowledgeStore | None = None,
         output_root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(prog="knowledge")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("rebuild", help="rebuild knowledge.db from the vault")
    bf = sub.add_parser("backfill", help="import existing output/ artifacts")
    bf.add_argument("--dry-run", action="store_true")
    sub.add_parser("drain", help="embed pending objects")
    args = parser.parse_args(argv)

    store = store or _default_store()

    if args.command == "rebuild":
        count = store.rebuild_index()
        print(f"rebuilt index: {count} notes")
        return 0
    if args.command == "backfill":
        root = output_root or (store.settings.root / "output")
        report = backfill(store, output_root=root, dry_run=args.dry_run)
        mode = "dry-run" if args.dry_run else "import"
        print(f"backfill ({mode}): found {report.found}, imported {report.imported}")
        for item in report.items:
            print(f"  - {item}")
        return 0
    if args.command == "drain":
        count = store.drain_pending()
        print(f"drained: {count} embeddings")
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/knowledge/test_cli.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add knowledge/cli.py tests/knowledge/test_cli.py
git commit -m "feat(knowledge): add CLI for rebuild/backfill/drain"
```

---

### Task 12: Golden corpus + calibration script

**Files:**
- Create: `tests/knowledge/golden_corpus.yaml`
- Create: `scripts/calibrate_dedup.py`
- Test: `tests/knowledge/test_golden_corpus.py`

The golden corpus is a labeled set of content pairs. The calibration script reports
false-positive / false-negative rates so the Captain can tune thresholds.

- [ ] **Step 1: Write the failing test**

`tests/knowledge/test_golden_corpus.py`:

```python
from __future__ import annotations
from pathlib import Path
import yaml
from scripts.calibrate_dedup import evaluate

CORPUS = Path(__file__).parent / "golden_corpus.yaml"


def test_corpus_is_well_formed():
    pairs = yaml.safe_load(CORPUS.read_text(encoding="utf-8"))
    assert len(pairs) >= 15
    for p in pairs:
        assert set(p) >= {"a", "b", "same_page", "expected"}
        assert p["expected"] in ("STRONG", "SOFT", "none")


def test_evaluate_returns_rates():
    # a perfect classifier returning the labeled answer scores zero error
    pairs = yaml.safe_load(CORPUS.read_text(encoding="utf-8"))
    result = evaluate(pairs, classify=lambda a, b, same_page: _label(pairs, a, b))
    assert result["false_positive"] == 0
    assert result["false_negative"] == 0


def _label(pairs, a, b):
    for p in pairs:
        if p["a"] == a and p["b"] == b:
            return p["expected"]
    return "none"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/knowledge/test_golden_corpus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.calibrate_dedup'`

- [ ] **Step 3: Write minimal implementation**

`tests/knowledge/golden_corpus.yaml` — create 18 labeled pairs. Use realistic SlayHack
content (Thai + English). Each entry: `a` and `b` are `dedup_text` strings, `same_page`
is a bool, `expected` is `STRONG` / `SOFT` / `none`:

```yaml
- {a: "Quiet luxury wardrobe essentials for fall", b: "Essential quiet-luxury pieces for autumn", same_page: true, expected: STRONG}
- {a: "Quiet luxury wardrobe essentials for fall", b: "Essential quiet-luxury pieces for autumn", same_page: false, expected: SOFT}
- {a: "How to build a capsule wardrobe", b: "Capsule wardrobe starter guide", same_page: true, expected: STRONG}
- {a: "How to build a capsule wardrobe", b: "Loud streetwear sneaker drops 2026", same_page: true, expected: none}
- {a: "เทรนด์ quiet luxury สำหรับสาวออฟฟิศ", b: "quiet luxury ลุคสาวทำงาน", same_page: true, expected: STRONG}
- {a: "เทรนด์ quiet luxury สำหรับสาวออฟฟิศ", b: "รีวิวลิปสติกโทนนู้ด", same_page: true, expected: none}
- {a: "Minimalist skincare routine for glass skin", b: "Glass-skin minimal skincare steps", same_page: true, expected: STRONG}
- {a: "Minimalist skincare routine for glass skin", b: "Glass-skin minimal skincare steps", same_page: false, expected: SOFT}
- {a: "Best neutral-tone handbags under budget", b: "Affordable beige and tan handbags", same_page: true, expected: STRONG}
- {a: "Best neutral-tone handbags under budget", b: "Bold neon party clutches", same_page: true, expected: none}
- {a: "5 ways to style a white shirt", b: "White shirt styling ideas", same_page: true, expected: STRONG}
- {a: "5 ways to style a white shirt", b: "How to fold a fitted sheet", same_page: true, expected: none}
- {a: "Old money aesthetic explained", b: "What is the old-money look", same_page: true, expected: STRONG}
- {a: "Old money aesthetic explained", b: "What is the old-money look", same_page: false, expected: SOFT}
- {a: "Investing basics for women in their 20s", b: "Beginner investing guide for young women", same_page: true, expected: STRONG}
- {a: "Investing basics for women in their 20s", b: "Quiet luxury fall wardrobe", same_page: true, expected: none}
- {a: "Linen summer dresses roundup", b: "Best linen dresses for summer", same_page: true, expected: STRONG}
- {a: "Linen summer dresses roundup", b: "Winter wool coat care tips", same_page: true, expected: none}
```

`scripts/calibrate_dedup.py`:

```python
from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import yaml

# classifier signature: (text_a, text_b, same_page) -> "STRONG" | "SOFT" | "none"
Classifier = Callable[[str, str, bool], str]


def evaluate(pairs: list[dict], classify: Classifier) -> dict[str, float]:
    """Compare a classifier's output to the labeled corpus.

    false_positive: predicted a match (STRONG/SOFT) where expected was none.
    false_negative: predicted none where a match was expected.
    """
    fp = fn = 0
    for p in pairs:
        predicted = classify(p["a"], p["b"], p["same_page"])
        expected = p["expected"]
        pred_match = predicted != "none"
        exp_match = expected != "none"
        if pred_match and not exp_match:
            fp += 1
        if exp_match and not pred_match:
            fn += 1
    total = len(pairs) or 1
    return {
        "total": total,
        "false_positive": fp,
        "false_negative": fn,
        "false_positive_rate": fp / total,
        "false_negative_rate": fn / total,
    }


def _main() -> int:  # pragma: no cover — manual calibration tool
    corpus = Path(__file__).parent.parent / "tests" / "knowledge" / "golden_corpus.yaml"
    pairs = yaml.safe_load(corpus.read_text(encoding="utf-8"))
    from knowledge.dedup import cosine
    from knowledge.embedder import Embedder, openai_embed_fn
    import os

    embed_fn = openai_embed_fn("text-embedding-3-small", os.environ["OPENAI_API_KEY"])
    embedder = Embedder("text-embedding-3-small", embed_fn)
    strong = float(os.getenv("KNOWLEDGE_STRONG_THRESHOLD", "0.82"))
    soft = float(os.getenv("KNOWLEDGE_SOFT_THRESHOLD", "0.68"))

    def classify(a: str, b: str, same_page: bool) -> str:
        va, vb = embedder.embed([a, b])
        score = cosine(va, vb)
        if same_page and score >= strong:
            return "STRONG"
        if not same_page and score >= soft:
            return "SOFT"
        return "none"

    result = evaluate(pairs, classify)
    print(f"thresholds: strong={strong} soft={soft}")
    for k, v in result.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
```

**Note:** create an empty `scripts/__init__.py` if `scripts/` is not yet a package, so
`from scripts.calibrate_dedup import evaluate` resolves in tests.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/knowledge/test_golden_corpus.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/knowledge/golden_corpus.yaml tests/knowledge/test_golden_corpus.py scripts/calibrate_dedup.py scripts/__init__.py
git commit -m "feat(knowledge): add golden corpus and dedup calibration script"
```

---

### Task 13: End-to-end acceptance test (CP3 close)

**Files:**
- Test: `tests/knowledge/test_acceptance.py`

One test exercises the whole lifecycle. When it is green, SP-0 is done.

- [ ] **Step 1: Write the failing test**

`tests/knowledge/test_acceptance.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/knowledge/test_acceptance.py -v`
Expected: it may fail only if a prior task is incomplete. If all prior tasks passed, this
should PASS immediately — that is acceptable for an acceptance test. If it fails, fix the
underlying component, do not weaken the test.

- [ ] **Step 3: Verify the full suite**

Run: `pytest tests/knowledge/ -v`
Expected: PASS — every knowledge test green.

- [ ] **Step 4: Quality gates**

Run: `ruff check knowledge/ scripts/ tests/knowledge/ && mypy knowledge/`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add tests/knowledge/test_acceptance.py
git commit -m "test(knowledge): add end-to-end acceptance test for SP-0"
```

---

## ⛔ CHECKPOINT 3 — STOP (SP-0 complete)

Hand back to the Captain. Report:
- Full `knowledge/` package implemented and tested; `pytest tests/knowledge/ -v` summary.
- Backfill ran against real `output/` in `--dry-run` first — paste that report for review
  before a real import is approved.
- SP-0 acceptance test green = definition of done met.

Then await direction on SP-1 (Scout).

---

## Notes for the executor

- **Never weaken a test to make it pass.** If a test fails, fix the component.
- **Embedding API:** real runs use `openai_embed_fn`; every test injects a fake `embed_fn`. Do not call the network in tests.
- **`knowledge.db`:** add `knowledge.db`, `knowledge.db-wal`, `knowledge.db-shm` to `.gitignore` before the first commit that can create it (do this in Task 4's commit).
- **Vault path:** tests use `KnowledgeSettings(root=tmp_path)` (vault at `tmp_path/vault/`). Production uses `vault_subdir=Path("vaults/NayzFreedom Vault")` — wired in `knowledge/cli.py`.
- **Scheduled embedding drain (spec D13):** `python -m knowledge.cli drain` is the entrypoint for the daily scheduled drain. After Task 11, add a cron line (mirroring the existing scheduler/reporter cron entries in CLAUDE.md), e.g. `30 6 * * * /path/to/.venv/bin/python -m knowledge.cli drain`. Per-operation "lazy" drain is intentionally deferred — confirm with the Captain whether it is wanted before adding it.
- **Out of scope (do not build):** auto-posting, Notion sync, Drive backup wiring, dashboard surfacing, personal/music content. Those are later sub-projects.
- **Drive backup (spec §6):** the spec includes a versioned Drive backup of the vault. It is intentionally NOT in this plan — it is a thin `google_drive.py` + cron wrapper, peripheral to the store itself. Treat it as a small follow-on (SP-0.1) pending the Captain's go-ahead.
```
