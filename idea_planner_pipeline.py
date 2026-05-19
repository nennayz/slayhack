from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agents.idea_planner import IdeaPlannerAgent
from knowledge.object import ContentObject
from models.idea_plan_job import IdeaDraft, IdeaPlanJob, IdeaPlanJobStatus
from project_loader import load_project

if TYPE_CHECKING:
    from config import Config
    from knowledge.store import KnowledgeStore

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent
_OUTPUT_ROOT = _ROOT / "output"


def run_idea_planner_pipeline(
    page_slug: str,
    config: "Config",
    store: "KnowledgeStore",
    dry_run: bool = False,
    output_root: Path | None = None,
) -> IdeaPlanJob:
    _output_root = output_root if output_root is not None else _OUTPUT_ROOT
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    job = IdeaPlanJob(job_id=job_id, page_slug=page_slug, triggered_by="pipeline")
    job.status = IdeaPlanJobStatus.RUNNING
    date_str = datetime.now().strftime("%Y%m%d")

    try:
        pm = load_project(page_slug)
        brand = {
            "page_slug": page_slug,
            "mission": pm.brand.mission,
            "tone": pm.brand.tone,
            "target_audience": pm.brand.target_audience,
            "script_style": pm.brand.script_style,
        }
    except Exception as exc:
        logger.warning("IdeaPlanner: could not load brand profile for %s: %s — using empty", page_slug, exc)
        brand = {"page_slug": page_slug}

    recent_signals = store.recent(kind="trend_signal", page=page_slug, limit=10)
    job.signals_used = len(recent_signals)
    if not recent_signals:
        logger.warning("IdeaPlanner: no trend signals in KS for %s — brand-only context", page_slug)

    recent_ideas = store.recent(kind="idea", page=page_slug, limit=30)

    signals_dicts = [
        {"title": o.title, "direction": _extract_direction(o), "score": _extract_score(o)}
        for o in recent_signals
    ]
    ideas_dicts = [{"title": o.title} for o in recent_ideas]

    agent = IdeaPlannerAgent(config)
    drafts = agent.generate(signals=signals_dicts, recent_ideas=ideas_dicts, brand=brand, dry_run=dry_run)
    job.ideas_generated = len(drafts)

    for draft in drafts:
        obj = _draft_to_content_object(draft, page_slug, date_str, recent_signals)
        if _has_exact_duplicate(store, obj):
            job.ideas_skipped += 1
            logger.debug("Skipping exact dup idea: %s", draft.title)
            continue
        matches = store.check_duplicate(obj.dedup_text, obj.page, obj.kind)
        if matches and matches[0].score is not None and matches[0].score >= store.settings.strong_threshold:
            job.ideas_skipped += 1
            logger.debug("Skipping dup idea: %s", draft.title)
            continue
        store.add(obj, embed=True)
        job.ideas_stored += 1

    digest_path = write_idea_digest(drafts, page_slug, _output_root, date_str)
    job.digest_path = str(digest_path)
    job.status = IdeaPlanJobStatus.COMPLETED
    return job


def _has_exact_duplicate(store: "KnowledgeStore", obj: ContentObject) -> bool:
    rows = store.index.conn.execute(
        "SELECT uid FROM notes WHERE page=? AND kind=? AND dedup_text=? LIMIT 1",
        (obj.page, obj.kind, obj.dedup_text),
    ).fetchall()
    return bool(rows)


def _draft_to_content_object(
    draft: IdeaDraft,
    page_slug: str,
    date_str: str,
    recent_signals: list[ContentObject],
) -> ContentObject:
    signal_uids = draft.source_signal_uids or [o.uid for o in recent_signals[:3] if o.uid]
    source_summary = "\n".join(f"- {o.title} ({o.uid})" for o in recent_signals[:3]) or "- Brand-context fallback"
    body = (
        f"## {draft.title}\n\n"
        f"**Hook:** {draft.hook}\n\n"
        f"**Angle:** {draft.angle}\n\n"
        f"**Content type:** {draft.content_type}\n\n"
        "### Source signals\n"
        f"{source_summary}\n"
    )
    return ContentObject(
        page=page_slug,
        kind="idea",
        title=draft.title,
        body=body,
        dedup_text=f"{draft.title}|{draft.hook}|{page_slug}|{date_str}",
        tags=[draft.content_type, draft.angle, page_slug],
        parent_uids=signal_uids,
        status="new",
    )


def _extract_direction(obj: ContentObject) -> str:
    for tag in obj.tags:
        if tag in ("rising", "stable", "declining", "unknown"):
            return tag
    return "unknown"


def _extract_score(obj: ContentObject) -> float:
    for tag in obj.tags:
        if tag.startswith("score:"):
            try:
                return float(tag[6:])
            except ValueError:
                pass
    return 0.0


def write_idea_digest(
    drafts: list[IdeaDraft],
    page_slug: str,
    output_root: Path,
    date_str: str,
) -> Path:
    digest_dir = output_root / page_slug / "ideas" / date_str
    digest_dir.mkdir(parents=True, exist_ok=True)
    digest_path = digest_dir / "idea_digest.md"

    lines = [
        f"# Idea Digest — {page_slug} — {date_str}\n\n",
        "| # | Title | Hook | Angle | Type |\n",
        "|---|---|---|---|---|\n",
    ]
    for i, d in enumerate(drafts, 1):
        lines.append(f"| {i} | {_escape_table(d.title)} | {_escape_table(d.hook[:60])} | {_escape_table(d.angle)} | {_escape_table(d.content_type)} |\n")
    lines.append("\n---\n\n")
    for d in drafts:
        lines.append(
            f"## {d.title}\n\n"
            f"**Hook:** {d.hook}\n\n"
            f"**Angle:** {d.angle} | **Type:** {d.content_type}\n\n"
        )

    digest_path.write_text("".join(lines), encoding="utf-8")
    logger.info("Idea digest written to %s", digest_path)
    return digest_path


def _escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
