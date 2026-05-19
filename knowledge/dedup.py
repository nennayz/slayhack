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
