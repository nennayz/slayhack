from unittest.mock import MagicMock
from agents.mia import MiaAgent
from config import Config
from models.content_job import ContentJob, PMProfile, BrandProfile, VisualIdentity


def make_config():
    return Config(brave_search_api_key="brave", openai_api_key="oai")


def make_job(dry_run=True):
    brand = BrandProfile(
        mission="m", visual=VisualIdentity(colors=[], style=""), platforms=["instagram"],
        tone="sassy", target_audience="Gen Z USA", script_style="lowercase", nora_max_retries=2,
    )
    pm = PMProfile(name="Slay", page_name="Slayhack", persona="test pm", brand=brand)
    return ContentJob(project="nayzfreedom_fleet", pm=pm, brief="lipstick that lasts", platforms=["instagram"], dry_run=dry_run)


def test_mia_dry_run_populates_trend_data():
    agent = MiaAgent(make_config())
    job = agent.run(make_job(dry_run=True))
    assert job.trend_data is not None
    assert "trends" in job.trend_data
    assert job.stage == "mia_done"


def test_mia_live_calls_brave_search(mocker):
    mock_get = mocker.patch("agents.mia.requests.get")
    mock_get.return_value.json.return_value = {
        "web": {"results": [{"title": "Glossy lips trend", "description": "trending now"}]}
    }
    mock_get.return_value.raise_for_status = MagicMock()
    mocker.patch.object(MiaAgent, "_call_claude", return_value='```json\n{"trends": ["Glossy lips"], "trending_sounds": ["Espresso"]}\n```')

    agent = MiaAgent(make_config())
    job = agent.run(make_job(dry_run=False))
    assert job.trend_data is not None
    assert job.stage == "mia_done"
    mock_get.assert_called_once()
