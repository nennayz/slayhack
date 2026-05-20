from agents.bella import BellaAgent
from agents.base_agent import TEAM_IDENTITY
from tests.test_mia import make_config, make_job
from models.content_job import (
    Idea, Script, Article, ImageCaption, InfographicContent,
    ContentType,
)


def make_job_with_idea(dry_run=True, content_type=ContentType.VIDEO):
    job = make_job(dry_run=dry_run)
    job.content_type = content_type
    job.selected_idea = Idea(
        number=1, title="Lip Hack", hook="pov your lips last all day",
        angle="Tutorial", content_type=content_type,
    )
    return job


def test_bella_dry_run_video_returns_script():
    agent = BellaAgent(make_config())
    job = agent.run(make_job_with_idea(dry_run=True, content_type=ContentType.VIDEO))
    assert isinstance(job.bella_output, Script)
    assert job.bella_output.hook != ""
    assert job.bella_output.cta != ""
    assert job.stage == "bella_done"


def test_bella_dry_run_article_returns_article():
    agent = BellaAgent(make_config())
    job = agent.run(make_job_with_idea(dry_run=True, content_type=ContentType.ARTICLE))
    assert isinstance(job.bella_output, Article)
    assert job.bella_output.heading != ""
    assert job.bella_output.cta != ""
    assert job.stage == "bella_done"


def test_bella_dry_run_image_returns_caption():
    agent = BellaAgent(make_config())
    job = agent.run(make_job_with_idea(dry_run=True, content_type=ContentType.IMAGE))
    assert isinstance(job.bella_output, ImageCaption)
    assert job.bella_output.caption != ""
    assert job.bella_output.alt_text != ""
    assert job.stage == "bella_done"


def test_bella_dry_run_infographic_returns_infographic():
    agent = BellaAgent(make_config())
    job = agent.run(make_job_with_idea(dry_run=True, content_type=ContentType.INFOGRAPHIC))
    assert isinstance(job.bella_output, InfographicContent)
    assert job.bella_output.title != ""
    assert len(job.bella_output.points) > 0
    assert job.stage == "bella_done"


def test_bella_live_video_calls_claude(mocker):
    script_json = '{"type":"script","hook":"wait—","body":"step 1","cta":"save this","duration_seconds":30}'
    mocker.patch.object(BellaAgent, "_call_claude", return_value=script_json)
    agent = BellaAgent(make_config())
    job = agent.run(make_job_with_idea(dry_run=False, content_type=ContentType.VIDEO))
    assert isinstance(job.bella_output, Script)
    assert job.bella_output.hook == "wait—"
    assert job.bella_output.duration_seconds == 30


def test_bella_live_article_calls_claude(mocker):
    article_json = '{"type":"article","heading":"The Look","body":"Step 1...","cta":"Shop now"}'
    mocker.patch.object(BellaAgent, "_call_claude", return_value=article_json)
    agent = BellaAgent(make_config())
    job = agent.run(make_job_with_idea(dry_run=False, content_type=ContentType.ARTICLE))
    assert isinstance(job.bella_output, Article)
    assert job.bella_output.heading == "The Look"


def test_bella_system_prompt_includes_team_identity(mocker):
    captured = {}
    def fake_call(system, user, **kwargs):
        captured["system"] = system
        return '{"type":"script","hook":"h","body":"b","cta":"c","duration_seconds":30}'
    agent = BellaAgent(make_config())
    mocker.patch.object(agent, "_call_claude", side_effect=fake_call)
    job = make_job_with_idea(dry_run=False, content_type=ContentType.VIDEO)
    agent.run(job)
    assert captured["system"].startswith(TEAM_IDENTITY)
