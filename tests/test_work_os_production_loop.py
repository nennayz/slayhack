from __future__ import annotations

from unittest.mock import MagicMock, patch

from knowledge.embedder import Embedder
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore
from models.content_job import ContentJob, JobStatus
from models.work_os import PlanContentType, ProductionTicket, TicketStatus
from work_os_store import load_tickets, save_tickets


def test_production_loop_prefers_work_os_ticket(tmp_path):
    from production_loop import run_production_loop

    settings = KnowledgeSettings(root=tmp_path)
    store = KnowledgeStore(settings, Embedder("test", embed_fn=lambda texts: [[0.0] * 4 for _ in texts]))
    ticket = ProductionTicket(
        plan_id="plan-1",
        page="nayzfreedom_fleet",
        ticket_type=PlanContentType.SHORT_VIDEO,
        brief="Create the ticket-first video prompt pack.",
    )
    save_tickets(tmp_path, [ticket])
    config = MagicMock()
    captured: list[ContentJob] = []

    def success(job: ContentJob, **kwargs: object) -> ContentJob:
        captured.append(job)
        job.status = JobStatus.COMPLETED
        return job

    with patch("production_loop.Orchestrator") as MockOrch:
        MockOrch.return_value.run.side_effect = success
        result = run_production_loop("nayzfreedom_fleet", config, store, dry_run=True, output_root=tmp_path)

    assert result.tickets_found == 1
    assert result.jobs_started == 1
    assert result.jobs_completed == 1
    assert captured[0].production_ticket is not None
    assert captured[0].production_ticket["id"] == ticket.id
    assert load_tickets(tmp_path)[0].status == TicketStatus.DONE
