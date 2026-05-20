from __future__ import annotations

from typing import TYPE_CHECKING

from knowledge.object import ContentObject
from models.content_job import ContentJob, ContentType

if TYPE_CHECKING:
    from models.content_job import PMProfile


def idea_to_content_job(
    idea: ContentObject,
    pm: "PMProfile",
    platforms: list[str] | None = None,
    dry_run: bool = False,
) -> ContentJob:
    hook = _extract_hook(idea)
    angle = idea.tags[1] if len(idea.tags) > 1 else ""
    brief = f"{idea.title}: {hook}" + (f" [{angle}]" if angle else "") if hook else idea.title

    content_type = _resolve_content_type(idea.tags)

    job = ContentJob(
        project=idea.page,
        pm=pm,
        brief=brief,
        platforms=platforms or list(pm.brand.platforms),
        dry_run=dry_run,
        idea_uid=idea.uid,
    )
    if content_type is not None:
        job.content_type = content_type
    return job


def _extract_hook(idea: ContentObject) -> str:
    if idea.summary:
        return idea.summary
    for line in idea.body.splitlines():
        stripped = line.strip()
        if stripped.startswith("**Hook:**"):
            return stripped.replace("**Hook:**", "").strip()
    return ""


def _resolve_content_type(tags: list[str]) -> ContentType | None:
    if not tags:
        return None
    try:
        return ContentType(tags[0])
    except ValueError:
        return None
