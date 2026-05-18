from __future__ import annotations
from pathlib import Path
import yaml
from models.content_job import BrandProfile, ContentJob, PMProfile, VisualIdentity

_PROJECT_ALIASES = {
    "nayzfreedom_fleet": "slay_hack",
}


class ProjectNotFoundError(Exception):
    pass


def resolve_project_slug(project_slug: str, root: Path | None = None) -> str:
    alias = _PROJECT_ALIASES.get(project_slug)
    if alias is None:
        return project_slug
    base = (root or Path(".")) / "projects"
    if (base / alias).exists():
        return alias
    if (base / project_slug).exists():
        return project_slug
    return project_slug


def project_slug_matches(left: str, right: str, root: Path | None = None) -> bool:
    return resolve_project_slug(left, root=root) == resolve_project_slug(right, root=root)


def list_project_slugs(root: Path | None = None) -> list[str]:
    base = (root or Path(".")) / "projects"
    aliases_with_targets = {
        alias for alias, target in _PROJECT_ALIASES.items()
        if (base / target).exists()
    }
    return sorted(
        p.parent.name for p in base.glob("*/pm_profile.yaml")
        if p.parent.name not in aliases_with_targets
    )


def load_project_page_name(project_slug: str, root: Path | None = None) -> str:
    resolved_slug = resolve_project_slug(project_slug, root=root)
    base = (root or Path(".")) / "projects" / resolved_slug
    try:
        pm_data = yaml.safe_load((base / "pm_profile.yaml").read_text()) or {}
    except (FileNotFoundError, yaml.YAMLError):
        return resolved_slug
    return pm_data.get("page_name") or resolved_slug


def normalize_job_identity(job: ContentJob, root: Path | None = None) -> ContentJob:
    resolved_slug = resolve_project_slug(job.project, root=root)
    job.project = resolved_slug

    page_name = load_project_page_name(resolved_slug, root=root)
    if page_name != resolved_slug:
        job.pm.page_name = page_name
    return job


def load_project(project_slug: str, root: Path | None = None) -> PMProfile:
    resolved_slug = resolve_project_slug(project_slug, root=root)
    base = (root or Path(".")) / "projects" / resolved_slug
    if not base.exists():
        raise ProjectNotFoundError(f"Project '{project_slug}' not found in projects/")

    try:
        pm_data = yaml.safe_load((base / "pm_profile.yaml").read_text())
        brand_data = yaml.safe_load((base / "brand.yaml").read_text())
    except FileNotFoundError as e:
        raise ProjectNotFoundError(f"Missing required file in '{project_slug}': {e.filename}")
    except yaml.YAMLError as e:
        raise ProjectNotFoundError(f"Invalid YAML in '{project_slug}': {e}")

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
    resolved_slug = resolve_project_slug(project_slug, root=root)
    base = (root or Path(".")) / "projects" / resolved_slug
    if not base.exists():
        raise ProjectNotFoundError(f"Project '{project_slug}' not found in projects/")
    specs_path = base / "platform_specs.yaml"
    if not specs_path.exists():
        return {}
    try:
        raw = yaml.safe_load(specs_path.read_text())
    except yaml.YAMLError as e:
        raise ProjectNotFoundError(f"Invalid YAML in platform_specs.yaml for '{project_slug}': {e}")
    return {platform: data["editorial"] for platform, data in raw.items()}


def load_project_bridge(project_slug: str, root: Path | None = None) -> dict:
    resolved_slug = resolve_project_slug(project_slug, root=root)
    base = (root or Path(".")) / "projects" / resolved_slug
    if not base.exists():
        raise ProjectNotFoundError(f"Project '{project_slug}' not found in projects/")
    bridge_path = base / "project_bridge.yaml"
    if not bridge_path.exists():
        return {}
    try:
        return yaml.safe_load(bridge_path.read_text()) or {}
    except yaml.YAMLError as e:
        raise ProjectNotFoundError(f"Invalid YAML in project_bridge.yaml for '{project_slug}': {e}")
