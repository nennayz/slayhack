from __future__ import annotations
from unittest.mock import MagicMock, patch
from config import Config
from models.niche_opportunity import NicheSignal, NicheOpportunity, ScoutJob, ScoutJobStatus


def _make_config() -> Config:
    return Config(brave_search_api_key="x", openai_api_key="test-openai")


def _make_job_with_signals() -> ScoutJob:
    job = ScoutJob(job_id="test_analyst_001", triggered_by="test")
    job.signals = [
        NicheSignal(niche_name="clean beauty", raw_data={"google_trends": {"trend_direction": "rising"}, "reddit": {"subreddits": [{"subscribers": 400000}]}}),
        NicheSignal(niche_name="quiet luxury", raw_data={"google_trends": {"trend_direction": "rising"}, "reddit": {"subreddits": [{"subscribers": 300000}]}}),
    ]
    return job


def test_analyst_dry_run_returns_opportunities():
    from agents.analyst import AnalystAgent
    agent = AnalystAgent(_make_config())
    job = _make_job_with_signals()
    result = agent.run(job, dry_run=True)
    assert len(result.opportunities) >= 1
    assert all(isinstance(o, NicheOpportunity) for o in result.opportunities)
    assert result.status == ScoutJobStatus.AWAITING_APPROVAL


def test_analyst_dry_run_reach_scores_valid():
    from agents.analyst import AnalystAgent
    agent = AnalystAgent(_make_config())
    job = _make_job_with_signals()
    result = agent.run(job, dry_run=True)
    for opp in result.opportunities:
        assert 0 <= opp.reach_score <= 100


def test_analyst_opportunities_sorted_by_reach_score():
    from agents.analyst import AnalystAgent
    agent = AnalystAgent(_make_config())
    job = _make_job_with_signals()
    result = agent.run(job, dry_run=True)
    scores = [o.reach_score for o in result.opportunities]
    assert scores == sorted(scores, reverse=True)


@patch("agents.analyst.OpenAI")
def test_analyst_live_calls_openai(mock_openai_cls):
    from agents.analyst import AnalystAgent
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.choices[0].message.content = '''[
        {"niche_name": "clean beauty", "target_audience": "Women USA 25-35", "platforms": ["instagram","tiktok"], "reach_score": 88.0, "trend_direction": "rising", "content_formats": ["reel"], "monetization_notes": "High affiliate", "signals": {}}
    ]'''
    mock_client.chat.completions.create.return_value = mock_response

    agent = AnalystAgent(_make_config())
    job = _make_job_with_signals()
    result = agent.run(job, dry_run=False)
    assert mock_client.chat.completions.create.called
    assert len(result.opportunities) == 1
    assert result.opportunities[0].niche_name == "clean beauty"
