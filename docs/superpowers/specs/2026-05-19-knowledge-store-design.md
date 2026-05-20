# SP-0 — Knowledge Store Design

**Date:** 2026-05-19
**Status:** Approved by Captain (Nayz) — ready for implementation planning
**Sub-project:** SP-0, the foundation of the NayzFreedom Fleet system redesign
**Author / Lead:** Claude (architect). Implementation to be executed by a separate agent from this spec + its companion implementation plan.

---

## 1. Context

The NayzFreedom Fleet content system is being redesigned for simplicity and stability.
The user's brief describes a work system that — once reframed — is **one content
lifecycle riding on a shared backbone**, plus parallel tracks:

```
Layer A (backbone) : KNOWLEDGE STORE              ← this spec (SP-0)
Layer B (pipeline) : Scout → Idea/Content Planning → Production Loop → Social Packaging → Auto-post
Layer C (daily)    : Daily Ops (Bubble Message + Comment Reply)
Tracks             : Monetize/Affiliate ; Personal Secretary
```

The full redesign is decomposed into sub-projects SP-0 … SP-7 plus a Personal track.
**This spec covers SP-0 only.** SP-0 is built first because every other sub-project
reads from and writes to it; a stable backbone makes the rest "not messy" by default.

SP-0 directly answers the user's requirement: *do not produce duplicate content;
branch and extend instead; retrieve stored content accurately by ID.*

### Relationship to the existing codebase

Design is fresh, but implementation **evolves the existing repo** — it is not a
greenfield rewrite. Reuse where sensible:
- `google_drive.py` — for the Drive backup of the vault.
- `job_store.py` patterns — JSON/file persistence conventions.
- Existing `pytest` setup and `output/<page>/<job_id>/` artifacts — the backfill source.
- The Obsidian vault at `vaults/NayzFreedom Vault/` — becomes the canonical store.

The nautical "Fleet" theme is a final cosmetic skin and is **out of scope** for SP-0.

---

## 2. Approved decisions

Every item below was explicitly approved by the Captain during brainstorming.

| # | Decision |
|---|----------|
| D1 | **Dedup behavior:** semantic-similarity detection that *warns and suggests how to extend* — never blocks. |
| D2 | **Canonical store:** the Obsidian vault. Notes are the source of truth. |
| D3 | **Index:** a derived, disposable SQLite file behind the vault (Approach A). |
| D4 | **Scope of content:** the whole pipeline — trend, idea, plan, article, image, video, caption. |
| D5 | **Dedup scope:** strong warning within the same page; soft warning across pages. |
| D6 | **Backfill:** import all existing content (`output/` + vault) at setup time. |
| D7 | `kind` is an **open string**, not a fixed enum (so SP-1…SP-6 can add kinds with no schema migration). |
| D8 | `status` uses one **small generic set**: `new` / `approved` / `done` / `archived` / `rejected`. |
| D9 | Each object carries an explicit **`dedup_text`** — the text used for similarity. |
| D10 | Lineage is a **graph**: `parent_uids` is a list, not a single parent. |
| D11 | SP-0 stores **work pages only**. Personal/music content gets a separate namespaced store later. |
| D12 | Embedding vectors store their **`embed_model`**; a model mismatch marks the vector `pending`. |
| D13 | The `pending_embedding` queue is **drained automatically** (lazily on any online op + a daily scheduled task). |
| D14 | **Human edits to vault notes are authoritative** — the store re-indexes from them, never overwrites. |
| D15 | **No hard delete.** `archived` is a soft-delete that stays in dedup memory; `rebuild_index` sweeps rows whose note no longer exists. |
| D16 | Similarity **thresholds live in config**; a calibration script reports false-positive/negative rates against a golden corpus. |
| D17 | `backfill` has a **`--dry-run`** report mode that previews the import plan before writing. |
| D18 | One **end-to-end acceptance test** is the single "definition of done" for SP-0. |

---

## 3. Content Object — the shared contract

Every artifact in the pipeline is represented by one schema. This is the contract
all current and future sub-projects use when talking to the Knowledge Store.

