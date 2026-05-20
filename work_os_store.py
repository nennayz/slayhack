from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from collections.abc import Sequence
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

from models.work_os import (
    BubbleMessage,
    BubbleStatus,
    ContentPlan,
    ContentSlate,
    DailyWorkBrief,
    MonetizeOpportunity,
    PlanContentType,
    PlanStatus,
    ProductionTicket,
    PublishQueueReview,
    ReviewStatus,
    SlateStatus,
    TicketStatus,
    WorkObjective,
)
from project_loader import list_project_slugs, load_project

if TYPE_CHECKING:
    from knowledge.object import ContentObject
    from knowledge.store import KnowledgeStore

T = TypeVar("T", bound=BaseModel)


def _dir(root: Path) -> Path:
    path = root / "output" / "work_os"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_model_list(path: Path, model: type[T]) -> list[T]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        return []
    return [model.model_validate(item) for item in data]


def _write_model_list(path: Path, items: Sequence[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([item.model_dump(mode="json") for item in items], indent=2))


def load_plans(root: Path) -> list[ContentPlan]:
    return _read_model_list(_dir(root) / "content_plans.json", ContentPlan)


def save_plans(root: Path, items: list[ContentPlan]) -> None:
    _write_model_list(_dir(root) / "content_plans.json", items)


def load_slates(root: Path) -> list[ContentSlate]:
    return _read_model_list(_dir(root) / "content_slates.json", ContentSlate)


def save_slates(root: Path, items: list[ContentSlate]) -> None:
    _write_model_list(_dir(root) / "content_slates.json", items)


def load_tickets(root: Path) -> list[ProductionTicket]:
    return _read_model_list(_dir(root) / "production_tickets.json", ProductionTicket)


def save_tickets(root: Path, items: list[ProductionTicket]) -> None:
    _write_model_list(_dir(root) / "production_tickets.json", items)


def load_bubbles(root: Path) -> list[BubbleMessage]:
    return _read_model_list(_dir(root) / "bubble_messages.json", BubbleMessage)


def save_bubbles(root: Path, items: list[BubbleMessage]) -> None:
    _write_model_list(_dir(root) / "bubble_messages.json", items)


def load_monetize(root: Path) -> list[MonetizeOpportunity]:
    return _read_model_list(_dir(root) / "monetize_opportunities.json", MonetizeOpportunity)


def save_monetize(root: Path, items: list[MonetizeOpportunity]) -> None:
    _write_model_list(_dir(root) / "monetize_opportunities.json", items)


def load_publish_reviews(root: Path) -> list[PublishQueueReview]:
    return _read_model_list(_dir(root) / "publish_queue_reviews.json", PublishQueueReview)


def save_publish_reviews(root: Path, items: list[PublishQueueReview]) -> None:
    _write_model_list(_dir(root) / "publish_queue_reviews.json", items)



def _plan_dedup_key(idea: "ContentObject") -> str:
    return f"{idea.uid}:{idea.title}:{idea.summary}" if idea.uid else idea.dedup_text


def _content_type_from_idea(idea: "ContentObject") -> PlanContentType:
    tags = {tag.lower() for tag in idea.tags}
    text = f"{idea.title} {idea.summary} {idea.body}".lower()
    if "article" in tags or "guide" in tags or "บทความ" in text:
        return PlanContentType.ARTICLE
    if "image" in tags or "infographic" in tags or "ภาพ" in text:
        return PlanContentType.INFOGRAPHIC if "infographic" in tags else PlanContentType.IMAGE
    if "long_video" in tags or "long video" in text:
        return PlanContentType.LONG_VIDEO
    if "prompt_only_video" in tags or "prompt-only" in text:
        return PlanContentType.PROMPT_ONLY_VIDEO
    if "bubble" in tags or "status" in tags:
        return PlanContentType.BUBBLE
    return PlanContentType.SHORT_VIDEO


def _objective_from_idea(idea: "ContentObject") -> WorkObjective:
    tags = {tag.lower() for tag in idea.tags}
    text = f"{idea.title} {idea.summary} {idea.body}".lower()
    if "revenue" in tags or "monetize" in tags or "affiliate" in text or "ebook" in text:
        return WorkObjective.REVENUE
    if "save" in tags or "guide" in tags or "checklist" in text:
        return WorkObjective.SAVE
    if "community" in tags or "comment" in tags or "bubble" in tags:
        return WorkObjective.COMMUNITY
    if "learning" in tags:
        return WorkObjective.LEARNING
    return WorkObjective.REACH


def _platforms_for_page(root: Path, page: str) -> list[str]:
    try:
        project = load_project(page, root=root)
        return project.brand.platforms or ["facebook", "instagram"]
    except Exception:  # noqa: BLE001 - planner must degrade when project metadata is missing
        return ["facebook", "instagram"]


def plan_from_approved_idea(root: Path, idea: "ContentObject") -> ContentPlan:
    content_type = _content_type_from_idea(idea)
    objective = _objective_from_idea(idea)
    hook = idea.title.strip() or idea.summary.strip() or "Approved idea ready for planning"
    angle = idea.summary.strip() or idea.body.strip()[:240] or "Turn this approved idea into a practical page-native content plan."
    plan = ContentPlan(
        page=idea.page,
        source_idea_uid=idea.uid,
        pillar=(idea.tags[0] if idea.tags else "growth"),
        objective=objective,
        content_type=content_type,
        target_platforms=_platforms_for_page(root, idea.page)[:3],
        hook=hook,
        angle=angle,
        production_brief=(
            f"Create a {content_type.value} production brief from approved idea {idea.uid}: "
            f"hook={hook}; angle={angle[:180]}"
        ),
        publish_window="Manual best-time review from page cadence",
        status=PlanStatus.DRAFT,
        next_action="Captain approves/rejects this plan, then creates tickets for approved plans.",
    )
    return plan


def _mirror_work_os_object(store: "KnowledgeStore | None", obj: "ContentObject") -> None:
    if store is None:
        return
    try:
        store.add(obj, embed=False)
    except Exception:
        return


def sync_approved_ideas_into_planner(
    root: Path,
    store: "KnowledgeStore",
    limit: int = 50,
) -> tuple[list[ContentPlan], int]:
    from knowledge.object import ContentObject

    plans = load_plans(root)
    existing_sources = {plan.source_idea_uid for plan in plans if plan.source_idea_uid}
    created = 0
    for idea in store.recent(kind="idea", status="approved", limit=limit, order="asc"):
        if idea.uid in existing_sources:
            continue
        plan = plan_from_approved_idea(root, idea)
        plans.append(plan)
        existing_sources.add(idea.uid)
        created += 1
        _mirror_work_os_object(
            store,
            ContentObject(
                page=plan.page,
                kind="content_plan",
                title=plan.hook,
                summary=plan.angle,
                body=plan.production_brief,
                dedup_text=f"work_os:content_plan:{_plan_dedup_key(idea)}",
                status=plan.status.value,
                parent_uids=[idea.uid],
                tags=[plan.pillar, plan.objective.value, plan.content_type.value, "work_os"],
            ),
        )
    if created:
        save_plans(root, plans)
    return plans, created


def update_plan_status(root: Path, plan_id: str, status: PlanStatus) -> ContentPlan | None:
    plans = load_plans(root)
    for plan in plans:
        if plan.id == plan_id:
            plan.status = status
            plan.updated_at = datetime.now()
            if status == PlanStatus.APPROVED:
                plan.next_action = "Plan approved; add it to a slate or create a production ticket."
            elif status == PlanStatus.REJECTED:
                plan.next_action = "Rejected locally; keep for learning but do not produce."
            save_plans(root, plans)
            return plan
    return None


def create_today_slate(root: Path, page: str | None = None) -> ContentSlate | None:
    plans = load_plans(root)
    slates = load_slates(root)
    today = datetime.now().date()
    candidates = [
        plan for plan in plans
        if plan.status in {PlanStatus.APPROVED, PlanStatus.TICKETED}
        and (page is None or plan.page == page)
    ]
    if not candidates:
        return None
    target_page = page or candidates[0].page
    existing = next((slate for slate in slates if slate.page == target_page and slate.date == today), None)
    plan_ids = [plan.id for plan in candidates if plan.page == target_page]
    if existing is not None:
        existing.plan_ids = sorted(set(existing.plan_ids + plan_ids))
        existing.updated_at = datetime.now()
        save_slates(root, slates)
        return existing
    slate = ContentSlate(
        page=target_page,
        daily_focus="Produce approved plans through ticket-first Work OS flow; keep live publishing manual.",
        plan_ids=plan_ids,
        status=SlateStatus.DRAFT,
        next_action="Captain approves the slate, then tickets move into production.",
    )
    slates.append(slate)
    save_slates(root, slates)
    return slate


def update_slate_status(root: Path, slate_id: str, status: SlateStatus) -> ContentSlate | None:
    slates = load_slates(root)
    for slate in slates:
        if slate.id == slate_id:
            slate.status = status
            slate.updated_at = datetime.now()
            save_slates(root, slates)
            return slate
    return None


def seed_content_planner(root: Path) -> tuple[list[ContentPlan], list[ContentSlate], list[ProductionTicket]]:
    plans = load_plans(root)
    slates = load_slates(root)
    tickets = load_tickets(root)
    if plans or slates or tickets:
        return plans, slates, tickets

    slugs = list_project_slugs(root=root) or ["nayzfreedom_fleet"]
    created_plans: list[ContentPlan] = []
    created_slates: list[ContentSlate] = []
    created_tickets: list[ProductionTicket] = []
    for slug in slugs[:3]:
        try:
            project = load_project(slug, root=root)
            page_name = project.page_name
            platforms = project.brand.platforms or ["facebook", "instagram"]
            tone = project.brand.tone or "brand voice"
        except Exception:  # noqa: BLE001 - planner seed must degrade safely
            page_name = slug
            platforms = ["facebook", "instagram"]
            tone = "brand voice"
        page_plans = [
            ContentPlan(
                page=slug,
                pillar="viral-trust",
                objective=WorkObjective.REACH,
                content_type=PlanContentType.SHORT_VIDEO,
                target_platforms=platforms[:2],
                hook=f"{page_name}: stop the scroll with today's strongest practical hook",
                angle=f"Use {tone} to turn one trend into a useful short-video promise.",
                production_brief="Create a short-video brief with hook, beats, visual direction, CTA, and prompt-only fallback.",
                publish_window="Evening local platform review",
                status=PlanStatus.APPROVED,
            ),
            ContentPlan(
                page=slug,
                pillar="searchable-depth",
                objective=WorkObjective.SAVE,
                content_type=PlanContentType.ARTICLE,
                target_platforms=["facebook"],
                hook=f"{page_name}: turn the trend into a save-worthy guide",
                angle="Create one practical article that can feed future video and e-book lanes.",
                production_brief="Draft an article outline, key sections, source notes, CTA, and one supporting image prompt.",
                publish_window="Manual post after Captain review",
                status=PlanStatus.APPROVED,
            ),
            ContentPlan(
                page=slug,
                pillar="daily-presence",
                objective=WorkObjective.COMMUNITY,
                content_type=PlanContentType.BUBBLE,
                target_platforms=["facebook", "instagram"],
                hook=f"{page_name}: daily bubble/status prompt",
                angle="Keep the page alive with a short seasonal/story-driven status message.",
                production_brief="Write one bubble/status message matched to today, the page voice, and the active slate.",
                publish_window="Morning or lunch manual story/status",
                status=PlanStatus.APPROVED,
            ),
        ]
        created_plans.extend(page_plans)
        slate = ContentSlate(
            page=slug,
            daily_focus="Use one strong trend to create reach, depth, and community presence without live automation.",
            plan_ids=[plan.id for plan in page_plans],
            status=SlateStatus.APPROVED,
        )
        created_slates.append(slate)
        for plan in page_plans:
            created_tickets.append(ticket_from_plan(plan))
            plan.status = PlanStatus.TICKETED
            plan.next_action = "Production ticket created; run or review the ticket."
    save_plans(root, created_plans)
    save_slates(root, created_slates)
    save_tickets(root, created_tickets)
    return created_plans, created_slates, created_tickets


def ticket_from_plan(plan: ContentPlan) -> ProductionTicket:
    requirements = {
        PlanContentType.ARTICLE: ["outline", "body draft", "CTA", "supporting image prompt"],
        PlanContentType.IMAGE: ["visual prompt", "caption", "alt text"],
        PlanContentType.INFOGRAPHIC: ["points", "layout prompt", "caption"],
        PlanContentType.SHORT_VIDEO: ["hook", "script beats", "scene prompts", "caption"],
        PlanContentType.LONG_VIDEO: ["storyboard", "script", "scene prompts", "retention beats"],
        PlanContentType.PROMPT_ONLY_VIDEO: ["tool prompt", "negative prompt", "manual render notes"],
        PlanContentType.BUBBLE: ["bubble text", "story prompt", "posting note"],
    }
    criteria = [
        "Matches page voice and target audience.",
        "Has a concrete next action or CTA.",
        "Can be reviewed manually before publishing.",
    ]
    return ProductionTicket(
        plan_id=plan.id,
        page=plan.page,
        ticket_type=plan.content_type,
        brief=plan.production_brief,
        required_assets=requirements.get(plan.content_type, ["draft artifact"]),
        acceptance_criteria=criteria,
        status=TicketStatus.QUEUED,
    )


def create_ticket_for_plan(root: Path, plan_id: str) -> ProductionTicket | None:
    plans = load_plans(root)
    tickets = load_tickets(root)
    for ticket in tickets:
        if ticket.plan_id == plan_id:
            return ticket
    for plan in plans:
        if plan.id == plan_id:
            if plan.status not in {PlanStatus.APPROVED, PlanStatus.TICKETED}:
                return None
            ticket = ticket_from_plan(plan)
            tickets.append(ticket)
            plan.status = PlanStatus.TICKETED
            plan.next_action = "Production ticket created; run or review the ticket."
            plan.updated_at = datetime.now()
            save_plans(root, plans)
            save_tickets(root, tickets)
            return ticket
    return None


def update_publish_review(root: Path, package_id: str, status: ReviewStatus, note: str = "") -> PublishQueueReview:
    reviews = load_publish_reviews(root)
    found = next((item for item in reviews if item.package_id == package_id), None)
    if found is None:
        found = PublishQueueReview(package_id=package_id)
        reviews.append(found)
    found.status = status
    found.review_note = note
    found.reviewed_at = datetime.now()
    save_publish_reviews(root, reviews)
    return found


def publish_queue_rows(root: Path) -> list[dict[str, object]]:
    queue = root / "output" / "publish_queue.jsonl"
    reviews = {item.package_id: item for item in load_publish_reviews(root)}
    rows: list[dict[str, object]] = []
    if queue.exists():
        for idx, line in enumerate(queue.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                data = {"raw": line}
            package_id = str(data.get("package_uid") or data.get("package_id") or data.get("job_id") or f"queue-{idx}")
            review = reviews.get(package_id)
            rows.append({
                "package_id": package_id,
                "job_id": str(data.get("job_id") or ""),
                "platforms": data.get("platforms") or data.get("target_platforms") or [],
                "caption": str(data.get("caption") or data.get("body") or "")[:600],
                "hashtags": data.get("hashtags") or [],
                "asset_path": str(data.get("asset_path") or ""),
                "status": review.status.value if review else ReviewStatus.PENDING.value,
                "review_note": review.review_note if review else "",
            })
    return rows


def generate_bubbles(root: Path) -> list[BubbleMessage]:
    bubbles = load_bubbles(root)
    today = str(datetime.now().date())
    existing = {f"{item.page}:{item.date}" for item in bubbles}
    plans, slates, _ = seed_content_planner(root)
    for slate in slates:
        key = f"{slate.page}:{today}"
        if key in existing:
            continue
        page_plans = [plan for plan in plans if plan.id in slate.plan_ids]
        hook = page_plans[0].hook if page_plans else slate.daily_focus
        bubbles.append(BubbleMessage(
            page=slate.page,
            story_prompt=f"Turn today's focus into a casual Story/Bubble that tees up: {hook}",
            bubble_text=f"Today we are testing one tiny upgrade: {slate.daily_focus[:120]}",
            trend_context="Generated from the approved Work OS slate; Captain posts manually.",
            status=BubbleStatus.DRAFT,
        ))
    save_bubbles(root, bubbles)
    return bubbles


def seed_monetize(root: Path) -> list[MonetizeOpportunity]:
    opportunities = load_monetize(root)
    if opportunities:
        return opportunities
    plans, _, _ = seed_content_planner(root)
    pages = sorted({plan.page for plan in plans}) or ["nayzfreedom_fleet"]
    for page in pages:
        opportunities.append(MonetizeOpportunity(
            page=page,
            source="work_os_seed",
            audience_pain="Audience needs a practical transformation that can become a lead magnet or low-ticket product.",
            suggested_offer="Qualify one e-book or lead magnet from the strongest recurring content pillar before adding affiliate links.",
            matching_content_ids=[plan.id for plan in plans if plan.page == page][:3],
        ))
    save_monetize(root, opportunities)
    return opportunities


def build_daily_work_brief(root: Path) -> DailyWorkBrief:
    plans, slates, tickets = seed_content_planner(root)
    queue = publish_queue_rows(root)
    bubbles = generate_bubbles(root)
    monetize = seed_monetize(root)
    return DailyWorkBrief(
        focus="Run the Work OS loop manually: approve slate, move tickets, review publish packages, capture learning.",
        priorities=[
            f"Review {len(slates)} content slate(s).",
            f"Move {sum(1 for item in tickets if item.status == TicketStatus.QUEUED)} queued production ticket(s).",
            f"Review {sum(1 for row in queue if row['status'] == ReviewStatus.PENDING.value)} publish package(s).",
        ],
        decisions=[
            "Which plan gets Captain approval today?",
            "Which production ticket should run first?",
            "Which package is safe to post manually?",
        ],
        risks=[
            "Live auto-posting remains locked.",
            "Affiliate/checkout work stays in opportunity research until QA and approval.",
            f"{len(bubbles)} bubble draft(s) and {len(monetize)} monetize opportunity item(s) are advisory only.",
        ],
    )
