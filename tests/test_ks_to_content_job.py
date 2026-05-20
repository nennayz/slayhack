from __future__ import annotations

from knowledge.object import ContentObject
from models.content_job import BrandProfile, ContentType, PMProfile, VisualIdentity


def _make_idea(title: str, summary: str = "", tags: list | None = None, body: str = "") -> ContentObject:
    return ContentObject(
        page="nayzfreedom_fleet",
        kind="idea",
        title=title,
        summary=summary,
        dedup_text=f"{title}|nayzfreedom_fleet|20260519",
        tags=tags or ["video", "Tutorial", "nayzfreedom_fleet"],
        body=body,
        uid="nayzfreedom_fleet-idea-20260519-abcd",
    )


def _make_pm() -> PMProfile:
    brand = BrandProfile(
        mission="Beauty for Gen Z",
        visual=VisualIdentity(colors=["#FF69B4"], style="bold"),
        platforms=["instagram", "facebook"],
        tone="sassy",
        target_audience="Gen Z USA",
        script_style="lowercase",
    )
    return PMProfile(name="Slay", page_name="Slayhack", persona="test pm", brand=brand)


def test_brief_uses_summary_and_angle():
    from ks_to_content_job import idea_to_content_job
    idea = _make_idea("The Glow Up Method", summary="this hack changed my whole face",
                      tags=["video", "Tutorial", "nayzfreedom_fleet"])
    job = idea_to_content_job(idea, _make_pm())
    assert job.brief == "The Glow Up Method: this hack changed my whole face [Tutorial]"


def test_brief_fallback_parses_hook_from_body():
    from ks_to_content_job import idea_to_content_job
    body = "## The Glow Up Method\n\n**Hook:** parsed from body\n\n**Angle:** Tutorial\n"
    idea = _make_idea("The Glow Up Method", summary="", body=body)
    job = idea_to_content_job(idea, _make_pm())
    assert "parsed from body" in job.brief


def test_brief_title_only_when_no_hook():
    from ks_to_content_job import idea_to_content_job
    idea = _make_idea("Bare Title", summary="", body="No hook line here")
    job = idea_to_content_job(idea, _make_pm())
    assert job.brief == "Bare Title"


def test_content_type_from_first_tag():
    from ks_to_content_job import idea_to_content_job
    idea = _make_idea("T", tags=["article", "Editorial", "nayzfreedom_fleet"])
    job = idea_to_content_job(idea, _make_pm())
    assert job.content_type == ContentType.ARTICLE


def test_invalid_content_type_tag_returns_none():
    from ks_to_content_job import idea_to_content_job
    idea = _make_idea("T", tags=["not_a_type", "Tutorial", "nayzfreedom_fleet"])
    job = idea_to_content_job(idea, _make_pm())
    assert job.content_type is None


def test_idea_uid_set_on_job():
    from ks_to_content_job import idea_to_content_job
    idea = _make_idea("T")
    job = idea_to_content_job(idea, _make_pm())
    assert job.idea_uid == idea.uid


def test_platforms_default_from_brand():
    from ks_to_content_job import idea_to_content_job
    idea = _make_idea("T")
    job = idea_to_content_job(idea, _make_pm())
    assert job.platforms == ["instagram", "facebook"]


def test_no_mia_zoe_in_tool_definitions():
    from tools.agent_tools import get_tool_definitions
    names = {t["name"] for t in get_tool_definitions()}
    assert "run_mia" not in names
    assert "run_zoe" not in names
