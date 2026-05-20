# ruff: noqa: F403,F405
from .helpers import *


def test_work_os_planner_seeds_slates_and_tickets(client):
    response = client.get("/aurora/planner", headers=_auth())
    assert response.status_code == 200
    assert "Content Planner" in response.text
    assert "Production queue" in response.text
    assert "Idea → plan contracts" in response.text


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
