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
