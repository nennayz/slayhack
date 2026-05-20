from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agents.idea_planner import IdeaPlannerAgent
from models.idea_plan_job import IdeaDraft


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.openai_api_key = ""
    cfg.openai_agent_model = "gpt-4o-mini"
    return cfg


def test_dry_run_returns_seven_drafts(config):
    agent = IdeaPlannerAgent(config)
    drafts = agent.generate(signals=[], recent_ideas=[], brand={}, dry_run=True)
    assert len(drafts) == 7
    assert all(isinstance(d, IdeaDraft) for d in drafts)


def test_dry_run_drafts_have_required_fields(config):
    agent = IdeaPlannerAgent(config)
    drafts = agent.generate(signals=[], recent_ideas=[], brand={}, dry_run=True)
    for d in drafts:
        assert d.title
        assert d.hook
        assert d.angle
        assert d.content_type in {"video", "image", "article", "infographic"}


def test_parse_ideas_valid_json(config):
    agent = IdeaPlannerAgent(config)
    raw = json.dumps([
        {
            "title": "Test Idea",
            "hook": "Test hook",
            "angle": "Tutorial",
            "content_type": "video",
        }
    ])
    drafts = agent._parse_ideas(raw)
    assert len(drafts) == 1
    assert drafts[0].title == "Test Idea"


def test_parse_ideas_invalid_json_returns_empty(config):
    agent = IdeaPlannerAgent(config)
    drafts = agent._parse_ideas("not json at all {{")
    assert drafts == []


def test_parse_ideas_partial_json_skips_bad_items(config):
    agent = IdeaPlannerAgent(config)
    raw = json.dumps([
        {"title": "Good", "hook": "h", "angle": "a", "content_type": "video"},
        {"bad_key": "missing title"},          # missing required fields
    ])
    drafts = agent._parse_ideas(raw)
    assert len(drafts) == 1
    assert drafts[0].title == "Good"


def test_client_not_constructed_until_needed(config):
    # Instantiating IdeaPlannerAgent must NOT touch OpenAI — no api_key needed
    agent = IdeaPlannerAgent(config)
    assert agent._client is None


def test_generate_live_calls_openai(config):
    agent = IdeaPlannerAgent(config)
    fake_response = MagicMock()
    fake_response.choices[0].message.content = json.dumps([
        {"title": "Mock Idea", "hook": "mock hook", "angle": "Tutorial", "content_type": "video"}
    ] * 7)
    with patch.object(agent, "client") as mock_client:
        mock_client.chat.completions.create.return_value = fake_response
        drafts = agent.generate(signals=[], recent_ideas=[], brand={}, dry_run=False)
    assert len(drafts) == 7