| Field | Type | Meaning |
|-------|------|---------|
| `uid` | str | Unique id: `<page>-<kind>-<YYYYMMDD>-<hash4>`, e.g. `slayhack-article-20260519-a3f9`. `<YYYYMMDD>` is the object's `created_at` date (not "today"), so backfill is stable. `hash4` = first 4 hex chars of a hash of `dedup_text`; collision-checked on insert. |
| `page` | str | Page slug. Defines dedup scope. |
| `kind` | str | Open string. Known set: `trend`, `idea`, `plan`, `article`, `image`, `video`, `caption`. New sub-projects may add values. |
| `title` | str | Short human title. |
| `summary` | str | One-paragraph summary. |
| `body` | str | Full content. For `image`/`video`, the description + the production prompt. |
| `dedup_text` | str | The exact text used for similarity matching. The producer sets it explicitly (article → title+summary; image → prompt; idea → angle). |
| `status` | str | One of `new` / `approved` / `done` / `archived` / `rejected`. |
| `parent_uids` | list[str] | UIDs this object was extended/branched from. Empty for originals. |
| `tags` | list[str] | Free tags. |
| `created_at` | datetime | Creation timestamp (ISO 8601). |
| `vault_path` | str | Path to the `.md` note in the Obsidian vault. Used to open/read. |
| `asset_path` | str \| null | Path to the real binary file for `image`/`video`. Binaries are never embedded in markdown. |

The object is persisted as a Markdown note with YAML frontmatter carrying every
structured field; `body` is the note's markdown content.

### Vault layout

```
vaults/NayzFreedom Vault/08 Knowledge/<page>/<kind>/<uid>.md   ← canonical notes
knowledge.db                                                   ← SQLite index (repo root, gitignored, NOT in vault, NOT synced)
```

`08 Knowledge` is a new top-level vault folder (existing folders are `00`–`07`, `99`).

---

## 4. Architecture & components

Principle: **the vault is truth; the index is derived and disposable.** If the index
is lost or corrupt, `rebuild_index` reconstructs it entirely from the vault.

| Component | Responsibility | Depends on |
|-----------|----------------|------------|
| **Content Object** | The shared schema (section 3). A Pydantic model. | — |
| **Vault Writer** | Writes/updates a Content Object as a `.md` note with YAML frontmatter. | vault filesystem |
| **Index** | `knowledge.db` (SQLite, WAL mode): a metadata table, an FTS5 full-text table, and a vectors table. Mirrors the vault. | SQLite (stdlib) |
| **Embedder** | Turns `dedup_text` into a vector via the embedding API; caches vectors keyed by `(content_hash, embed_model)`. | embedding API |
| **Dedup Checker** | Given a candidate, returns similar existing objects scored and classified STRONG / SOFT / none. | Index, Embedder |
| **Retrieval API** | `get(uid)`, `search(query, page, kind)`, `recent(page, kind)`, `lineage(uid)`. | Index |
| **Backfill Importer** | One-time scan of `output/` + existing vault content into Content Objects, notes, and index rows. Has `--dry-run`. | Vault Writer, Index, Embedder |

The public surface other sub-projects use:
`store.add(object)`, `store.check_duplicate(dedup_text, page, kind)`,
`store.get(uid)`, `store.search(...)`, `store.recent(...)`, `store.lineage(uid)`,
`store.rebuild_index()`, `store.drain_pending()`.

---

## 5. Data flows

### A. Write (a pipeline agent produced something)

```
agent produces content → store.add(object)
  1. Vault Writer writes <uid>.md + YAML frontmatter        ← truth committed first
  2. Index upserts metadata row + FTS5 row
  3. Embedder: online → embed + cache ; offline → set pending_embedding flag
```

Write order is always **vault → index → embedding**. A failure at a later step
leaves earlier steps intact and recoverable.

### B. Duplicate check (before producing — the core feature)

```
agent has a candidate → store.check_duplicate(dedup_text, page, kind)
  online  : cosine similarity over vectors
  offline : FTS5 keyword match (coarser, never fully broken)
  → results classified:
       same page  → STRONG  "very close to <uid> — extend it instead"
       other page → SOFT    "page X already did <uid> — reference it"
  → never blocks; returns matches + suggested parent_uids for the producer/human to decide
```

Similarity thresholds for STRONG/SOFT come from config (see D16).

### C. Retrieval (Captain reads work)

```
store.get(uid)                    → returns vault_path → open in Obsidian
store.search(query, page, kind)   → vector search (online) / FTS5 (offline)
store.recent(page, kind)          → latest objects
store.lineage(uid)                → walks parent_uids → the "extended from" graph
```

### D. Backfill (one-time, at setup)

```
scan output/<page>/<job>/ + existing vault notes
  → build Content Objects (infer kind/page from path)
  → write notes into 08 Knowledge/, build index, queue embeddings in capped batches
  → idempotent: re-running yields the same state (uid is stable, derived from content hash)
  → `backfill --dry-run` reports the plan ("found N items, M look mutually duplicate, import plan: …")
    without writing anything
```

---

## 6. Offline / sync / error handling

### Offline-first

Everything is a local file; only the Embedder needs network.

| Situation | Behavior |
|-----------|----------|
| Online | embed + cache vectors → full semantic dedup |
| Offline, new content | write vault + index + FTS5 immediately; set `pending_embedding` |
| Offline, dedup check | fall back to FTS5 keyword match — degraded, never fully broken |
| Back online | `pending_embedding` queue drained automatically (lazy on next online op + daily scheduled task) |

