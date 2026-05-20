from __future__ import annotations
import json
import logging
from datetime import datetime
from pathlib import Path

from config import Config
from agents.trend_scout import TrendScoutAgent
from knowledge.store import KnowledgeStore
from knowledge.object import ContentObject
from models.trend_scan_job import TrendHit, TrendScanJob, TrendScanJobStatus
from project_loader import load_scout_seed_topics

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent
_OUTPUT_ROOT = _ROOT / "output"


def run_trend_scout_pipeline(
    page_slug: str,
    config: Config,
    store: KnowledgeStore,
    dry_run: bool = False,
    output_root: Path = _OUTPUT_ROOT,
) -> TrendScanJob:
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    job = TrendScanJob(job_id=job_id, page_slug=page_slug, triggered_by="pipeline")

    seed_topics = load_scout_seed_topics(page_slug)
    if not seed_topics:
        logger.info("No scout_seed_topics for %s — skipping trend scan", page_slug)
        job.status = TrendScanJobStatus.COMPLETED
        return job

    job.status = TrendScanJobStatus.RUNNING
    date_str = datetime.now().strftime("%Y%m%d")

    agent = TrendScoutAgent(config)
    hits = agent.scan(seed_topics, dry_run=dry_run)
    job.signals_found = len(hits)

    for hit in hits:
        obj = _hit_to_content_object(hit, page_slug, date_str)
        matches = store.check_duplicate(obj.dedup_text, obj.page, obj.kind)
        if any(match.level == "STRONG" and (match.score is None or match.score >= 0.82) for match in matches):
            job.signals_skipped += 1
            logger.debug("Skipping dup trend signal: %s", hit.topic)
            continue
        store.add(obj, embed=True)
        job.signals_stored += 1

    digest_path = write_trend_digest(hits, page_slug, output_root, date_str)
    job.digest_path = str(digest_path)
    job.status = TrendScanJobStatus.COMPLETED
    return job


def _hit_to_content_object(hit: TrendHit, page_slug: str, date_str: str) -> ContentObject:
    source_keys = [str(key) for key in hit.sources]
    body = (
        f"## Trend Signal\n\n"
        f"**Topic:** {hit.topic}  \n"
        f"**Direction:** {hit.direction}  \n"
        f"**Score:** {hit.score:.1f}/100  \n\n"
        f"### Metadata\n\n"
        f"- Topic: {hit.topic}\n"
        f"- Direction: {hit.direction}\n"
        f"- Score: {hit.score:.1f}\n\n"
        f"### Sources\n\n"
        f"```json\n{json.dumps(hit.sources, indent=2, default=str)[:2000]}\n```\n"
    )
    return ContentObject(
        page=page_slug,
        kind="trend_signal",
        title=f"{hit.topic} — {hit.direction}",
        body=body,
        dedup_text=f"{hit.topic}|{page_slug}|{date_str}",
        tags=[hit.direction, page_slug] + source_keys,
    )


def write_trend_digest(
    hits: list[TrendHit],
    page_slug: str,
    output_root: Path,
    date_str: str,
) -> Path:
    digest_dir = output_root / page_slug / "scout" / date_str
    digest_dir.mkdir(parents=True, exist_ok=True)
    digest_path = digest_dir / "trend_digest.md"

    sorted_hits = sorted(hits, key=lambda h: h.score, reverse=True)
    lines = [
        f"# Trend Digest — {page_slug} — {date_str}\n\n",
        "| # | Topic | Direction | Score |\n",
        "|---|---|---|---|\n",
    ]
    for i, hit in enumerate(sorted_hits, 1):
        lines.append(f"| {i} | {hit.topic} | {hit.direction} | {hit.score:.1f} |\n")
    lines.append("\n---\n\n")
    for hit in sorted_hits:
        lines.append(f"## {hit.topic}\n\n- **Direction:** {hit.direction}\n- **Score:** {hit.score:.1f}/100\n\n")

    digest_path.write_text("".join(lines), encoding="utf-8")
    logger.info("Trend digest written to %s", digest_path)
    return digest_path
