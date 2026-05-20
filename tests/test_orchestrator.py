from unittest.mock import MagicMock

from models.content_job import Article, CheckpointDecision, ContentType, GrowthStrategy, Idea, JobStatus, QAResult
from orchestrator import Orchestrator
from tests.test_mia import make_config, make_job


def test_orchestrator_dry_run_completes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    monkeypatch.setattr("orchestrator.pause", lambda *args, **kwargs: CheckpointDecision(stage=args[0], decision="1" if args[0] == "idea_selection" else "approved"))

    orch = Orchestrator(make_config())
    job = make_job(dry_run=True)
    job.content_type = ContentType.VIDEO
    result = orch.run(job)

    assert result.status == JobStatus.COMPLETED
    assert result.trend_data is None
    assert result.ideas is None
    assert result.selected_idea is None
    assert result.bella_output is not None
    assert result.growth_strategy is not None
    assert result.community_faq_path is not None
    assert [entry.stage for entry in result.checkpoint_log] == [
        "content_review",
        "qa_review",
        "final_approval",
    ]


def test_orchestrator_dispatch_idea_selection_sets_content_type(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    orch = Orchestrator(make_config())
    job = make_job(dry_run=True)
    job.ideas = [
        Idea(number=1, title="Lip Hack", hook="h", angle="Tutorial", content_type=ContentType.VIDEO),
        Idea(number=2, title="Morning Routine", hook="h2", angle="Lifestyle", content_type=ContentType.ARTICLE),
    ]

    mocker.patch("orchestrator.pause", return_value=CheckpointDecision(stage="idea_selection", decision="2"))

    orch._dispatch(
        "request_checkpoint",
        {"stage": "idea_selection", "summary": "pick one", "options": ["1", "2"]},
        job,
    )

    assert job.selected_idea is not None
    assert job.content_type == ContentType.ARTICLE
    assert job.selected_idea.number == 2


def test_orchestrator_unattended_selects_matching_content_type(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    orch = Orchestrator(make_config())
    orch._unattended = True
    job = make_job(dry_run=True)
    job.content_type = ContentType.ARTICLE
    job.ideas = [
        Idea(number=1, title="Video idea", hook="h", angle="Tutorial", content_type=ContentType.VIDEO),
        Idea(number=2, title="Article idea", hook="h2", angle="Editorial", content_type=ContentType.ARTICLE),
    ]

    monkeypatch.setattr("orchestrator.pause", lambda *args, **kwargs: CheckpointDecision(stage="idea_selection", decision="1"))

    orch._dispatch(
        "request_checkpoint",
        {"stage": "idea_selection", "summary": "pick one", "options": []},
        job,
    )

    assert job.selected_idea is not None
    assert job.selected_idea.number == 2
    assert job.content_type == ContentType.ARTICLE


def test_orchestrator_resume_skips_completed_stages(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    monkeypatch.setattr("orchestrator.pause", lambda *args, **kwargs: CheckpointDecision(stage=args[0], decision="approved"))

    orch = Orchestrator(make_config())
    job = make_job(dry_run=True)
    job.trend_data = {"trends": ["already"]}
    job.ideas = [Idea(number=1, title="Existing", hook="Hook", angle="Angle", content_type=ContentType.ARTICLE)]
    job.selected_idea = job.ideas[0]
    job.content_type = ContentType.ARTICLE
    job.bella_output = Article(heading="Existing heading", body="Existing body", cta="Existing CTA")
    job.checkpoint_log.append(CheckpointDecision(stage="content_review", decision="approved"))
    job.qa_result = QAResult(passed=True)
    job.checkpoint_log.append(CheckpointDecision(stage="qa_review", decision="approved"))

    mia_run = mocker.patch.object(orch.agents["mia"], "run", wraps=orch.agents["mia"].run)
    zoe_run = mocker.patch.object(orch.agents["zoe"], "run", wraps=orch.agents["zoe"].run)
    bella_run = mocker.patch.object(orch.agents["bella"], "run", wraps=orch.agents["bella"].run)

    result = orch.run(job, unattended=True)

    assert result.status == JobStatus.COMPLETED
    mia_run.assert_not_called()
    zoe_run.assert_not_called()
    bella_run.assert_not_called()
    assert result.growth_strategy is not None
    assert result.community_faq_path is not None


def test_orchestrator_parallel_post_production_merges_results_without_shared_state(mocker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    orch = Orchestrator(make_config())
    job = make_job(dry_run=True)

    roxy_result = job.model_copy(deep=True)
    roxy_result.growth_strategy = GrowthStrategy(
        hashtags=["#test"],
        caption="Caption",
        best_post_time_utc="12:00",
        best_post_time_thai="19:00",
    )
    roxy_result.stage = "roxy_done"

    emma_result = job.model_copy(deep=True)
    emma_result.community_faq_path = "output/faq.md"
    emma_result.stage = "emma_done"

    mocker.patch.object(orch, "_run_agent_job", side_effect=[roxy_result, emma_result])

    orch._run_parallel_post_production(job)

    assert job.growth_strategy is not None
    assert job.growth_strategy.caption == "Caption"
    assert job.community_faq_path == "output/faq.md"
    assert job.stage == "emma_done"


def test_orchestrator_safe_prep_intercepts_publish(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    orch = Orchestrator(make_config(), safe_prep=True)
    job = make_job(dry_run=False)
    job.growth_strategy = GrowthStrategy(
        hashtags=["#test"],
        caption="Safe caption",
        best_post_time_utc="12:00",
        best_post_time_thai="19:00",
    )
    publish_agent = MagicMock()
    orch.agents["publish"] = publish_agent

    result = orch._dispatch("run_publish", {"schedule": True}, job)

    publish_agent.run.assert_not_called()
    assert result == {"status": "safe_prep", "stage": "ready_to_publish"}
    assert job.stage == "ready_to_publish"
    assert job.publish_package is not None
    assert job.publish_execution is not None
    assert job.publish_result is not None
    assert job.publish_package["status"] == "completed"
    assert job.publish_execution["status"] == "ready_to_publish"
    assert job.publish_result["instagram"]["status"] == "ready_to_publish"
    assert job.publish_result["instagram"]["dry_run"] is True