from __future__ import annotations

from datetime import date as dt_date, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


def _id(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"


class WorkObjective(str, Enum):
    REACH = "reach"
    SAVE = "save"
    SHARE = "share"
    REVENUE = "revenue"
    COMMUNITY = "community"
    LEARNING = "learning"


class PlanContentType(str, Enum):
    ARTICLE = "article"
    IMAGE = "image"
    INFOGRAPHIC = "infographic"
    SHORT_VIDEO = "short_video"
    LONG_VIDEO = "long_video"
    PROMPT_ONLY_VIDEO = "prompt_only_video"
    BUBBLE = "bubble"


class PlanStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    TICKETED = "ticketed"
    DONE = "done"
    REJECTED = "rejected"


class SlateStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    IN_PRODUCTION = "in_production"
    COMPLETED = "completed"


class TicketStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    QA_READY = "qa_ready"
    PRODUCTION_READY = "production_ready"
    BLOCKED = "blocked"
    DONE = "done"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED_MANUALLY = "posted_manually"


class BubbleStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    USED = "used"
    ARCHIVED = "archived"


class MonetizeStatus(str, Enum):
    NEW = "new"
    RESEARCHING = "researching"
    APPROVED = "approved"
    REJECTED = "rejected"
    BUILDING = "building"
    LIVE = "live"
    ARCHIVED = "archived"


class OfferType(str, Enum):
    EBOOK = "ebook"
    AFFILIATE = "affiliate"
    LEAD_MAGNET = "lead_magnet"
    SALES_PAGE = "sales_page"
    WEBSITE = "website"
    COURSE = "course"
    OTHER = "other"


class ContentPlan(BaseModel):
    id: str = Field(default_factory=lambda: _id("plan"))
    page: str
    source_idea_uid: str = "manual"
    pillar: str = "growth"
    objective: WorkObjective = WorkObjective.REACH
    content_type: PlanContentType = PlanContentType.SHORT_VIDEO
    target_platforms: list[str] = Field(default_factory=list)
    hook: str
    angle: str
    production_brief: str
    publish_window: str = "manual best-time review"
    status: PlanStatus = PlanStatus.DRAFT
    next_action: str = "Captain approves plan or sends it back."
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ContentSlate(BaseModel):
    id: str = Field(default_factory=lambda: _id("slate"))
    date: dt_date = Field(default_factory=dt_date.today)
    page: str
    daily_focus: str
    plan_ids: list[str] = Field(default_factory=list)
    status: SlateStatus = SlateStatus.DRAFT
    next_action: str = "Approve slate, then create production tickets."
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ProductionTicket(BaseModel):
    id: str = Field(default_factory=lambda: _id("ticket"))
    plan_id: str
    page: str
    ticket_type: PlanContentType
    brief: str
    required_assets: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    status: TicketStatus = TicketStatus.QUEUED
    artifact_path: str = ""
    next_action: str = "Run production draft, then QA before packaging."
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class PublishQueueReview(BaseModel):
    package_id: str
    job_id: str = ""
    status: ReviewStatus = ReviewStatus.PENDING
    review_note: str = ""
    reviewed_at: datetime | None = None


class BubbleMessage(BaseModel):
    id: str = Field(default_factory=lambda: _id("bubble"))
    page: str
    date: dt_date = Field(default_factory=dt_date.today)
    source_slate_id: str = ""
    source_plan_ids: list[str] = Field(default_factory=list)
    target_platforms: list[str] = Field(default_factory=list)
    story_prompt: str
    bubble_text: str
    trend_context: str = ""
    status: BubbleStatus = BubbleStatus.DRAFT
    next_action: str = "Captain reviews and posts manually."
    manual_checklist: list[str] = Field(default_factory=list)
    review_note: str = ""
    reviewed_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class MonetizeOpportunity(BaseModel):
    id: str = Field(default_factory=lambda: _id("monetize"))
    page: str
    source: str = "manual"
    source_plan_ids: list[str] = Field(default_factory=list)
    offer_type: OfferType = OfferType.EBOOK
    audience_pain: str
    suggested_offer: str
    matching_content_ids: list[str] = Field(default_factory=list)
    risk_notes: str = "Review claims, disclosure, checkout, and brand trust before launch."
    status: MonetizeStatus = MonetizeStatus.NEW
    next_action: str = "Research and qualify before building."
    manual_checklist: list[str] = Field(default_factory=list)
    review_note: str = ""
    reviewed_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class DailyBriefAction(BaseModel):
    label: str
    reason: str
    href: str
    priority: int
    category: str
    count: int = 0


class DailyBriefSection(BaseModel):
    key: str
    title: str
    item_count: int = 0
    next_action: str
    href: str = ""
    empty_message: str = "Nothing waiting here."


class DailyWorkBrief(BaseModel):
    date: dt_date = Field(default_factory=dt_date.today)
    focus: str
    priorities: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_best_action: DailyBriefAction | None = None
    action_queue: list[DailyBriefAction] = Field(default_factory=list)
    sections: list[DailyBriefSection] = Field(default_factory=list)
    personal_note: str = "Nami low-sensitivity brief only; no private finance/music data connected yet."
