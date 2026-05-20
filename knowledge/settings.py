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
