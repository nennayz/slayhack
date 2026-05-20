from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from knowledge.object import ContentObject, make_uid
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
                stable_uid = make_uid(obj.page, obj.kind, obj.created_at, obj.dedup_text)
                report.found += 1
                report.items.append(f"{obj.kind}: {obj.title}")
                if stable_uid in existing:
                    continue
                obj.assign_uid(taken=existing)
                if not dry_run:
                    store.add(obj, embed=False)  # leave embeddings pending — drain later
                    report.imported += 1
                existing.add(obj.uid)
    return report
