from __future__ import annotations

from pathlib import Path

import yaml

from models.content_job import BrandProfile, ContentJob, PMProfile, VisualIdentity

_CANONICAL_PROJECT_SLUG = "nayzfreedom_fleet"
_PROJECT_ALIASES = {
    "slay_hack": _CANONICAL_PROJECT_SLUG,
}


class ProjectNotFoundError(Exception):
    pass


def resolve_project_slug(project_slug: str, root: Path | None = None) -> str:
    canonical = _PROJECT_ALIASES.get(project_slug, project_slug)
    base = (root or Path(".")) / "projects"
    if (base / canonical).exists():
        return canonical
    if (base / project_slug).exists():
        return project_slug
    return canonical


def _project_search_dirs(project_slug: str, root: Path | None = None) -> list[Path]:
    base = (root or Path(".")) / "projects"
    resolved_slug = resolve_project_slug(project_slug, root=root)
    candidates = [base / resolved_slug]
    legacy_sources = [slug for slug, target in _PROJECT_ALIASES.items() if target == resolved_slug]
    for slug in legacy_sources:
        legacy_dir = base / slug
        if legacy_dir not in candidates:
            candidates.append(legacy_dir)
    direct_dir = base / project_slug
    if direct_dir not in candidates:
        candidates.append(direct_dir)
    return candidates


def _first_existing_project_dir(project_slug: str, root: Path | None = None) -> Path:
    for candidate in _project_search_dirs(project_slug, root=root):
        if candidate.exists():
            return candidate
    raise ProjectNotFoundError(f"Project '{project_slug}' not found in projects/")


def _read_project_yaml(project_slug: str, filename: str, root: Path | None = None, default: object | None = None):
    for candidate in _project_search_dirs(project_slug, root=root):
        path = candidate / filename
        if not path.exists():
            continue
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            raise ProjectNotFoundError(f"Invalid YAML in '{path}': {exc}")
        return default if data is None else data
    if default is not None:
        return default
    raise ProjectNotFoundError(f"Missing required file for '{project_slug}': {filename}")


def project_slug_matches(left: str, right: str, root: Path | None = None) -> bool:
    return resolve_project_slug(left, root=root) == resolve_project_slug(right, root=root)


def list_project_slugs(root: Path | None = None) -> list[str]:
    base = (root or Path(".")) / "projects"
    seen: set[str] = set()
    project_slugs: list[str] = []
    for pm_profile in sorted(base.glob("*/pm_profile.yaml")):
        raw_slug = pm_profile.parent.name
        canonical_slug = resolve_project_slug(raw_slug, root=root)
        if canonical_slug in seen:
            continue
        canonical_dir = base / canonical_slug
        if not canonical_dir.exists():
            canonical_dir = pm_profile.parent
        if not _scheduler_rotation_approved(canonical_dir):
            continue
        seen.add(canonical_slug)
        project_slugs.append(canonical_slug)
    return sorted(project_slugs)


def _scheduler_rotation_approved(project_dir: Path) -> bool:
    activation_path = project_dir / "scout_activation.yaml"
    if not activation_path.exists():
        return True
    try:
        data = yaml.safe_load(activation_path.read_text()) or {}
    except yaml.YAMLError:
        return False
    return bool(data.get("scheduler_rotation_approved"))


def load_project_page_name(project_slug: str, root: Path | None = None) -> str:
    try:
        pm_data = _read_project_yaml(project_slug, "pm_profile.yaml", root=root, default={}) or {}
    except ProjectNotFoundError:
        return resolve_project_slug(project_slug, root=root)
    return pm_data.get("page_name") or resolve_project_slug(project_slug, root=root)


def normalize_job_identity(job: ContentJob, root: Path | None = None) -> ContentJob:
    resolved_slug = resolve_project_slug(job.project, root=root)
    job.project = resolved_slug

    page_name = load_project_page_name(resolved_slug, root=root)
    if page_name != resolved_slug:
        job.pm.page_name = page_name
    return job


def load_project(project_slug: str, root: Path | None = None) -> PMProfile:
    _first_existing_project_dir(project_slug, root=root)
    pm_data = _read_project_yaml(project_slug, "pm_profile.yaml", root=root)
    brand_data = _read_project_yaml(project_slug, "brand.yaml", root=root)

    extra: dict = {}
    if "allowed_content_types" in brand_data:
        extra["allowed_content_types"] = brand_data["allowed_content_types"]

    brand = BrandProfile(
        mission=brand_data["mission"],
        visual=VisualIdentity(**brand_data["visual"]),
        platforms=brand_data["platforms"],
        tone=brand_data["tone"],
        target_audience=brand_data["target_audience"],
        script_style=brand_data["script_style"],
        comment_reply_style=brand_data.get("comment_reply_style", ""),
        nora_max_retries=brand_data.get("nora_max_retries", 2),
        **extra,
    )
    return PMProfile(
        name=pm_data["name"],
        page_name=pm_data["page_name"],
        persona=pm_data["persona"].strip(),
        brand=brand,
    )


def load_platform_specs(project_slug: str, root: Path | None = None) -> dict[str, str]:
    _first_existing_project_dir(project_slug, root=root)
    raw = _read_project_yaml(project_slug, "platform_specs.yaml", root=root, default={})
    return {platform: data["editorial"] for platform, data in raw.items()}


def load_project_bridge(project_slug: str, root: Path | None = None) -> dict:
    _first_existing_project_dir(project_slug, root=root)
    return _read_project_yaml(project_slug, "project_bridge.yaml", root=root, default={})
