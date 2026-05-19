from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


@dataclass
class TrendHit:
    topic: str
    direction: str   # "rising" | "stable" | "declining" | "unknown"
    score: float     # 0–100
    sources: dict    # raw source data


class TrendScanJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TrendScanJob(BaseModel):
    job_id: str
    page_slug: str
    triggered_by: str
    created_at: datetime = Field(default_factory=datetime.now)
    status: TrendScanJobStatus = TrendScanJobStatus.PENDING
    signals_found: int = 0
    signals_stored: int = 0
    signals_skipped: int = 0
    digest_path: Optional[str] = None
    error: Optional[str] = None
