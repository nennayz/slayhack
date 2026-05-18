from __future__ import annotations
from unittest.mock import MagicMock, patch
from config import Config
from models.niche_opportunity import NicheSignal, ScoutJob, ScoutJobStatus


def _make_config() -> Config:
    return Config(
        brave_search_api_key="test-brave",
        openai_api_key="test-openai",
        scout_seed_categories="clean beauty,quiet luxury",
    )


def test_scout_dry_run_returns_signals():
    from agents.scout import ScoutAgent
    agent = ScoutAgent(_make_config())
    job = ScoutJob(job_id="test_001", triggered_by="test")
    result = agent.run(job, dry_run=True)
    assert result.status == ScoutJobStatus.RUNNING
    assert len(result.signals) >= 2
    assert all(isinstance(s, NicheSignal) for s in result.signals)


def test_scout_signal_has_niche_name():
    from agents.scout import ScoutAgent
    agent = ScoutAgent(_make_config())
    job = ScoutJob(job_id="test_002", triggered_by="test")
    result = agent.run(job, dry_run=True)
    for sig in result.signals:
        assert sig.niche_name
        assert isinstance(sig.raw_data, dict)


@patch("agents.scout.requests.get")
def test_scout_live_calls_brave_search(mock_get):
    from agents.scout import ScoutAgent
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"web": {"results": [
        {"title": "Clean beauty trend", "description": "Rising fast"}
    ]}}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    with patch("agents.scout.ScoutAgent._fetch_google_trends", return_value={}), \
         patch("agents.scout.ScoutAgent._fetch_reddit", return_value={}), \
         patch("agents.scout.ScoutAgent._fetch_meta_ads", return_value={}):
        agent = ScoutAgent(_make_config())
        job = ScoutJob(job_id="test_003", triggered_by="test")
        result = agent.run(job, dry_run=False)
        assert mock_get.called
        assert len(result.signals) >= 1
        # Verify Brave results are wired into the signal's raw_data
        brave_data = result.signals[0].raw_data.get("brave", [])
        assert len(brave_data) >= 1
        assert brave_data[0]["title"] == "Clean beauty trend"
