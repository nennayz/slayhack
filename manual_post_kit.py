from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from models.content_job import ContentJob, ContentType

DEFAULT_CAPTAIN_TIMEZONE = "America/Chicago"
MANUAL_KIT_ROOT_NAME = "NayzFreedom Fleet Manual Kits"

WORK_TYPE_FOLDERS = {
    ContentType.ARTICLE: "01_Articles",
    ContentType.IMAGE: "03_Images",
    ContentType.INFOGRAPHIC: "03_Images",
    ContentType.VIDEO: "04_Video_PreProduction",
}


def captain_timezone() -> str:
    return os.getenv("CAPTAIN_TIMEZONE", DEFAULT_CAPTAIN_TIMEZONE)


def project_folder_name(job: ContentJob) -> str:
    name = (job.pm.page_name or job.project or "Project").strip()
    normalized = re.sub(r"[\s_-]+", "", name).lower()
    if normalized == "slayhack":
        return "SlayHack"
    return _safe_name(name)


def work_type_folder(job: ContentJob) -> str:
    if job.content_type in WORK_TYPE_FOLDERS:
        return WORK_TYPE_FOLDERS[job.content_type]
    if job.trend_data and not job.bella_output:
        return "02_Research"
    return "05_Ready_To_Post"


def drive_folder_path(job: ContentJob) -> list[str]:
    return [project_folder_name(job), work_type_folder(job)]


def manual_kit_filename(job: ContentJob) -> str:
    slug = _slug(job.selected_idea.title if job.selected_idea else job.brief)
    return f"{job.id}_{slug}_manual-kit.zip"


def manual_kit_folder_name(job: ContentJob) -> str:
    slug = _slug(job.selected_idea.title if job.selected_idea else job.brief)
    return f"{job.id}_{slug}"


def manual_kit_summary(job: ContentJob, root: Path) -> dict[str, object]:
    job_dir = _job_dir(root, job)
    drive_root_id = os.getenv("GOOGLE_DRIVE_MANUAL_KITS_FOLDER_ID", "").strip()
    existing = job.manual_post_kit or {}
    drive_sync = existing.get("drive_sync") if isinstance(existing, dict) else None
    manual_post = existing.get("manual_post") if isinstance(existing, dict) else None
    folder_path = [MANUAL_KIT_ROOT_NAME, *drive_folder_path(job)]
    return {
        "label": "Manual Post Kit",
        "state": "ready" if job_dir.exists() else "missing",
        "detail": "Download the structured kit and post manually. Live publishing stays locked.",
        "filename": manual_kit_filename(job),
        "project_folder": project_folder_name(job),
        "work_type_folder": work_type_folder(job),
        "folder_path": " / ".join(folder_path),
        "drive_configured": bool(drive_root_id),
        "drive_sync": drive_sync if isinstance(drive_sync, dict) else None,
        "manual_post": manual_post if isinstance(manual_post, dict) else None,
        "caption_ready": _caption_text(job) != "",
        "hashtags_ready": bool(_hashtags(job)),
        "prompt_pack_ready": bool(job.visual_prompt or _has_video_prompt_pack(job)),
        "asset_ready": bool(_existing_media_paths(root, job)),
        "timezone": captain_timezone(),
    }


def create_manual_post_kit_archive(root: Path, job: ContentJob) -> Path:
    job_dir = _job_dir(root, job)
    if not job_dir.exists() or not job_dir.is_dir():
        raise FileNotFoundError("Job artifact folder not found")

    tmp = tempfile.NamedTemporaryFile(prefix=f"{job.id}-manual-kit-", suffix=".zip", delete=False)
    zip_path = Path(tmp.name)
    tmp.close()

    top_dir = f"{project_folder_name(job)}/{work_type_folder(job)}/{manual_kit_folder_name(job)}"
    generated_files = _generated_files(root, job)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_path, content in generated_files.items():
            archive.writestr(f"{top_dir}/{relative_path}", content)
        for path in sorted(job_dir.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=f"{top_dir}/raw_output/{path.relative_to(job_dir)}")
        for path in _existing_media_paths(root, job):
            archive.write(path, arcname=f"{top_dir}/assets/{path.name}")

    return zip_path


def _generated_files(root: Path, job: ContentJob) -> dict[str, str]:
    files = {
        "README_MANUAL_POST.md": _readme(job),
        "research.md": _research_markdown(job),
        "job.json": job.model_dump_json(indent=2),
    }
    caption = _caption_text(job)
    if caption:
        files["caption.txt"] = caption + "\n"
    hashtags = _hashtags(job)
    if hashtags:
        files["hashtags.txt"] = " ".join(hashtags) + "\n"
    content_file = _bella_output_file(job)
    if content_file:
        files.update(content_file)
    if job.visual_prompt:
        files["visual_prompt.txt"] = job.visual_prompt.strip() + "\n"
    if _has_video_prompt_pack(job):
        files["storyboard.md"] = _storyboard_markdown(job)
        files["video_prompts/google_video_8s.md"] = _google_video_prompts(job)
        files["video_prompts/kling_detailed.md"] = _kling_prompts(job)
        files["video_prompts/seedance2_detailed.md"] = _seedance_prompts(job)
    return files


