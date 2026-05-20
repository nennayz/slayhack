from __future__ import annotations

from knowledge.embedder import Embedder
from knowledge.object import ContentObject
from knowledge.settings import KnowledgeSettings
from knowledge.store import KnowledgeStore
from models.work_os import ContentPlan, ContentSlate, PlanStatus, ProductionTicket, ReviewStatus, SlateStatus, TicketStatus
from work_os_store import (
    build_daily_work_brief,
    create_ticket_for_plan,
    create_today_slate,
    export_manual_publish_checklist,
    load_plans,
    load_slates,
    load_tickets,
    publish_queue_rows,
    save_plans,
    sync_approved_ideas_into_planner,
    update_plan_status,
    update_publish_review,
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


def _plan(page: str = "nayzfreedom_fleet", status: PlanStatus = PlanStatus.DRAFT) -> ContentPlan:
    return ContentPlan(
        page=page,
        hook="Daily brief hook",
        angle="Daily brief angle",
        production_brief="Daily brief production brief",
        status=status,
    )


def test_daily_brief_next_action_prefers_draft_plan_review(tmp_path):
    plan = _plan(status=PlanStatus.DRAFT)
    save_plans(tmp_path, [plan])

    brief = build_daily_work_brief(tmp_path)

    assert brief.next_best_action is not None
    assert brief.next_best_action.label == "Review draft plans"
    assert brief.next_best_action.href == "/aurora/planner"
    assert brief.next_best_action.count == 1
    assert any(section.key == "draft_plans_waiting_review" and section.item_count == 1 for section in brief.sections)


def test_daily_brief_recommends_slate_for_approved_plan_without_today_slate(tmp_path):
    plan = _plan(status=PlanStatus.APPROVED)
    save_plans(tmp_path, [plan])

    brief = build_daily_work_brief(tmp_path)

    assert brief.next_best_action is not None
    assert brief.next_best_action.label == "Create today's slate"
    assert brief.next_best_action.count == 1


def test_daily_brief_recommends_approving_draft_slate_before_ticket(tmp_path):
    plan = _plan(status=PlanStatus.APPROVED)
    save_plans(tmp_path, [plan])
    slate = create_today_slate(tmp_path, page=plan.page)
    assert slate is not None

    brief = build_daily_work_brief(tmp_path)

    assert brief.next_best_action is not None
    assert brief.next_best_action.label == "Approve today's slate"
    assert brief.next_best_action.count == 1


def test_daily_brief_recommends_ticket_after_approved_slate(tmp_path):
    plan = _plan(status=PlanStatus.APPROVED)
    save_plans(tmp_path, [plan])
    slate = ContentSlate(
        page=plan.page,
        daily_focus="Approved daily focus",
        plan_ids=[plan.id],
        status=SlateStatus.APPROVED,
    )
    from work_os_store import save_slates

    save_slates(tmp_path, [slate])

    brief = build_daily_work_brief(tmp_path)

    assert brief.next_best_action is not None
    assert brief.next_best_action.label == "Create production tickets"
    assert brief.next_best_action.count == 1


def test_daily_brief_recommends_queued_ticket_and_survives_reload(tmp_path):
    plan = _plan(status=PlanStatus.TICKETED)
    ticket = ProductionTicket(
        plan_id=plan.id,
        page=plan.page,
        ticket_type=plan.content_type,
        brief=plan.production_brief,
        status=TicketStatus.QUEUED,
    )
    save_plans(tmp_path, [plan])
    from work_os_store import save_tickets

    save_tickets(tmp_path, [ticket])

    brief = build_daily_work_brief(tmp_path)
    reloaded = build_daily_work_brief(tmp_path)

    assert brief.next_best_action is not None
    assert brief.next_best_action.label == "Run or review queued production"
    assert reloaded.next_best_action is not None
    assert reloaded.next_best_action.label == "Run or review queued production"
    assert any(section.key == "queued_production_tickets" and section.item_count == 1 for section in reloaded.sections)


def test_daily_brief_recommends_publish_queue_after_production_queue(tmp_path):
    queue = tmp_path / "output" / "publish_queue.jsonl"
    queue.parent.mkdir(parents=True)
    queue.write_text('{"package_uid": "pkg-brief", "caption": "ready for review"}\n')

    brief = build_daily_work_brief(tmp_path)

    assert brief.next_best_action is not None
    assert brief.next_best_action.label == "Review publish queue"
    assert brief.next_best_action.href == "/aurora/publish-queue"
    assert any(section.key == "publish_queue_pending_review" and section.item_count == 1 for section in brief.sections)


def test_daily_brief_empty_state_does_not_seed_work_objects(tmp_path):
    brief = build_daily_work_brief(tmp_path)

    assert brief.next_best_action is not None
    assert brief.next_best_action.label == "Sync planner or scout for the next idea"
    assert load_plans(tmp_path) == []
    assert load_slates(tmp_path) == []
    assert load_tickets(tmp_path) == []
    assert any("Live auto-posting remains locked" in risk for risk in brief.risks)


def test_publish_queue_rows_include_filters_lineage_and_manual_checklist(tmp_path):
    queue = tmp_path / "output" / "publish_queue.jsonl"
    queue.parent.mkdir(parents=True)
    queue.write_text(
        '{"package_uid": "pkg-pending", "job_id": "job-1", "ticket_id": "ticket-1", '
        '"plan_id": "plan-1", "platforms": ["facebook", "instagram"], '
        '"caption": "caption one", "hashtags": ["#one"], "asset_path": "output/asset-one.mp4"}\n'
        '{"package_uid": "pkg-approved", "job_id": "job-2", "platform": "facebook", '
        '"post_text": "caption two", "asset": "output/asset-two.png"}\n'
    )
    update_publish_review(tmp_path, "pkg-approved", ReviewStatus.APPROVED, "safe manual handoff")

    all_rows = publish_queue_rows(tmp_path)
    pending_rows = publish_queue_rows(tmp_path, status_filter="pending")
    approved_rows = publish_queue_rows(tmp_path, status_filter="approved")

    assert [row["package_id"] for row in all_rows] == ["pkg-pending", "pkg-approved"]
    assert [row["package_id"] for row in pending_rows] == ["pkg-pending"]
    assert [row["package_id"] for row in approved_rows] == ["pkg-approved"]
    assert pending_rows[0]["platforms"] == ["facebook", "instagram"]
    assert "ticket: ticket-1" in pending_rows[0]["lineage"]
    assert "plan: plan-1" in pending_rows[0]["lineage"]
    assert any("no live API" in item for item in pending_rows[0]["manual_checklist"])
    assert approved_rows[0]["review_note"] == "safe manual handoff"


def test_export_manual_publish_checklist_is_local_handoff_only(tmp_path):
    queue = tmp_path / "output" / "publish_queue.jsonl"
    queue.parent.mkdir(parents=True)
    queue.write_text(
        '{"package_uid": "pkg-checklist", "job_id": "job-check", '
        '"caption": "manual caption", "hashtags": ["#manual"], "asset_path": "output/manual.mp4"}\n'
    )

    checklist = export_manual_publish_checklist(tmp_path)

    assert "# Manual Publish Checklist" in checklist
    assert "Live publish APIs remain locked" in checklist
    assert "pkg-checklist" in checklist
    assert "manual caption" in checklist
    assert "#manual" in checklist
    assert "job: job-check" in checklist
    assert "- [ ] Post manually only after Captain review" in checklist
