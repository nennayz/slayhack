from pathlib import Path
from agents.emma import EmmaAgent
from tests.test_roxy import make_job_post_qa
from tests.test_mia import make_config
from models.content_job import GrowthStrategy

def make_job_for_emma(dry_run=True):
    job = make_job_post_qa(dry_run=dry_run)
    job.growth_strategy = GrowthStrategy(
        hashtags=["#LipHack"], caption="test", best_post_time_utc="13:00", best_post_time_thai="20:00"
    )
    return job

def test_emma_dry_run_writes_faq_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output" / "Slayhack").mkdir(parents=True)
    job = make_job_for_emma(dry_run=True)
    agent = EmmaAgent(make_config())
    job = agent.run(job)
    assert job.community_faq_path is not None
    assert Path(job.community_faq_path).exists()
    assert job.stage == "emma_done"


def test_emma_live_writes_faq_from_claude(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output" / "Slayhack").mkdir(parents=True)
    job = make_job_for_emma(dry_run=False)
    faq_content = "# FAQ\n\n**Q: Does it work?**\nA: yes bestie!"
    mocker.patch.object(EmmaAgent, "_call_claude", return_value=faq_content)
    agent = EmmaAgent(make_config())
    job = agent.run(job)
    assert job.community_faq_path is not None
    assert Path(job.community_faq_path).exists()
    assert job.stage == "emma_done"
    assert "FAQ" in Path(job.community_faq_path).read_text()
