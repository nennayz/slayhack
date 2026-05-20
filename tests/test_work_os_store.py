from __future__ import annotations

from knowledge.embedder import Embedder
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore
from models.work_os import PlanStatus, SlateStatus, TicketStatus
from work_os_store import (
    create_ticket_for_plan,
    create_today_slate,
    load_plans,
    load_slates,
    load_tickets,
    save_plans,
    sync_approved_ideas_into_planner,
    update_plan_status,
    update_slate_status,
)


def _store(root):
    return KnowledgeStore(
        KnowledgeSettings(root=root),
        Embedder("test", embed_fn=lambda texts: [[0.0] * 4 for _ in texts]),
    )


def _idea(page: str, title: str, status: str = "approved") -> ContentObject:
    return ContentObject(
        page=page,
        kind="idea",
        title=title,
        summary="A save-worthy approved idea for a short viral test.",
        dedup_text=f"{page}:{title}",
        status=status,
        tags=["video", "save"],
    )


def test_sync_approved_ideas_creates_idempotent_content_plan(tmp_path):
    store = _store(tmp_path)
    approved = store.add(_idea("nayzfreedom_fleet", "Approved hook"), embed=False)
    store.add(_idea("nayzfreedom_fleet", "Rejected hook", status="rejected"), embed=False)

    plans, created = sync_approved_ideas_into_planner(tmp_path, store)
    assert created == 1
    assert len(plans) == 1
    assert plans[0].source_idea_uid == approved.uid
    assert plans[0].status == PlanStatus.DRAFT
    assert plans[0].content_type.value == "short_video"

    plans_again, created_again = sync_approved_ideas_into_planner(tmp_path, store)
    assert created_again == 0
    assert [plan.source_idea_uid for plan in plans_again] == [approved.uid]

    mirrored = store.recent(kind="content_plan", status="draft", limit=10)
    assert len(mirrored) == 1
    assert mirrored[0].parent_uids == [approved.uid]


def test_plan_review_slate_and_ticket_lifecycle(tmp_path):
    store = _store(tmp_path)
    store.add(_idea("nayzfreedom_fleet", "Lifecycle hook"), embed=False)
    plans, _ = sync_approved_ideas_into_planner(tmp_path, store)
    plan = plans[0]

    assert create_ticket_for_plan(tmp_path, plan.id) is None
    approved = update_plan_status(tmp_path, plan.id, PlanStatus.APPROVED)
    assert approved is not None
    assert approved.status == PlanStatus.APPROVED

    slate = create_today_slate(tmp_path, page="nayzfreedom_fleet")
    assert slate is not None
    assert slate.status == SlateStatus.DRAFT
    assert plan.id in slate.plan_ids
    reviewed = update_slate_status(tmp_path, slate.id, SlateStatus.APPROVED)
    assert reviewed is not None
    assert reviewed.status == SlateStatus.APPROVED

    ticket = create_ticket_for_plan(tmp_path, plan.id)
    assert ticket is not None
    assert ticket.status == TicketStatus.QUEUED
    assert ticket.plan_id == plan.id
    assert load_plans(tmp_path)[0].status == PlanStatus.TICKETED
    assert load_slates(tmp_path)[0].status == SlateStatus.APPROVED
    assert load_tickets(tmp_path)[0].id == ticket.id


def test_save_plan_reload_preserves_existing_plans(tmp_path):
    store = _store(tmp_path)
    store.add(_idea("nayzfreedom_fleet", "First"), embed=False)
    plans, _ = sync_approved_ideas_into_planner(tmp_path, store)
    save_plans(tmp_path, plans)
    store.add(_idea("nayzfreedom_fleet", "Second"), embed=False)

    updated, created = sync_approved_ideas_into_planner(tmp_path, store)
    assert created == 1
    assert len(updated) == 2
