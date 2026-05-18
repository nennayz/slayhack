from agents.zoe import ZoeAgent
from agents.base_agent import TEAM_IDENTITY
from tests.test_mia import make_config, make_job
from models.content_job import Idea, ContentType


def test_zoe_system_prompt_includes_team_identity(mocker):
    captured = {}
    def fake_call(system, user, **kwargs):
        captured["system"] = system
        return '[{"number":1,"title":"T","hook":"h","angle":"a","content_type":"video"}]'
    agent = ZoeAgent(make_config())
    mocker.patch.object(agent, "_call_claude", side_effect=fake_call)
    job = make_job(dry_run=False)
    job.trend_data = {"trends": [], "trending_sounds": [], "formats": []}
    agent.run(job)
    assert captured["system"].startswith(TEAM_IDENTITY)


def test_zoe_dry_run_returns_ideas():
    job = make_job(dry_run=True)
    job.trend_data = {"trends": ["Glossy lips"], "trending_sounds": ["Espresso"], "formats": ["POV"]}
    agent = ZoeAgent(make_config())
    job = agent.run(job)
    assert job.ideas is not None
    assert len(job.ideas) >= 3
    assert all(isinstance(i, Idea) for i in job.ideas)
    assert job.stage == "zoe_done"


def test_zoe_live_calls_claude(mocker):
    ideas_json = '[{"number":1,"title":"Lip Hack","hook":"pov your lips last","angle":"Tutorial","content_type":"video"}]'
    mocker.patch.object(ZoeAgent, "_call_claude", return_value=ideas_json)
    job = make_job(dry_run=False)
    job.trend_data = {"trends": ["Glossy lips"], "trending_sounds": [], "formats": []}
    agent = ZoeAgent(make_config())
    job = agent.run(job)
    assert len(job.ideas) == 1
    assert job.ideas[0].title == "Lip Hack"
    assert job.ideas[0].content_type == ContentType.VIDEO


def test_zoe_live_limits_allowed_type_when_preset(mocker):
    captured = {}
    def fake_call(system, user, **kwargs):
        captured["user"] = user
        return '[{"number":1,"title":"Article","hook":"h","angle":"a","content_type":"article"}]'
    mocker.patch.object(ZoeAgent, "_call_claude", side_effect=fake_call)
    job = make_job(dry_run=False)
    job.content_type = ContentType.ARTICLE
    job.trend_data = {"trends": [], "trending_sounds": [], "formats": []}
    agent = ZoeAgent(make_config())
    agent.run(job)
    assert "Allowed content types: article" in captured["user"]


def test_zoe_live_normalizes_requested_content_type(mocker):
    ideas_json = '[{"number":1,"title":"Article","hook":"h","angle":"a","content_type":"carousel-style posts"}]'
    mocker.patch.object(ZoeAgent, "_call_claude", return_value=ideas_json)
    job = make_job(dry_run=False)
    job.content_type = ContentType.ARTICLE
    job.trend_data = {"trends": [], "trending_sounds": [], "formats": []}
    agent = ZoeAgent(make_config())
    job = agent.run(job)
    assert job.ideas[0].content_type == ContentType.ARTICLE


def test_zoe_live_normalizes_common_content_type_aliases(mocker):
    ideas_json = '[{"number":1,"title":"Reel","hook":"h","angle":"a","content_type":"short-form videos"}]'
    mocker.patch.object(ZoeAgent, "_call_claude", return_value=ideas_json)
    job = make_job(dry_run=False)
    job.trend_data = {"trends": [], "trending_sounds": [], "formats": []}
    agent = ZoeAgent(make_config())
    job = agent.run(job)
    assert job.ideas[0].content_type == ContentType.VIDEO


def test_zoe_dry_run_ideas_have_content_type():
    job = make_job(dry_run=True)
    job.trend_data = {"trends": [], "trending_sounds": [], "formats": []}
    agent = ZoeAgent(make_config())
    job = agent.run(job)
    for idea in job.ideas:
        assert isinstance(idea.content_type, ContentType)
