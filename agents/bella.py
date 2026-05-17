from __future__ import annotations
from pathlib import Path
from pydantic import TypeAdapter
from agents.base_agent import BaseAgent, TEAM_IDENTITY
from job_store import load_recent_performance
from models.content_job import (
    ContentJob, ContentType,
    Script, Article, ImageCaption, InfographicContent, BellaOutput,
)

_bella_output_adapter = TypeAdapter(BellaOutput)

_DRY_RUN_OUTPUTS: dict[ContentType, BellaOutput] = {
    ContentType.VIDEO: Script(
        hook="wait— you've been doing your lips WRONG this whole time",
        body="step 1: exfoliate. step 2: liner ALL the way around. "
             "step 3: the trick nobody tells you— blot with tissue, dust translucent powder, reapply. "
             "your lips will literally last 8 hours.",
        cta="save this for your next glam sesh bestie",
        duration_seconds=30,
    ),
    ContentType.ARTICLE: Article(
        heading="The Quiet Luxury Lip Trick Nobody's Talking About",
        body="You've been applying lip liner wrong. Here's the three-step method that makes your lips last all day without touch-ups.",
        cta="Bookmark this for your next glam session.",
    ),
    ContentType.IMAGE: ImageCaption(
        caption="the lip hack you didn't know you needed 💋",
        alt_text="Close-up of gold-cased lipstick on ivory marble, soft morning light",
    ),
    ContentType.INFOGRAPHIC: InfographicContent(
        title="3-Step Kiss-Proof Lips",
        points=[
            "Step 1: Exfoliate — use a damp cloth or sugar scrub",
            "Step 2: Line all the way around, slightly outside your natural lip line",
            "Step 3: Blot → translucent powder → reapply. Done.",
        ],
        cta="Save this for your next glam sesh",
    ),
}

_PROMPTS = {
    ContentType.VIDEO: (
        "Write a 15-60 second Reels script. Return JSON with keys: "
        "type (must be \"script\"), hook (str), body (str), cta (str), duration_seconds (int). JSON only."
    ),
    ContentType.ARTICLE: (
        "Write a short article with a compelling heading, body paragraphs, and a CTA. "
        "Return JSON with keys: type (must be \"article\"), heading (str), body (str), cta (str). JSON only."
    ),
    ContentType.IMAGE: (
        "Write a social media image caption and alt text. "
        "Return JSON with keys: type (must be \"image\"), caption (str, max 150 chars), alt_text (str). JSON only."
    ),
    ContentType.INFOGRAPHIC: (
        "Write infographic content: a title, a list of data points or tips, and a CTA. "
        "Return JSON with keys: type (must be \"infographic\"), title (str), points (list of str), cta (str). JSON only."
    ),
}


def _write_bella_output_file(job: ContentJob) -> None:
    out_dir = Path("output") / job.pm.page_name / job.id
    out_dir.mkdir(parents=True, exist_ok=True)
    b = job.bella_output
    if isinstance(b, Script):
        content = f"# Script\n\n**Hook:** {b.hook}\n\n**Body:** {b.body}\n\n**CTA:** {b.cta}\n\n_Duration: {b.duration_seconds}s_"
    elif isinstance(b, Article):
        content = f"# Article\n\n## {b.heading}\n\n{b.body}\n\n**CTA:** {b.cta}"
    elif isinstance(b, ImageCaption):
        content = f"# Image Caption\n\n**Caption:** {b.caption}\n\n**Alt text:** {b.alt_text}"
    elif isinstance(b, InfographicContent):
        points = "\n".join(f"- {p}" for p in b.points)
        content = f"# Infographic\n\n## {b.title}\n\n{points}\n\n**CTA:** {b.cta}"
    else:
        content = str(b)
    (out_dir / "bella_output.md").write_text(content)


class BellaAgent(BaseAgent):
    def run_dry(self, job: ContentJob, **kwargs) -> ContentJob:
        if job.content_type is None:
            raise ValueError("BellaAgent requires content_type to be set.")
        job.bella_output = _DRY_RUN_OUTPUTS[job.content_type]
        job.stage = "bella_done"
        _write_bella_output_file(job)
        return job

    def run_live(self, job: ContentJob, **kwargs) -> ContentJob:
        if job.selected_idea is None or job.content_type is None:
            raise ValueError("BellaAgent requires selected_idea and content_type to be set.")
        idea = job.selected_idea
        system = (
            TEAM_IDENTITY +
            f"You are Bella, a content writer for {job.pm.page_name}. "
            f"Writing style: {job.pm.brand.script_style}. "
            f"Tone: {job.pm.brand.tone}. "
            f"Audience: {job.pm.brand.target_audience}."
        )
        perf_context = load_recent_performance(job.pm.page_name)
        perf_section = f"Past performance data (use to calibrate tone and style):\n{perf_context}\n\n" if perf_context else ""
        user = (
            f"{perf_section}"
            f"Brief: {job.brief}\nIdea: {idea.title}\nHook line: {idea.hook}\nAngle: {idea.angle}\n"
            f"Content type: {job.content_type.value}\nPlatforms: {', '.join(job.platforms)}\n\n"
            + _PROMPTS[job.content_type]
        )
        raw = self._call_claude(system, user, max_tokens=1024)
        job.bella_output = _bella_output_adapter.validate_python(self._parse_json(raw))
        job.stage = "bella_done"
        _write_bella_output_file(job)
        return job
