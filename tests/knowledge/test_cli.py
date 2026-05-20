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