def _readme(job: ContentJob) -> str:
    lines = [
        f"# Manual Post Kit - {job.id}",
        "",
        f"- Project: {project_folder_name(job)}",
        f"- Work type folder: {work_type_folder(job)}",
        f"- Brief: {job.brief}",
        f"- Platforms: {', '.join(job.platforms)}",
        f"- Content type: {job.content_type.value if job.content_type else 'not set'}",
        f"- Status: {job.status.value}",
        f"- Captain local timezone: {captain_timezone()}",
        "",
        "## Posting Time",
        _posting_time_text(job),
        "",
        "## Manual Workflow",
        "1. Review script/article/caption and visual prompt.",
        "2. Use the prompt package externally if this is video pre-production.",
        "3. Post manually from your platform account.",
        "4. Keep the final platform URL or post ID for later tracking.",
        "",
        "Live publishing from Fleet remains locked unless Captain explicitly approves it.",
        "",
    ]
    return "\n".join(lines)


def _posting_time_text(job: ContentJob) -> str:
    strategy = job.growth_strategy
    if not strategy:
        return "No Roxy timing recommendation recorded yet."
    local = _utc_hhmm_to_local(strategy.best_post_time_utc, captain_timezone())
    lines = []
    if local:
        lines.append(f"- Recommended local time: {local} ({captain_timezone()})")
    if strategy.best_post_time_utc:
        lines.append(f"- UTC reference: {strategy.best_post_time_utc}")
    if strategy.best_post_time_thai:
        lines.append(f"- Thai reference: {strategy.best_post_time_thai}")
    return "\n".join(lines) if lines else "No usable timing recommendation recorded yet."


def _research_markdown(job: ContentJob) -> str:
    if not job.trend_data:
        return "# Research\n\nNo trend research recorded yet.\n"
    return "# Research\n\n```json\n" + json.dumps(job.trend_data, indent=2, ensure_ascii=False) + "\n```\n"


def _bella_output_file(job: ContentJob) -> dict[str, str] | None:
    output = job.bella_output
    if output is None:
        return None
    data = output.model_dump()
    if data["type"] == "article":
        return {"article.md": f"# {data['heading']}\n\n{data['body']}\n\nCTA: {data['cta']}\n"}
    if data["type"] == "script":
        return {
            "script.md": (
                f"# Script\n\n## Hook\n{data['hook']}\n\n## Body\n{data['body']}\n\n"
                f"## CTA\n{data['cta']}\n\nDuration: {data['duration_seconds']} seconds\n"
            )
        }
    if data["type"] == "image":
        return {"image_caption.md": f"# Image Caption\n\n{data['caption']}\n\nAlt text: {data['alt_text']}\n"}
    if data["type"] == "infographic":
        points = "\n".join(f"- {point}" for point in data["points"])
        return {"infographic.md": f"# {data['title']}\n\n{points}\n\nCTA: {data['cta']}\n"}
    return None


def _storyboard_markdown(job: ContentJob) -> str:
    package = job.video_package or {}
    scenes = _video_scenes(job)
    lines = [
        f"# Storyboard - {package.get('title', job.brief)}",
        "",
        f"- Format: {package.get('format_name', 'Video pre-production package')}",
        f"- Total duration: {package.get('total_duration_seconds', 'unknown')} seconds",
        "",
    ]
    if not package.get("total_duration_seconds") and scenes:
        lines[3] = f"- Total duration: {sum(_scene_duration(scene) for scene in scenes)} seconds"
    for scene in scenes:
        lines.extend(
            [
                f"## Scene {scene.get('number')}: {scene.get('purpose')}",
                f"- Timing: {scene.get('start_second')}s-{scene.get('end_second')}s",
                f"- Visual direction: {scene.get('visual_direction')}",
                f"- Prompt: {scene.get('prompt')}",
                "",
            ]
        )
    assets = package.get("asset_checklist") or []
    if assets:
        lines.extend(["## Asset Checklist", *[f"- {asset}" for asset in assets], ""])
    return "\n".join(lines)


def _google_video_prompts(job: ContentJob) -> str:
    return _provider_prompt_doc(
        job,
        "Google Video / Veo - 8 second scenes",
        "Create exactly one 8-second clip for this scene. Keep motion readable, camera movement smooth, and the final frame usable for continuity.",
    )


