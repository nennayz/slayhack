from __future__ import annotations
import base64
import time
from pathlib import Path
from typing import cast
import openai
from google import genai
from agents.base_agent import BaseAgent, TEAM_IDENTITY
from models.content_job import ContentJob, ContentType, Script, ImageCaption, InfographicContent

_DRY_RUN_PROMPTS = {
    ContentType.VIDEO: (
        "Cinematic close-up of a gold-cased lipstick on ivory marble surface, "
        "soft natural morning light, minimalist Quiet Luxury aesthetic, "
        "white and cream tones, high-end editorial style"
    ),
    ContentType.IMAGE: (
        "Flat-lay of luxury beauty essentials on cream linen, gold accents, "
        "soft diffused light, editorial minimalist style"
    ),
    ContentType.INFOGRAPHIC: (
        "Clean white infographic layout with gold typography, step-by-step icons, "
        "minimalist beauty aesthetic, sans-serif font"
    ),
}
_DRY_RUN_IMAGE = "assets/placeholder.png"
_DRY_RUN_VIDEO = "assets/placeholder.mp4"
_VIDEO_GENERATION_TIMEOUT = 600
_VIDEO_POLL_INTERVAL = 15


class LilaAgent(BaseAgent):
    def run_dry(self, job: ContentJob, **kwargs) -> ContentJob:
        if job.content_type is None:
            raise ValueError(f"LilaAgent requires content_type to be set on job {job.id}")
        if job.content_type == ContentType.ARTICLE:
            job.stage = "lila_done"
            return job
        job.visual_prompt = _DRY_RUN_PROMPTS.get(
            job.content_type,
            _DRY_RUN_PROMPTS[ContentType.VIDEO],
        )
        if job.content_type == ContentType.VIDEO:
            job.video_path = _DRY_RUN_VIDEO
            job.image_path = None
        else:
            job.image_path = _DRY_RUN_IMAGE
        job.stage = "lila_done"
        self._write_prompt_file(job)
        return job

    def run_live(self, job: ContentJob, **kwargs) -> ContentJob:
        if job.content_type is None:
            raise ValueError(f"LilaAgent requires content_type to be set on job {job.id}")
        if job.content_type == ContentType.ARTICLE:
            job.stage = "lila_done"
            return job

        system = (
            TEAM_IDENTITY +
            f"You are Lila, visual director for {job.pm.page_name}. "
            f"Visual style: {job.pm.brand.visual.style}. "
            f"Color palette: {', '.join(job.pm.brand.visual.colors)}."
        )

        bella = job.bella_output
        if job.content_type == ContentType.VIDEO:
            hook_text = bella.hook if isinstance(bella, Script) else str(bella)
            user = (
                f"Script hook: {hook_text}\nBrief: {job.brief}\n"
                "Write a single cinematic video generation prompt for this Reel. "
                "Be specific about lighting, composition, and mood. Plain text only."
            )
            job.visual_prompt = self._call_claude(system, user, max_tokens=256)
            job.video_path = self._generate_video(job)
            job.image_path = None
        elif job.content_type == ContentType.IMAGE:
            caption_text = bella.caption if isinstance(bella, ImageCaption) else str(bella)
            user = (
                f"Caption: {caption_text}\nBrief: {job.brief}\n"
                "Write a single cinematic image generation prompt for this social media image. "
                "Be specific about lighting, composition, and mood. Plain text only."
            )
            job.visual_prompt = self._call_claude(system, user, max_tokens=256)
            job.image_path = self._generate_image(job)
        elif job.content_type == ContentType.INFOGRAPHIC:
            points_text = "; ".join(bella.points) if isinstance(bella, InfographicContent) else str(bella)
            user = (
                f"Infographic points: {points_text}\nBrief: {job.brief}\n"
                "Write a single image generation prompt for this infographic's visual layout. "
                "Describe the layout, typography style, and color palette. Plain text only."
            )
            job.visual_prompt = self._call_claude(system, user, max_tokens=256)
            job.image_path = self._generate_image(job)

        job.stage = "lila_done"
        self._write_prompt_file(job)
        return job

    def _write_prompt_file(self, job: ContentJob) -> None:
        if job.visual_prompt is None:
            return
        out_dir = Path("output") / job.pm.page_name / job.id
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "visual_prompt.txt").write_text(job.visual_prompt)

    def _generate_video(self, job: ContentJob) -> str:
        if not job.visual_prompt:
            raise ValueError(f"visual_prompt must be set before video generation for job {job.id}")
        client = genai.Client(
            vertexai=True,
            project=self.config.google_cloud_project,
            location="us-central1",
        )
        try:
            operation = client.models.generate_videos(
                model="veo-2.0-generate-001",
                prompt=job.visual_prompt,
            )
        except Exception as e:
            raise RuntimeError(
                f"Video generation failed for job {job.id}: {e}"
            ) from e
        start = time.time()
        while not operation.done:
            if time.time() - start > _VIDEO_GENERATION_TIMEOUT:
                raise RuntimeError(
                    f"Video generation timed out after {_VIDEO_GENERATION_TIMEOUT}s "
                    f"for job {job.id}"
                )
            time.sleep(_VIDEO_POLL_INTERVAL)
            operation = client.operations.get(operation)
        try:
            result = operation.result
            if result is None or not result.generated_videos:
                raise RuntimeError("No generated videos returned")
            video = result.generated_videos[0].video
            if video is None or video.video_bytes is None:
                raise RuntimeError("Generated video payload missing bytes")
            video_bytes = cast(bytes, video.video_bytes)
        except Exception as e:
            raise RuntimeError(
                f"Video generation failed for job {job.id}: {e}"
            ) from e
        out_dir = Path("output") / job.pm.page_name / job.id
        out_dir.mkdir(parents=True, exist_ok=True)
        video_path = out_dir / "video.mp4"
        video_path.write_bytes(video_bytes)
        return str(video_path)

    def _generate_image(self, job: ContentJob) -> str:
        if not job.visual_prompt:
            raise ValueError(f"visual_prompt must be set before image generation for job {job.id}")
        client = openai.OpenAI(api_key=self.config.openai_api_key)
        try:
            response = client.images.generate(
                model="gpt-image-2",
                prompt=job.visual_prompt,
                n=1,
                size="1024x1024",
            )
        except openai.OpenAIError as e:
            raise RuntimeError(
                f"Image generation failed for job {job.id} "
                f"({job.content_type}): {e}"
            ) from e
        if not response.data or response.data[0].b64_json is None:
            raise RuntimeError(f"Image generation failed for job {job.id} ({job.content_type}): missing image bytes")
        image_b64 = cast(str, response.data[0].b64_json)
        image_bytes = base64.b64decode(image_b64)
        out_dir = Path("output") / job.pm.page_name / job.id
        out_dir.mkdir(parents=True, exist_ok=True)
        image_path = out_dir / "image.png"
        image_path.write_bytes(image_bytes)
        return str(image_path)