### Sync / backup

- **Obsidian Sync** handles the vault across devices — the Knowledge Store does not interfere.
- **Google Drive** = secondary backup: scheduled, versioned (timestamped snapshots, not a destructive mirror) sync of the vault, reusing `google_drive.py`.
- `knowledge.db` is **never** synced or committed — derived, per-device, rebuildable. Add to `.gitignore`; keep it outside the vault.
- **Notion** is skipped (YAGNI); may be added later as a read-only view.

### Error handling — "no single point kills the whole job"

| Failure | Handling |
|---------|----------|
| Embedding API fails / times out | short retry → still failing: set `pending_embedding`, continue. Job never dies. |
| Index corrupt / lost | `rebuild_index` scans the vault and rebuilds `knowledge.db` whole. |
| `embed_model` mismatch | vector treated as `pending`; `rebuild_index` can re-embed. |
| UID collision | near-impossible; uniqueness checked on insert. On a real collision (different content, same `<page>-<kind>-<date>-<hash4>`) the hash is deterministically extended (more hex chars) until unique — identical content still always yields the identical uid, so backfill stays idempotent. |
| Concurrent writes | SQLite WAL mode; vault notes are one file per object — no overwrite contention. |
| Vault written, index failed | vault is truth — next `rebuild_index` reconciles. |
| Note edited outside the store (human edit in Obsidian) | store detects hash mismatch → re-indexes from the note, never overwrites it. |
| Content deleted | `archived` = soft-delete, stays in dedup memory. Note removed from vault → `rebuild_index` sweeps the orphan row. |

---

## 7. Testing requirements

Tests verify **behavior**, not just compilation. All run with a mock embedder — no
live API calls. `pytest`, consistent with the existing project setup.

| Test group | Proves |
|------------|--------|
| Dedup classification | Labeled near/far content pairs classified STRONG/SOFT/none correctly; same-page vs cross-page split correct. |
| Backfill idempotent | Running backfill twice → identical state (stable uids, no duplicate notes). |
| Index rebuild | Delete `knowledge.db`, `rebuild_index` → index matches pre-delete state row-for-row. |
| Offline degrade | Mock embedder unavailable → content still written, `pending_embedding` set, dedup check falls back to FTS5. |
| Pending drain | Pending items embedded once online; queue empties; partial drain (online drops mid-drain) is resumable with no double-embed. |
| Embed model versioning | Vectors with non-matching `embed_model` treated as pending and re-embeddable. |
| Human-edit detection | Note edited outside the store → store re-indexes from it, does not overwrite. |
| Vault-first recovery | Simulated index failure mid-write → vault note intact; `rebuild_index` recovers. |
| Soft-delete | `archived` items still appear in dedup memory; notes removed from vault are swept by `rebuild_index`. |
| UID collision | Forced hash collision → uniqueness check catches it, re-hash. |

### Test fixtures & calibration

- **Golden corpus:** ~15–20 real-ish content pairs (Thai + English), each labeled with
  the expected STRONG / SOFT / none outcome. Serves as the dedup regression suite.
- **Calibration script:** runs the golden corpus against the configured thresholds and
  reports false-positive / false-negative rates so the Captain can tune. Thresholds
  live in config, never hardcoded.

### Definition of done

A single **end-to-end acceptance test** exercises the full lifecycle:
`add → check_duplicate → get/search → archive → rebuild_index`, asserting correct
state at each step. When this test is green, SP-0 is complete. The executor agent
uses this as the unambiguous completion signal.

---

## 8. Out of scope for SP-0

- Personal / music (Freedom, Lyra) content — separate namespaced store later (D11).
- Notion integration.
- The Fleet nautical theme / dashboard surfacing of the store.
- Any pipeline logic (Scout, Production, etc.) — those are SP-1 onward and merely
  *consume* this store's public API.

---

## 9. Build sequence (for the implementation plan)

Suggested order for the executor agent (the companion implementation plan will detail each):

1. Content Object model + UID scheme.
2. Vault Writer (note read/write + frontmatter, human-edit hash detection).
3. Index: SQLite schema (metadata + FTS5 + vectors), WAL mode.
4. Embedder + vector cache + `pending_embedding` queue.
5. Dedup Checker (vector + FTS5 fallback, STRONG/SOFT classification, config thresholds).
6. Retrieval API (`get` / `search` / `recent` / `lineage`).
7. `rebuild_index` + `drain_pending`.
8. Backfill Importer + `--dry-run`.
9. Golden corpus + calibration script.
10. Full test suite + the end-to-end acceptance test.