def _kling_prompts(job: ContentJob) -> str:
    return _provider_prompt_doc(
        job,
        "Kling - detailed cinematic prompts",
        "Use a detailed cinematic prompt with subject, environment, camera movement, lighting, motion, style, and negative prompt.",
    )


def _seedance_prompts(job: ContentJob) -> str:
    return _provider_prompt_doc(
        job,
        "Seedance 2.0 - detailed motion prompts",
        "Use a detailed motion-first prompt with action beats, transition intent, camera path, expression, texture, and pacing.",
    )


def _provider_prompt_doc(job: ContentJob, title: str, instruction: str) -> str:
    lines = [f"# {title}", "", instruction, ""]
    for scene in _video_scenes(job):
        end_second = cast(int, scene.get("end_second", 0)) if isinstance(scene.get("end_second", 0), int) else 0
        start_second = cast(int, scene.get("start_second", 0)) if isinstance(scene.get("start_second", 0), int) else 0
        lines.extend(
            [
                f"## Scene {scene.get('number')} - {scene.get('purpose')}",
                f"Duration: {end_second - start_second} seconds",
                "",
                str(scene.get("prompt") or scene.get("visual_direction") or "").strip(),
                "",
                "Negative prompt: blurry text, warped hands, unreadable UI, low quality, off-brand colors.",
                "",
            ]
        )
    return "\n".join(lines)


def _has_video_prompt_pack(job: ContentJob) -> bool:
    if job.video_package:
        return True
    return job.content_type == ContentType.VIDEO and bool(job.bella_output or job.visual_prompt)


def _video_scenes(job: ContentJob) -> list[dict[str, object]]:
    package = job.video_package if isinstance(job.video_package, dict) else {}
    scenes = package.get("scenes")
    if isinstance(scenes, list) and scenes:
        return [dict(scene) for scene in scenes]
    if job.content_type != ContentType.VIDEO:
        return []
    output = job.bella_output.model_dump() if job.bella_output else {}
    visual = job.visual_prompt or job.brief
    beats = [
        ("hook", output.get("hook") or job.brief),
        ("body", output.get("body") or visual),
        ("cta", output.get("cta") or "Invite the viewer to save, share, or comment."),
    ]
    scenes = []
    cursor = 0
    for index, (purpose, text) in enumerate(beats, start=1):
        end = cursor + 8
        prompt = (
            f"{job.brief}: {purpose}. "
            f"Script beat: {text}. "
            f"Visual direction: {visual}. "
            "Keep this as one clean 8-second pre-production scene."
        )
        scenes.append(
            {
                "number": index,
                "start_second": cursor,
                "end_second": end,
                "purpose": purpose,
                "visual_direction": visual,
                "prompt": prompt,
                "tool_hint": "manual_video_prompt",
            }
        )
        cursor = end
    return scenes


def _scene_duration(scene: dict[str, object]) -> int:
    try:
        end_second_raw = scene.get("end_second", 0)
        start_second_raw = scene.get("start_second", 0)
        return int(str(end_second_raw or 0)) - int(str(start_second_raw or 0))
    except (TypeError, ValueError):
        return int(str(scene.get("duration_seconds", 8) or 8))


def _caption_text(job: ContentJob) -> str:
    package = job.publish_package if isinstance(job.publish_package, dict) else {}
    if package.get("caption"):
        return str(package["caption"]).strip()
    if job.growth_strategy and job.growth_strategy.caption:
        return job.growth_strategy.caption.strip()
    return ""


def _hashtags(job: ContentJob) -> list[str]:
    package = job.publish_package if isinstance(job.publish_package, dict) else {}
    raw = package.get("hashtags") or (job.growth_strategy.hashtags if job.growth_strategy else [])
    return [str(tag).strip() for tag in raw if str(tag).strip()]


def _existing_media_paths(root: Path, job: ContentJob) -> list[Path]:
    paths = []
    for value in (job.image_path, job.video_path):
        if not value:
            continue
        path = Path(str(value))
        resolved = path if path.is_absolute() else root / path
        if resolved.exists():
            paths.append(resolved)
    return paths


def _job_dir(root: Path, job: ContentJob) -> Path:
    return root / "output" / job.pm.page_name / job.id


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^\w .()-]+", "", value).strip()
    return cleaned or "Project"


def _slug(value: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return (slug[:max_len].strip("-") or "mission")


def _utc_hhmm_to_local(value: str | None, tz_name: str) -> str | None:
    if not value:
        return None
    match = re.match(r"^(\d{1,2}):(\d{2})", value.strip())
    if not match:
        return None
    try:
        local_tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        local_tz = ZoneInfo(DEFAULT_CAPTAIN_TIMEZONE)
    now = datetime.now(timezone.utc)
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    utc_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return utc_dt.astimezone(local_tz).strftime("%I:%M %p").lstrip("0")
