from __future__ import annotations
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from config import Config
from models.content_job import ContentType
from models.niche_opportunity import NicheOpportunity, ScoutJob

logger = logging.getLogger(__name__)

_PROJECTS_ROOT = Path(__file__).resolve().parent.parent / "projects"


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _normalize_content_formats(formats: list[str]) -> list[str]:
    normalized: list[str] = []
    aliases = [
        (ContentType.VIDEO.value, ("video", "reel", "short form", "shortform", "clip")),
        (ContentType.INFOGRAPHIC.value, ("infographic", "cheat sheet", "chart", "diagram")),
        (ContentType.ARTICLE.value, ("article", "blog", "essay", "newsletter", "listicle", "explainer")),
        (ContentType.IMAGE.value, ("image", "photo", "carousel", "ootd", "post")),
    ]
    for raw in formats:
        text = str(raw or "").strip().lower().replace("_", " ").replace("-", " ")
        match = next(
            (content_type for content_type, markers in aliases if any(marker in text for marker in markers)),
            None,
        )
        if match and match not in normalized:
            normalized.append(match)
    return normalized or [ContentType.VIDEO.value, ContentType.INFOGRAPHIC.value, ContentType.ARTICLE.value]


def _brand_yaml(opp: NicheOpportunity) -> dict:
    content_formats = _normalize_content_formats(opp.content_formats)
    return {
        "mission": (
            f"Character-driven {opp.niche_name} content that builds a loyal audience "
            f"of {opp.target_audience} and converts trust into owned products."
        ),
        "visual": {
            "style": "warm 3D Pixar CGI, expressive lifestyle objects, soft left-side lighting, vertical 9:16",
            "colors": ["#FFFFFF", "#F5F5DC", "#D4AF37"],
        },
        "platforms": opp.platforms,
        "tone": "smart, supportive, aspirational, never preachy",
        "target_audience": opp.target_audience,
        "script_style": (
            "English only, casual bestie voice, punchy hook in first three words, "
            "no corporate language"
        ),
        "nora_max_retries": 2,
        "allowed_content_types": content_formats,
    }


def _pm_profile_yaml(opp: NicheOpportunity, slug: str) -> dict:
    page_name = slug.replace("_", " ").title().replace(" ", "")
    return {
        "name": "Alex",
        "page_name": page_name,
        "persona": (
            f"You are Alex, the Project Manager for {page_name}. "
            f"You produce {opp.niche_name} content for {opp.target_audience}. "
            f"Your content stops the scroll, builds community, and moves the audience "
            f"toward owned products. Priority: {opp.trend_direction} trend, reach first."
        ),
    }


def _platform_specs_yaml(opp: NicheOpportunity) -> dict:
    content_formats = _normalize_content_formats(opp.content_formats)
    return {
        platform: {"primary": True, "content_types": content_formats}
        for platform in opp.platforms
    }


def _weekly_calendar_yaml(opp: NicheOpportunity) -> dict:
    formats = set(_normalize_content_formats(opp.content_formats))
    schedule = {}
    if ContentType.VIDEO.value in formats:
        schedule["monday"] = {"short_video_1": f"{opp.niche_name} hack"}
        schedule["friday"] = {"short_video_2": f"{opp.niche_name} trend"}
    if ContentType.ARTICLE.value in formats:
        schedule["wednesday"] = {"article_1": f"{opp.niche_name} story"}
    if ContentType.INFOGRAPHIC.value in formats:
        schedule["sunday"] = {"infographic_1": f"{opp.niche_name} tips"}
    return schedule or {"monday": {"short_video_1": f"{opp.niche_name} hack"}}


def _scout_activation_yaml(job: ScoutJob, opp: NicheOpportunity) -> dict:
    return {
        "source": "scout",
        "source_report": job.job_id,
        "niche_name": opp.niche_name,
        "status": "captain_review",
        "scheduler_rotation_approved": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "review_notes": "Dry-run proof required before scheduler rotation approval.",
    }


class ArchitectAgent:
    def __init__(self, config: Config):
        self.config = config

    def run(self, job: ScoutJob, projects_root: Path = _PROJECTS_ROOT, dry_run: bool = False) -> str:
        opp = self._find_approved_opportunity(job)
        slug = _slugify(opp.niche_name)
        if dry_run:
            logger.info("Architect dry-run: would create projects/%s/", slug)
            return slug
        self._write_project(slug, opp, projects_root, job)
        # Record completion message on job for callers who inspect job state after approval
        job.status_message = f"Project {slug} created at projects/{slug}/"
        return slug

    def _find_approved_opportunity(self, job: ScoutJob) -> NicheOpportunity:
        if not job.approved_niche:
            raise ValueError("No approved_niche set on ScoutJob")
        approved_lower = job.approved_niche.lower()
        for opp in job.opportunities:
            if opp.niche_name.lower() == approved_lower:
                return opp
        raise ValueError(f"Approved niche '{job.approved_niche}' not found in opportunities")

    def _write_project(self, slug: str, opp: NicheOpportunity, root: Path, job: ScoutJob) -> None:
        project_dir = root / slug
        project_dir.mkdir(parents=True, exist_ok=True)

        files = {
            "brand.yaml": _brand_yaml(opp),
            "pm_profile.yaml": _pm_profile_yaml(opp, slug),
            "platform_specs.yaml": _platform_specs_yaml(opp),
            "weekly_calendar.yaml": _weekly_calendar_yaml(opp),
            "scout_activation.yaml": _scout_activation_yaml(job, opp),
        }
        for filename, data in files.items():
            (project_dir / filename).write_text(
                yaml.dump(data, allow_unicode=True, default_flow_style=False),
                encoding="utf-8",
            )
        logger.info("Architect: created project at projects/%s/", slug)
