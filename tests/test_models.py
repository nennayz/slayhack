import pytest
from pydantic import TypeAdapter, ValidationError
from models.content_job import (
    ContentJob, PMProfile, BrandProfile, VisualIdentity,
    Idea, Script, QAResult, GrowthStrategy, JobStatus, ContentType,
    Article, ImageCaption, InfographicContent, BellaOutput,
)

_BELLA_OUTPUT_ADAPTER: TypeAdapter[BellaOutput] = TypeAdapter(BellaOutput)


def make_brand():
    return BrandProfile(
        mission="Test mission",
        visual=VisualIdentity(colors=["#FFF"], style="minimalist"),
        platforms=["instagram"],
        tone="casual",
        target_audience="Gen Z women USA",
        script_style="lowercase slang",
        nora_max_retries=2,
    )

def make_pm():
    return PMProfile(name="Test", page_name="Test Page", persona="You are a test PM.", brand=make_brand())

def test_content_job_defaults():
    job = ContentJob(project="test", pm=make_pm(), brief="test brief", platforms=["instagram"])
    assert job.status == JobStatus.PENDING
    assert job.stage == "init"
    assert job.dry_run is False
    assert job.nora_retry_count == 0
    assert job.checkpoint_log == []
    assert job.performance == []

def test_content_job_id_is_timestamp_format():
    job = ContentJob(project="test", pm=make_pm(), brief="b", platforms=["instagram"])
    assert len(job.id) == 22  # YYYYMMDD_HHMMSS_%f (with microseconds)

def test_idea_model():
    idea = Idea(number=1, title="Test Idea", hook="Test hook", angle="Tutorial",
                content_type=ContentType.VIDEO)
    assert idea.number == 1
    assert idea.content_type == ContentType.VIDEO


def test_idea_content_type_required():
    with pytest.raises(ValidationError):
        Idea(number=1, title="Test", hook="h", angle="a")  # missing content_type

def test_qa_result_defaults():
    qa = QAResult(passed=True)
    assert qa.send_back_to is None
    assert qa.script_feedback is None

def test_pm_profile_has_name():
    pm = PMProfile(name="Slay", page_name="Slayhack", persona="test", brand=make_brand())
    assert pm.name == "Slay"

def test_content_type_values():
    assert ContentType.VIDEO == "video"
    assert ContentType.ARTICLE == "article"
    assert ContentType.IMAGE == "image"
    assert ContentType.INFOGRAPHIC == "infographic"

def test_brand_profile_allowed_content_types_default():
    brand = make_brand()
    assert set(brand.allowed_content_types) == {
        ContentType.VIDEO, ContentType.ARTICLE, ContentType.IMAGE, ContentType.INFOGRAPHIC
    }

def test_brand_profile_allowed_content_types_custom():
    brand = BrandProfile(
        mission="m", visual=VisualIdentity(colors=[], style=""),
        platforms=["instagram"], tone="c", target_audience="t", script_style="s",
        allowed_content_types=[ContentType.VIDEO, ContentType.IMAGE],
    )
    assert brand.allowed_content_types == [ContentType.VIDEO, ContentType.IMAGE]


def test_script_has_type_discriminator():
    s = Script(hook="h", body="b", cta="c", duration_seconds=30)
    assert s.type == "script"

def test_article_model():
    a = Article(heading="The Look", body="Step 1...", cta="Shop now")
    assert a.type == "article"
    assert a.heading == "The Look"

def test_image_caption_model():
    img = ImageCaption(caption="Soft glam vibes", alt_text="Woman in gold tones")
    assert img.type == "image"
    assert img.alt_text == "Woman in gold tones"

def test_infographic_content_model():
    inf = InfographicContent(title="5 Tips", points=["tip 1", "tip 2"], cta="Save this")
    assert inf.type == "infographic"
    assert len(inf.points) == 2

def test_bella_output_json_roundtrip_script():
    original = Script(hook="h", body="b", cta="c", duration_seconds=45)
    json_str = original.model_dump_json()
    restored = _BELLA_OUTPUT_ADAPTER.validate_json(json_str)
    assert isinstance(restored, Script)
    assert restored.hook == "h"

