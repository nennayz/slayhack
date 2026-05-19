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
