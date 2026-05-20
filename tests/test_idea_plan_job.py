from __future__ import annotations
from datetime import datetime
from models.idea_plan_job import IdeaDraft, IdeaPlanJob, IdeaPlanJobStatus


def test_idea_draft_fields():
    d = IdeaDraft(
        title="The Invisible Lip Liner Hack",
        hook="POV: your lips last all day",
        angle="Tutorial",
        content_type="video",
    )
    assert d.title == "The Invisible Lip Liner Hack"
    assert d.source_signal_uids == []


def test_idea_draft_with_signal_uids():
    d = IdeaDraft(
        title="Quiet Luxury Morning Routine",
        hook="This is how rich girls start their day",
        angle="Lifestyle",
        content_type="image",
        source_signal_uids=["nayzfreedom_fleet-trend_signal-20260519-abc1"],
    )
    assert len(d.source_signal_uids) == 1


def test_idea_plan_job_defaults():
    job = IdeaPlanJob(
        job_id="20260519_070000",
        page_slug="nayzfreedom_fleet",
        triggered_by="scheduler",
    )
    assert job.status == IdeaPlanJobStatus.PENDING
    assert job.ideas_generated == 0
    assert job.ideas_stored == 0
    assert job.ideas_skipped == 0
    assert job.signals_used == 0
    assert job.digest_path is None
    assert job.error is None


def test_idea_plan_job_status_enum_values():
    assert IdeaPlanJobStatus.PENDING == "pending"
    assert IdeaPlanJobStatus.RUNNING == "running"
    assert IdeaPlanJobStatus.COMPLETED == "completed"
    assert IdeaPlanJobStatus.FAILED == "failed"


def test_idea_plan_job_created_at_is_datetime():
    job = IdeaPlanJob(job_id="x", page_slug="p", triggered_by="t")
    assert isinstance(job.created_at, datetime)
