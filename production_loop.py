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


def _work_os_root(output_root: Path | None) -> Path:
    if output_root is None:
        return _ROOT
    return output_root.parent if output_root.name == "output" else output_root


@dataclass
class ProductionLoopResult:
    page_slug: str
    ideas_found: int = 0
    tickets_found: int = 0
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

    try:
        from models.content_job import ContentJob, ContentType, JobStatus
        from models.work_os import PlanContentType, TicketStatus
        from work_os_store import load_tickets, save_tickets

        store_root = _work_os_root(output_root)
        tickets = load_tickets(store_root)
        queued = [ticket for ticket in tickets if ticket.page == page_slug and ticket.status == TicketStatus.QUEUED]
        result.tickets_found = len(queued)
        if queued:
            ticket = queued[0]
            try:
                pm = load_project(page_slug)
            except Exception as exc:
                logger.error("Production loop: could not load project %s: %s", page_slug, exc)
                return result
            content_map = {
                PlanContentType.ARTICLE: ContentType.ARTICLE,
                PlanContentType.IMAGE: ContentType.IMAGE,
                PlanContentType.INFOGRAPHIC: ContentType.INFOGRAPHIC,
                PlanContentType.SHORT_VIDEO: ContentType.VIDEO,
                PlanContentType.LONG_VIDEO: ContentType.VIDEO,
                PlanContentType.PROMPT_ONLY_VIDEO: ContentType.VIDEO,
                PlanContentType.BUBBLE: ContentType.ARTICLE,
            }
            job = ContentJob(
                project=page_slug,
                pm=pm,
                brief=ticket.brief,
                platforms=pm.brand.platforms or ["facebook", "instagram"],
                dry_run=dry_run,
                content_type=content_map.get(ticket.ticket_type, ContentType.VIDEO),
                production_ticket=ticket.model_dump(mode="json"),
            )
            ticket.status = TicketStatus.IN_PROGRESS
            save_tickets(store_root, tickets)
            result.jobs_started += 1
            try:
                orchestrator = Orchestrator(config)
                orchestrator.run(job, unattended=True)
                ticket.status = TicketStatus.DONE if job.status == JobStatus.COMPLETED else TicketStatus.QA_READY
                save_tickets(store_root, tickets)
                result.jobs_completed += 1
                logger.info("Production loop: completed ticket=%s page=%s", ticket.id, page_slug)
            except Exception as exc:
                logger.error("Production loop: ticket failed ticket=%s: %s", ticket.id, exc)
                ticket.status = TicketStatus.QUEUED
                save_tickets(store_root, tickets)
                result.jobs_failed += 1
            return result
    except Exception as exc:  # noqa: BLE001 - keep legacy approved-idea loop available if Work OS store is unavailable
        logger.warning("Production loop: Work OS ticket scan skipped: %s", exc)

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
