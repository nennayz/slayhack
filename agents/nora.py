from __future__ import annotations
from pathlib import Path
from typing import Any, cast
from agents.base_agent import BaseAgent, TEAM_IDENTITY
from models.content_job import (
    ContentJob, ContentType, QAResult,
    Script, Article, ImageCaption, InfographicContent,
)


def _build_qa_user_prompt(job: ContentJob) -> str:
    bella = job.bella_output
    if bella is None:
        raise ValueError("bella_output is None — Bella must run before Nora.")
    if job.content_type is None:
        raise ValueError("content_type is None — cannot build QA prompt.")

    if job.content_type == ContentType.VIDEO and isinstance(bella, Script):
        return (
            f"Script hook: {bella.hook}\n"
            f"Script body: {bella.body}\n"
            f"CTA: {bella.cta}\n"
            f"Visual prompt: {job.visual_prompt}\n"
            f"Video generated: {'Yes' if job.video_path else 'No'}\n\n"
            "Review this video content. Return JSON with keys: passed (bool), "
            "script_feedback (str or null), visual_feedback (str or null), "
            "send_back_to ('bella' | null). JSON only."
        )
    elif job.content_type == ContentType.ARTICLE and isinstance(bella, Article):
        return (
            f"Article heading: {bella.heading}\n"
            f"Article body: {bella.body}\n"
            f"CTA: {bella.cta}\n\n"
            "Review this article content only (no visual). Return JSON with keys: passed (bool), "
            "script_feedback (str or null), visual_feedback (always null for articles), "
            "send_back_to ('bella' | null). JSON only."
        )
    elif job.content_type == ContentType.IMAGE and isinstance(bella, ImageCaption):
        if job.visual_prompt is None:
            raise ValueError("visual_prompt is required for IMAGE QA but is None.")
        return (
            f"Image caption: {bella.caption}\n"
            f"Alt text: {bella.alt_text}\n"
            f"Visual prompt: {job.visual_prompt}\n\n"
            "Review this image content. Return JSON with keys: passed (bool), "
            "script_feedback (str or null), visual_feedback (str or null), "
            "send_back_to ('bella' | 'lila' | null). JSON only."
        )
    elif job.content_type == ContentType.INFOGRAPHIC and isinstance(bella, InfographicContent):
        if job.visual_prompt is None:
            raise ValueError("visual_prompt is required for INFOGRAPHIC QA but is None.")
        points_str = "\n".join(f"- {p}" for p in bella.points)
        return (
            f"Infographic title: {bella.title}\n"
            f"Points:\n{points_str}\n"
            f"CTA: {bella.cta}\n"
            f"Visual prompt: {job.visual_prompt}\n\n"
            "Review this infographic content. Return JSON with keys: passed (bool), "
            "script_feedback (str or null), visual_feedback (str or null), "
            "send_back_to ('bella' | 'lila' | null). JSON only."
        )
    else:
        raise ValueError(
            f"content_type={job.content_type!r} does not match "
            f"bella_output type={type(bella).__name__!r}."
        )


class NoraAgent(BaseAgent):
    def run_dry(self, job: ContentJob, **kwargs) -> ContentJob:
        job.qa_result = QAResult(passed=True)
        job.stage = "nora_done"
        return job

    def run_live(self, job: ContentJob, **kwargs) -> ContentJob:
        if job.content_type == ContentType.VIDEO:
            if not job.video_path:
                job.qa_result = QAResult(passed=False, script_feedback="Video not generated")
                job.nora_retry_count += 1
                job.stage = "nora_done"
                return job
            video_file = Path(job.video_path)
            if not video_file.exists() or video_file.stat().st_size == 0:
                job.qa_result = QAResult(passed=False, script_feedback="Video file missing or empty")
                job.nora_retry_count += 1
                job.stage = "nora_done"
                return job

        system = (
            TEAM_IDENTITY +
            f"You are Nora, QA editor for {job.pm.page_name}. "
            f"Brand tone: {job.pm.brand.tone}. "
            f"Audience: {job.pm.brand.target_audience}. "
            "Be strict. Reject weak hooks, off-brand visuals, and anything that feels generic."
        )
        user = _build_qa_user_prompt(job)
        try:
            raw = self._call_claude(system, user, max_tokens=512)
            result = QAResult(**cast(dict[str, Any], self._parse_json(raw)))
        except Exception:
            result = QAResult(
                passed=False,
                script_feedback="Nora failed to parse Claude response.",
            )
        if job.content_type == ContentType.VIDEO and result.send_back_to == "lila":
            result = result.model_copy(update={"send_back_to": None})
        if not result.passed:
            job.nora_retry_count += 1
        job.qa_result = result
        job.stage = "nora_done"
        return job
