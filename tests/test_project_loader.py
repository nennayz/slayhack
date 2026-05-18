import pytest
from project_loader import (
    list_project_slugs,
    load_platform_specs,
    load_project,
    load_project_bridge,
    ProjectNotFoundError,
    resolve_project_slug,
)
from models.content_job import PMProfile, ContentType


def test_load_slay_hack():
    pm = load_project("slay_hack")
    assert isinstance(pm, PMProfile)
    assert pm.name == "Slay"
    assert pm.page_name == "Slayhack"
    assert "male Project Manager" in pm.persona
    assert "Format A" in pm.persona
    assert "e-book product lane" in pm.persona
    assert pm.brand.nora_max_retries == 2
    assert "#F06292" in pm.brand.visual.colors
    assert "18-44" in pm.brand.target_audience
    assert "Slay Hack Commenting Guideline" in pm.brand.comment_reply_style
    assert "No Gatekeeping" in pm.brand.comment_reply_style


def test_load_missing_project_raises():
    with pytest.raises(ProjectNotFoundError, match="nonexistent"):
        load_project("nonexistent")


def test_load_legacy_nayzfreedom_fleet_alias():
    pm = load_project("nayzfreedom_fleet")
    assert pm.name == "Slay"
    assert pm.page_name == "Slayhack"


def test_list_project_slugs_hides_alias_sources():
    assert "slay_hack" in list_project_slugs()
    assert "nayzfreedom_fleet" not in list_project_slugs()


def test_project_slug_alias_falls_back_when_legacy_folder_exists(tmp_path):
    project_dir = tmp_path / "projects" / "nayzfreedom_fleet"
    project_dir.mkdir(parents=True)
    (project_dir / "pm_profile.yaml").write_text("page_name: Legacy\n")

    assert resolve_project_slug("nayzfreedom_fleet", root=tmp_path) == "nayzfreedom_fleet"
    assert list_project_slugs(tmp_path) == ["nayzfreedom_fleet"]


def test_list_project_slugs_hides_pending_scout_projects(tmp_path):
    active = tmp_path / "projects" / "active"
    active.mkdir(parents=True)
    (active / "pm_profile.yaml").write_text("page_name: Active\n")

    pending = tmp_path / "projects" / "pending_scout"
    pending.mkdir(parents=True)
    (pending / "pm_profile.yaml").write_text("page_name: Pending\n")
    (pending / "scout_activation.yaml").write_text("scheduler_rotation_approved: false\n")

    approved = tmp_path / "projects" / "approved_scout"
    approved.mkdir(parents=True)
    (approved / "pm_profile.yaml").write_text("page_name: Approved\n")
    (approved / "scout_activation.yaml").write_text("scheduler_rotation_approved: true\n")

    assert list_project_slugs(tmp_path) == ["active", "approved_scout"]


def test_load_slay_hack_allowed_content_types():
    pm = load_project("slay_hack")
    assert set(pm.brand.allowed_content_types) == {
        ContentType.VIDEO, ContentType.ARTICLE,
        ContentType.IMAGE, ContentType.INFOGRAPHIC,
    }


def test_load_stadium_sweethearts_project():
    pm = load_project("stadium_sweethearts")

    assert pm.name == "Stadium"
    assert pm.page_name == "Stadium Sweethearts"
    assert "male Project Manager" in pm.persona
    assert "sporty" in pm.persona
    assert "fictional" in pm.persona
    assert "21+" in pm.persona
    assert pm.brand.target_audience.startswith("Men in the United States")
    assert pm.brand.allowed_content_types == [ContentType.VIDEO, ContentType.IMAGE]
    assert "#FF4F9A" in pm.brand.visual.colors
    assert "stadium" in pm.brand.visual.style


def test_load_platform_specs_slay_hack():
    specs = load_platform_specs("slay_hack")
    assert "instagram" in specs
    assert "facebook" in specs
    assert "tiktok" in specs
    assert "youtube" in specs
    assert len(specs["instagram"]) > 0

def test_load_platform_specs_missing_project_raises():
    with pytest.raises(ProjectNotFoundError):
        load_platform_specs("nonexistent")

def test_load_platform_specs_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project_dir = tmp_path / "projects" / "test_no_specs"
    project_dir.mkdir(parents=True)
    # No platform_specs.yaml — function should return {}
    result = load_platform_specs("test_no_specs")
    assert result == {}


def test_load_project_bridge_slay_hack():
    bridge = load_project_bridge("slay_hack")

    assert bridge["project"] == "slay_hack"
    assert bridge["display_name"] == "Slay Hack"
    assert bridge["pm"] == "Slay"
    assert bridge["current_phase"] == "ebook_product_launch"
    assert bridge["drive_root"].endswith("My Drive/Slay Hack")
    assert bridge["master_file"] == "Slay Hack Master File/Project Slay Hack - Master Operating File.md"
    assert "Ebook Project/20260517-Ebook-Knowledge-Base.md" in bridge["pm_review_sources"]


def test_load_project_bridge_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project_dir = tmp_path / "projects" / "test_no_bridge"
    project_dir.mkdir(parents=True)

    assert load_project_bridge("test_no_bridge") == {}
