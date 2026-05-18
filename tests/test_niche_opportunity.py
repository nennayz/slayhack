from __future__ import annotations
from datetime import datetime
from models.niche_opportunity import NicheSignal, NicheOpportunity, ScoutJob, ScoutJobStatus


def test_niche_signal_stores_raw_data():
    sig = NicheSignal(niche_name="clean beauty", raw_data={"brave": ["result1"]})
    assert sig.niche_name == "clean beauty"
    assert sig.raw_data["brave"] == ["result1"]


def test_niche_opportunity_reach_score_bounds():
    # Valid score passes
    opp = NicheOpportunity(
        niche_name="clean beauty",
        target_audience="Women USA 25-35",
        platforms=["instagram", "tiktok"],
        reach_score=85.0,
        trend_direction="rising",
        content_formats=["reel", "infographic"],
        monetization_notes="High affiliate potential",
        signals={"google_trends": "rising"},
    )
    assert opp.reach_score == 85.0

def test_niche_opportunity_reach_score_rejects_out_of_range():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        NicheOpportunity(
            niche_name="bad",
            target_audience="x",
            platforms=[],
            reach_score=150.0,
            trend_direction="rising",
            content_formats=[],
            monetization_notes="",
            signals={},
        )


def test_scout_job_defaults():
    job = ScoutJob(job_id="20260517_080000", triggered_by="scheduler")
    assert job.status == ScoutJobStatus.PENDING
    assert job.opportunities == []
    assert job.approved_niche is None


def test_scout_job_serializes_to_json():
    job = ScoutJob(job_id="20260517_080000", triggered_by="telegram")
    data = job.model_dump_json()
    assert "job_id" in data
    assert "opportunities" in data
