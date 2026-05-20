from __future__ import annotations
from pathlib import Path
from typing import Any, cast
from agents.base_agent import BaseAgent, TEAM_IDENTITY
from models.content_job import ContentJob, GrowthStrategy
from project_loader import load_platform_specs

_DRY_RUN_STRATEGY = GrowthStrategy(
    hashtags=["#LongLastingLips","#GlossyLips","#LipHack","#QuietLuxury","#BeautyHacks","#GlowUp"],
    caption="the lip hack you didn't know you needed 💋 save this before your next glam sesh",
    best_post_time_utc="13:00",
    best_post_time_thai="20:00",
    editorial_guidance={
        "instagram": "Hook within 3 seconds. Caption under 150 chars. Hashtags in first comment.",
        "facebook": "Conversational tone. 1-3 sentences. Hashtags optional, inline.",
        "tiktok": "Text overlay on video. CTA in last 3 seconds. Sound-on assumed. Trending audio boosts reach.",
        "youtube": "Thumbnail-first mindset. Title under 60 chars. Description with timestamps. First 30 seconds must hook.",
    },
)


def _write_growth_file(job: ContentJob) -> None:
    g = job.growth_strategy
    if g is None:
        raise ValueError(f"growth_strategy is not set for job {job.id}")
    out_dir = Path("output") / job.pm.page_name / job.id
    out_dir.mkdir(parents=True, exist_ok=True)
    guidance_lines = ""
    if g.editorial_guidance:
        items = "\n".join(f"  - **{p}:** {text}" for p, text in g.editorial_guidance.items())
        guidance_lines = f"\n\n## Editorial Guidance\n\n{items}"
    (out_dir / "growth.md").write_text(
        f"# Growth Strategy\n\n**Caption:** {g.caption}\n\n"
        f"**Hashtags:** {' '.join(g.hashtags)}\n\n"
        f"**Best post time:** {g.best_post_time_utc} UTC / {g.best_post_time_thai} Thai"
        + guidance_lines
    )


class RoxyAgent(BaseAgent):
    def run_dry(self, job: ContentJob, **kwargs) -> ContentJob:
        job.growth_strategy = _DRY_RUN_STRATEGY
        job.stage = "roxy_done"
        _write_growth_file(job)
        return job

    def run_live(self, job: ContentJob, **kwargs) -> ContentJob:
        if job.bella_output is None:
            raise ValueError(f"RoxyAgent requires bella_output to be set on job {job.id}")
        bella = job.bella_output
        if hasattr(bella, "hook"):
            content_ref = f"Script hook: {bella.hook}"
        elif hasattr(bella, "heading"):
            content_ref = f"Article heading: {bella.heading}"
        elif hasattr(bella, "caption"):
            content_ref = f"Image caption: {bella.caption}"
        elif hasattr(bella, "title"):
            content_ref = f"Infographic title: {bella.title}"
        else:
            content_ref = f"Content: {str(bella)}"

        system = (
            TEAM_IDENTITY +
            f"You are Roxy, growth strategist for {job.pm.page_name}. "
            f"Target audience: {job.pm.brand.target_audience}. "
            f"Platforms: {', '.join(job.platforms)}."
        )
        user = (
            f"Brief: {job.brief}\n{content_ref}\n"
            "Provide 5-10 hashtags, a short caption, and optimal post times for USA audience. "
            "Return JSON with keys: hashtags (list of str), caption (str), "
            "best_post_time_utc (str HH:MM), best_post_time_thai (str HH:MM). JSON only."
        )
        raw = self._call_claude(system, user, max_tokens=512)
        parsed = cast(dict[str, Any], self._parse_json(raw))

        try:
            all_specs = load_platform_specs(job.project)
        except Exception:
            all_specs = {}
        parsed["editorial_guidance"] = {
            p: str(all_specs[p]) for p in job.platforms if p in all_specs
        }

        job.growth_strategy = GrowthStrategy(**parsed)
        job.stage = "roxy_done"
        _write_growth_file(job)
        return job
