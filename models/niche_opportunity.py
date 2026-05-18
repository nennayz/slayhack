from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ScoutJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"


class NicheSignal(BaseModel):
    niche_name: str
    raw_data: dict


class NicheOpportunity(BaseModel):
    niche_name: str
    target_audience: str
    platforms: list[str]
    reach_score: float = Field(..., ge=0, le=100)
    trend_direction: str        # "rising" | "stable" | "declining"
    content_formats: list[str]
    monetization_notes: str
    signals: dict


class ScoutJob(BaseModel):
    job_id: str
    triggered_by: str           # "scheduler" | "telegram" | "dashboard"
    created_at: datetime = Field(default_factory=datetime.now)
    status: ScoutJobStatus = ScoutJobStatus.PENDING
    opportunities: list[NicheOpportunity] = Field(default_factory=list)
    approved_niche: Optional[str] = None
    signals: list[NicheSignal] = Field(default_factory=list)
    status_message: Optional[str] = None
