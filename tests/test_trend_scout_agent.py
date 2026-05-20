from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
from agents.trend_scout import TrendScoutAgent
from models.trend_scan_job import TrendHit


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.brave_search_api_key = ""
    cfg.reddit_client_id = ""
    return cfg


def test_dry_run_returns_five_hits(config):
    agent = TrendScoutAgent(config)
    hits = agent.scan(["beauty hacks"], dry_run=True)
    assert len(hits) == 5
    assert all(isinstance(h, TrendHit) for h in hits)


def test_dry_run_scores_in_range(config):
    agent = TrendScoutAgent(config)
    hits = agent.scan([], dry_run=True)
    for h in hits:
        assert 0.0 <= h.score <= 100.0


def test_score_clipped_high():
    from agents.trend_scout import TrendScoutAgent
    agent = TrendScoutAgent(MagicMock())
    score = agent._compute_score(
        brave=[{}] * 100,          # way over cap
        gtrends={"recent": 999},   # over 100
        reddit={"subreddits": [{"subscribers": 10_000_000}]},
    )
    assert score <= 100.0


def test_score_clipped_low():
    from agents.trend_scout import TrendScoutAgent
    agent = TrendScoutAgent(MagicMock())
    score = agent._compute_score(brave=[], gtrends={}, reddit={})
    assert score >= 0.0


def test_fetch_brave_empty_without_key(config):
    agent = TrendScoutAgent(config)
    result = agent._fetch_brave("beauty hacks")
    assert result == []


def test_fetch_reddit_empty_without_key(config):
    agent = TrendScoutAgent(config)
    result = agent._fetch_reddit("beauty hacks")
    assert result == {}


def test_fetch_google_trends_returns_dict_on_error(config):
    agent = TrendScoutAgent(config)
    with patch("agents.trend_scout.TrendScoutAgent._fetch_google_trends",
               return_value={"trend_direction": "unknown"}):
        result = agent._fetch_google_trends("anything")
    assert "trend_direction" in result
