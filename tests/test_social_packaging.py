from __future__ import annotations

import json
from pathlib import Path

from models.content_job import (
    BrandProfile,
    ContentJob,
    ContentType,
    GrowthStrategy,
    PMProfile,
    Script,
    VisualIdentity,
)
from social_packaging import run_social_packaging


class FakeStore:
    def __init__(self) -> None:
        self.added = []
        self.statuses = []

    def add(self, obj, embed=True):
        obj.uid = obj.uid or f"uid-{obj.kind}-{len(self.added)}"
        self.added.append((obj, embed))
        return obj

    def set_status(self, uid: str, status: str):
        self.statuses.append((uid, status))


def _pm() -> PMProfile:
    return PMProfile(
        name="Slay",
        page_name="Slay Hack",
        persona="Beauty PM",
        brand=BrandProfile(
            mission="Help women simplify routines.",
            visual=VisualIdentity(colors=["gold"], style="clean"),
            platforms=["tiktok", "instagram"],
            tone="warm",
            target_audience="busy women",
            script_style="short hooks",
        ),
    )


def _write_completed_job(root: Path) -> ContentJob:
    job = ContentJob(
        id="20260520_120000_sp6",
        project="nayzfreedom_fleet",
        pm=_pm(),
        brief="Quick hack for busy mornings",
        platforms=["tiktok", "instagram"],
        stage="emma_done",
        content_type=ContentType.VIDEO,
        idea_uid="nayzfreedom_fleet-idea-20260520-abcd",
    )
    job.bella_output = Script(hook="Save ten minutes", body="Try this simple routine.", cta="Follow for more", duration_seconds=30)
    job.growth_strategy = GrowthStrategy(
        caption="Save ten minutes every morning.",
        hashtags=["#slayhack", "#morningroutine"],
        best_post_time_utc="14:00",
        best_post_time_thai="21:00",
    )
    job.video_path = "output/Slay Hack/final-video.mp4"
    job_path = root / "output" / "Slay Hack" / job.id / "job.json"
    job_path.parent.mkdir(parents=True)
    job_path.write_text(job.model_dump_json(indent=2))
    return job


def test_social_packaging_creates_knowledge_objects_and_local_handoff_queue(tmp_path):
    _write_completed_job(tmp_path)
    store = FakeStore()

    result = run_social_packaging("nayzfreedom_fleet", store, root=tmp_path)

    assert result.jobs_found == 1
    assert result.packages_created == 1
    assert result.queue_entries_created == 1
    kinds = [obj.kind for obj, _ in store.added]
    assert kinds == ["caption", "publish_package"]
    assert store.added[0][0].parent_uids == ["nayzfreedom_fleet-idea-20260520-abcd"]
    assert store.added[1][0].parent_uids == [store.added[0][0].uid]
    assert store.statuses == [("nayzfreedom_fleet-idea-20260520-abcd", "done")]

    job_path = tmp_path / "output" / "Slay Hack" / "20260520_120000_sp6" / "job.json"
    data = json.loads(job_path.read_text())
    assert data["stage"] == "publish_queued"
    assert data["status"] == "awaiting_approval"
    assert data["publish_package"]["source"] == "social_packaging_v1"
    assert data["publish_package"]["caption_uid"] == store.added[0][0].uid
    assert data["publish_package"]["package_uid"] == store.added[1][0].uid
    assert data["publish_execution"]["status"] == "queued"
    assert data["publish_execution"]["live_publish"] is False
    assert data["publish_result"]["tiktok"]["dry_run"] is True
    assert data["publish_result"]["instagram"]["status"] == "scheduled"


def test_social_packaging_is_idempotent_for_already_packaged_jobs(tmp_path):
    _write_completed_job(tmp_path)
    store = FakeStore()
    first = run_social_packaging("nayzfreedom_fleet", store, root=tmp_path)
    second = run_social_packaging("nayzfreedom_fleet", store, root=tmp_path)

    assert first.packages_created == 1
    assert second.jobs_found == 1
    assert second.packages_created == 0
    assert second.jobs_skipped == 1
    assert len(store.added) == 2


def test_social_packaging_dry_run_does_not_write_job_or_store(tmp_path):
    _write_completed_job(tmp_path)
    store = FakeStore()
    job_path = tmp_path / "output" / "Slay Hack" / "20260520_120000_sp6" / "job.json"
    before = job_path.read_text()

    result = run_social_packaging("nayzfreedom_fleet", store, root=tmp_path, dry_run=True)

    assert result.jobs_found == 1
    assert result.packages_created == 1
    assert result.queue_entries_created == 1
    assert store.added == []
    assert job_path.read_text() == before
