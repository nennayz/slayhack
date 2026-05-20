# ruff: noqa: F403,F405
from .helpers import *


def test_work_os_planner_seeds_slates_and_tickets(client):
    response = client.get("/aurora/planner", headers=_auth())
    assert response.status_code == 200
    assert "Content Planner" in response.text
    assert "Production queue" in response.text
    assert "Idea → plan contracts" in response.text


def test_work_os_planner_syncs_approved_ks_ideas(client, tmp_path):
    from knowledge.embedder import Embedder
    from knowledge.object import ContentObject
    from knowledge.settings import KnowledgeSettings
    from knowledge.store import KnowledgeStore

    store = KnowledgeStore(
        KnowledgeSettings(root=tmp_path),
        Embedder("test", embed_fn=lambda texts: [[0.0] * 4 for _ in texts]),
    )
    idea = store.add(ContentObject(
        page="nayzfreedom_fleet",
        kind="idea",
        title="Approved KS planner idea",
        summary="Turn this real approved idea into a planner draft.",
        dedup_text="approved-ks-planner-idea",
        status="approved",
        tags=["video", "reach"],
    ), embed=False)

    response = client.post("/aurora/planner/sync", headers=_auth(), follow_redirects=True)
    assert response.status_code == 200
    assert "Approved KS planner idea" in response.text
    assert idea.uid in response.text

    plan_id = response.text.split('name="plan_id" value="', 1)[1].split('"', 1)[0]
    approve = client.post(
        "/aurora/planner/review",
        headers=_auth(),
        data={"plan_id": plan_id, "decision": "approve"},
        follow_redirects=True,
    )
    assert approve.status_code == 200
    assert "approved" in approve.text


def test_work_os_daily_brief_and_nami_brief_render(client):
    work = client.get("/aurora/work-brief", headers=_auth())
    assert work.status_code == 200
    assert "Today&apos;s Work Brief" in work.text or "Today's Work Brief" in work.text
    assert "Live auto-posting remains locked" in work.text

    nami = client.get("/freedom/daily-brief", headers=_auth())
    assert nami.status_code == 200
    assert "Nami Daily Brief" in nami.text
    assert "Low-sensitivity personal brief only" in nami.text


def test_bubbles_and_monetize_registry_render(client):
    bubbles = client.get("/aurora/bubbles", headers=_auth())
    assert bubbles.status_code == 200
    assert "Daily Bubble / Status Drafts" in bubbles.text
    assert "manual" in bubbles.text.lower()

    monetize = client.get("/aurora/monetize", headers=_auth())
    assert monetize.status_code == 200
    assert "Opportunity Gate" in monetize.text
    assert "No checkout or affiliate automation" in monetize.text


def test_publish_queue_review_is_local_only(client, tmp_path):
    queue = tmp_path / "output" / "publish_queue.jsonl"
    queue.parent.mkdir(parents=True)
    queue.write_text(json.dumps({
        "package_uid": "pkg-1",
        "job_id": "job-1",
        "platforms": ["facebook"],
        "caption": "manual caption only",
        "hashtags": ["#test"],
        "asset_path": "output/test.mp4",
    }) + "\n")

    page = client.get("/aurora/publish-queue", headers=_auth())
    assert page.status_code == 200
    assert "Captain Manual Publish Gate" in page.text
    assert "manual caption only" in page.text
    assert "Live publish" in page.text
    assert "Locked" in page.text

    reviewed = client.post(
        "/aurora/publish-queue/review",
        headers=_auth(),
        data={"package_id": "pkg-1", "decision": "approve", "review_note": "safe manual handoff"},
        follow_redirects=True,
    )
    assert reviewed.status_code == 200
    assert "approved" in reviewed.text
    assert "safe manual handoff" in reviewed.text
