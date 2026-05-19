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