def test_bella_output_json_roundtrip_article():
    original = Article(heading="Heading", body="Body text", cta="Click here")
    json_str = original.model_dump_json()
    restored = _BELLA_OUTPUT_ADAPTER.validate_json(json_str)
    assert isinstance(restored, Article)
    assert restored.heading == "Heading"

def test_bella_output_json_roundtrip_image():
    original = ImageCaption(caption="Glow up", alt_text="Woman posing")
    json_str = original.model_dump_json()
    restored = _BELLA_OUTPUT_ADAPTER.validate_json(json_str)
    assert isinstance(restored, ImageCaption)
    assert restored.caption == "Glow up"

def test_bella_output_json_roundtrip_infographic():
    original = InfographicContent(title="Tips", points=["a", "b"], cta="Save")
    json_str = original.model_dump_json()
    restored = _BELLA_OUTPUT_ADAPTER.validate_json(json_str)
    assert isinstance(restored, InfographicContent)
    assert restored.title == "Tips"


def test_content_job_has_content_type_and_bella_output():
    job = ContentJob(project="test", pm=make_pm(), brief="b", platforms=["instagram"])
    assert job.content_type is None
    assert job.bella_output is None

def test_content_job_bella_output_set_and_roundtrip():
    job = ContentJob(project="test", pm=make_pm(), brief="b", platforms=["instagram"])
    job.bella_output = Script(hook="h", body="b", cta="c", duration_seconds=30)
    json_str = job.model_dump_json()
    restored = ContentJob.model_validate_json(json_str)
    assert isinstance(restored.bella_output, Script)
    assert restored.bella_output.hook == "h"

def test_content_job_bella_output_article_roundtrip():
    job = ContentJob(project="test", pm=make_pm(), brief="b", platforms=["instagram"])
    job.bella_output = Article(heading="Title", body="Body text", cta="CTA")
    json_str = job.model_dump_json()
    restored = ContentJob.model_validate_json(json_str)
    assert isinstance(restored.bella_output, Article)
    assert restored.bella_output.heading == "Title"

def test_content_job_content_type_roundtrip():
    job = ContentJob(project="test", pm=make_pm(), brief="b", platforms=["instagram"])
    job.content_type = ContentType.VIDEO
    restored = ContentJob.model_validate_json(job.model_dump_json())
    assert restored.content_type == ContentType.VIDEO

def test_content_job_content_type_and_bella_output_roundtrip():
    job = ContentJob(project="test", pm=make_pm(), brief="b", platforms=["instagram"])
    job.content_type = ContentType.ARTICLE
    job.bella_output = Article(heading="Title", body="Body text", cta="CTA")
    restored = ContentJob.model_validate_json(job.model_dump_json())
    assert restored.content_type == ContentType.ARTICLE
    assert isinstance(restored.bella_output, Article)

def test_growth_strategy_editorial_guidance_default():
    g = GrowthStrategy(
        hashtags=["#a"], caption="cap",
        best_post_time_utc="13:00", best_post_time_thai="20:00",
    )
    assert g.editorial_guidance == {}

def test_growth_strategy_editorial_guidance_custom():
    g = GrowthStrategy(
        hashtags=["#a"], caption="cap",
        best_post_time_utc="13:00", best_post_time_thai="20:00",
        editorial_guidance={"instagram": "Hook within 3 seconds."},
    )
    assert g.editorial_guidance["instagram"] == "Hook within 3 seconds."

def test_content_job_published_at_defaults_none():
    job = ContentJob(project="test", pm=make_pm(), brief="b", platforms=["instagram"])
    assert job.published_at is None

def test_content_job_published_at_serializes():
    from datetime import datetime, timezone
    job = ContentJob(project="test", pm=make_pm(), brief="b", platforms=["instagram"])
    job.published_at = datetime(2026, 5, 17, 14, 0, 0, tzinfo=timezone.utc)
    data = job.model_dump_json()
    assert "published_at" in data
    job2 = ContentJob.model_validate_json(data)
    assert job2.published_at == job.published_at
