from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ks_to_content_job import idea_to_content_job
from orchestrator import Orchestrator
from project_loader import load_project

if TYPE_CHECKING:
    from config import Config
    from knowledge.store import KnowledgeStore

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent


@dataclass
class ProductionLoopResult:
    page_slug: str
    ideas_found: int = 0
    jobs_started: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0


def run_production_loop(
    page_slug: str,
    config: "Config",
    store: "KnowledgeStore",
    dry_run: bool = False,
    output_root: Path | None = None,
) -> ProductionLoopResult:
    result = ProductionLoopResult(page_slug=page_slug)

    approved = store.recent(kind="idea", page=page_slug, status="approved",
                             limit=1, order="asc")
    result.ideas_found = len(approved)
    if not approved:
        logger.info("Production loop: no approved ideas for %s", page_slug)
        return result

    idea = approved[0]
    logger.info("Production loop: starting job for idea=%s page=%s", idea.uid, page_slug)

    try:
        pm = load_project(page_slug)
    except Exception as exc:
        logger.error("Production loop: could not load project %s: %s", page_slug, exc)
        return result

    job = idea_to_content_job(idea, pm, dry_run=dry_run)
    store.set_status(idea.uid, "in_production")
    result.jobs_started += 1

    try:
        orchestrator = Orchestrator(config)
        orchestrator.run(job, unattended=True)
        result.jobs_completed += 1
        logger.info("Production loop: completed job=%s idea=%s", job.id, idea.uid)
    except Exception as exc:
        logger.error("Production loop: job failed idea=%s: %s", idea.uid, exc)
        store.set_status(idea.uid, "approved")
        result.jobs_failed += 1

    return result
