from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional, Union
from uuid import uuid4
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class ContentType(str, Enum):
    VIDEO = "video"
    ARTICLE = "article"
    IMAGE = "image"
    INFOGRAPHIC = "infographic"


class VisualIdentity(BaseModel):
    colors: list[str]
    style: str


class BrandProfile(BaseModel):
    mission: str
    visual: VisualIdentity
    platforms: list[str]
    tone: str
    target_audience: str
    script_style: str
    comment_reply_style: str = ""
    nora_max_retries: int = 2
    allowed_content_types: list[ContentType] = Field(
        default_factory=lambda: [
            ContentType.VIDEO, ContentType.IMAGE,
            ContentType.INFOGRAPHIC, ContentType.ARTICLE,
        ]
    )


class PMProfile(BaseModel):
    name: str
    page_name: str
    persona: str
    brand: BrandProfile


class Idea(BaseModel):
    number: int
    title: str
    hook: str
    angle: str
    content_type: ContentType


class Script(BaseModel):
    type: Literal["script"] = "script"
    hook: str
    body: str
    cta: str
    duration_seconds: int


class Article(BaseModel):
    type: Literal["article"] = "article"
    heading: str
    body: str
    cta: str


class ImageCaption(BaseModel):
    type: Literal["image"] = "image"
    caption: str
    alt_text: str


class InfographicContent(BaseModel):
    type: Literal["infographic"] = "infographic"
    title: str
    points: list[str]
    cta: str


BellaOutput = Annotated[
    Union[Script, Article, ImageCaption, InfographicContent],
    Field(discriminator="type")
]


class QAResult(BaseModel):
    passed: bool
    script_feedback: Optional[str] = None
    visual_feedback: Optional[str] = None
    send_back_to: Optional[Literal["bella", "lila"]] = None


class GrowthStrategy(BaseModel):
    hashtags: list[str]
    caption: str
    best_post_time_utc: str
    best_post_time_thai: str
    editorial_guidance: dict[str, str] = Field(default_factory=dict)


class CheckpointDecision(BaseModel):
    stage: str
    decision: str
    timestamp: datetime = Field(default_factory=datetime.now)


class PostPerformance(BaseModel):
    platform: str
    likes: Optional[int] = None
    reach: Optional[int] = None
    saves: Optional[int] = None
    shares: Optional[int] = None
    recorded_at: Optional[datetime] = None


class ContentJob(BaseModel):
    id: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:6])
    project: str
    pm: PMProfile
    brief: str
    platforms: list[str]
    stage: str = "init"
    status: JobStatus = JobStatus.PENDING
    dry_run: bool = False
    trend_data: Optional[dict] = None
    ideas: Optional[list[Idea]] = None
    selected_idea: Optional[Idea] = None
    content_type: Optional[ContentType] = None
    bella_output: Optional[BellaOutput] = None
    visual_prompt: Optional[str] = None
    image_path: Optional[str] = None
    video_path: Optional[str] = None
    production_ticket: Optional[dict] = None
    video_package: Optional[dict] = None
    generation_request: Optional[dict] = None
    generation_result: Optional[dict] = None
    qa_result: Optional[QAResult] = None
    nora_retry_count: int = 0
    growth_strategy: Optional[GrowthStrategy] = None
    community_faq_path: Optional[str] = None
    publish_package: Optional[dict] = None
    publish_execution: Optional[dict] = None
    publish_result: Optional[dict] = None
    manual_post_kit: Optional[dict] = None
    checkpoint_log: list[CheckpointDecision] = Field(default_factory=list)
    performance: list[PostPerformance] = Field(default_factory=list)
    published_at: Optional[datetime] = None
    idea_uid: str | None = None   # uid of the KS idea that spawned this job
