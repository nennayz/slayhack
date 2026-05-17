from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["DASHBOARD_USER"] = "admin"
os.environ["DASHBOARD_PASSWORD"] = "8888"

import dashboard as _dm  # noqa: E402
from tools.dashboard_visual_qa import run_visual_qa  # noqa: E402


def _write_project(root: Path) -> None:
    project_dir = root / "projects" / "nayzfreedom_fleet"
    project_dir.mkdir(parents=True)
    (project_dir / "pm_profile.yaml").write_text(
        'name: "Slay"\npage_name: "Slay Hack"\npersona: "PM for SlayHack"\n'
    )
    (project_dir / "brand.yaml").write_text(
        'mission: "beauty content"\nvisual:\n  colors: ["#fff"]\n  style: "warm 3D"\n'
        'platforms: ["instagram", "facebook", "tiktok", "youtube"]\ntone: "sassy"\n'
        'target_audience: "Gen Z women"\nscript_style: "bestie"\n'
        'allowed_content_types: ["video", "image", "infographic", "article"]\n'
    )
    (project_dir / "weekly_calendar.yaml").write_text(
        'monday:\n'
        '  short_video_1: "Quick hack"\n'
        '  long_video: "Long story episode"\n'
        '  article_1: "Guide one"\n'
        '  article_2: "Guide two"\n'
        '  infographic_1: "Save card one"\n'
        '  infographic_2: "Save card two"\n'
    )


def _write_job(root: Path) -> None:
    job_id = "20260517_visual_qa"
    payload = {
        "id": job_id,
        "project": "nayzfreedom_fleet",
        "pm": {
            "name": "Slay",
            "page_name": "Slay Hack",
            "persona": "PM",
            "brand": {
                "mission": "beauty content",
                "visual": {"colors": ["#fff"], "style": "warm 3D"},
                "platforms": ["instagram", "facebook"],
                "tone": "sassy",
                "target_audience": "Gen Z women",
                "script_style": "bestie",
                "nora_max_retries": 2,
            },
        },
        "brief": "Visual QA mission",
        "platforms": ["instagram", "facebook"],
        "status": "awaiting_approval",
        "stage": "publish_scheduled",
        "dry_run": True,
        "performance": [],
        "checkpoint_log": [],
        "video_package": {
            "title": "Video package mission: Visual QA",
            "owner": "Vera Reel",
            "format_name": "Short reel",
            "platform_primary": "instagram",
            "total_duration_seconds": 30,
            "asset_checklist": ["Hero portrait", "Caption file"],
            "scenes": [
                {
                    "start_second": 0,
                    "end_second": 15,
                    "purpose": "Hook",
                    "prompt": "Show the Aurora deck opening a mission.",
                },
                {
                    "start_second": 15,
                    "end_second": 30,
                    "purpose": "Handoff",
                    "prompt": "Show Roxy and Emma preparing the publish package.",
                },
            ],
        },
        "generation_request": {
            "status": "completed",
            "next_action": "Generated video is attached.",
            "tool_hint": "veo3",
        },
        "generation_result": {
            "status": "completed",
            "message": "Real generated video is attached to this mission.",
            "output_path": "output/Slay Hack/20260517_visual_qa/video.mp4",
            "provider": "manual_upload",
            "publish_packaging": {
                "status": "ready",
                "next_action": "Roxy and Emma can package caption, hashtags, FAQ, and publish prep.",
            },
        },
        "video_path": "output/Slay Hack/20260517_visual_qa/video.mp4",
        "publish_package": {
            "status": "completed",
            "caption": "Visual QA caption",
            "hashtags": ["#slayhack"],
            "faq_path": "output/Slay Hack/20260517_visual_qa/faq.md",
            "publish_notes": "Captain approved handoff only.",
        },
        "publish_execution": {
            "status": "scheduled",
            "platforms": ["instagram", "facebook"],
            "next_action": "Dashboard handoff only.",
        },
        "publish_result": {"instagram": {"status": "scheduled", "dry_run": True}},
    }
    job_dir = root / "output" / "Slay Hack" / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "job.json").write_text(json.dumps(payload))


def test_dashboard_visual_qa_local_report_passes(tmp_path, monkeypatch):
    _write_project(tmp_path)
    _write_job(tmp_path)
    monkeypatch.setattr(
        _dm,
        "_ops_unit_status",
        lambda: [{"name": "nayzfreedom-dashboard.service", "state": "Ready", "detail": "active"}],
    )
    monkeypatch.setattr(_dm, "_latest_backup_status", lambda: {"state": "Ready", "detail": "backup-ok"})

    report = run_visual_qa(tmp_path)

    assert report["ok"] is True
    assert {page["name"] for page in report["pages"]} >= {
        "captain_deck",
        "aurora",
        "daily_slate",
        "approval_queue",
        "crew",
        "crew_detail",
        "ops",
        "mission_detail",
    }
    assert report["css"]["checks"]["mobile_media"] is True
    assert report["css"]["checks"]["crew_sections_mobile"] is True
    assert report["css"]["checks"]["pm_action_mobile"] is True
    assert report["css"]["checks"]["slate_filter_mobile"] is True
    assert report["css"]["checks"]["slate_drawer_mobile"] is True
    assert report["css"]["checks"]["approval_next_action_mobile"] is True
    assert report["css"]["checks"]["no_negative_tracking"] is True
    crew = next(page for page in report["pages"] if page["name"] == "crew")
    assert crew["forbidden_text"] == []


def test_fleet_theme_assets_and_css_exist():
    root = Path(__file__).resolve().parents[1]
    asset_dir = root / "static" / "theme" / "fleet"
    expected = {
        "command-bridge.svg",
        "route-map.svg",
        "harbor-gate.svg",
        "engine-room.svg",
        "voyage-log.svg",
    }
    assert expected <= {path.name for path in asset_dir.glob("*.svg")}
    css = (root / "static" / "style.css").read_text()
    for name in expected:
        assert f"/static/theme/fleet/{name}" in css


def test_dashboard_visual_qa_reports_missing_required_text(tmp_path, monkeypatch):
    _write_project(tmp_path)
    monkeypatch.setattr(
        _dm,
        "_ops_unit_status",
        lambda: [{"name": "nayzfreedom-dashboard.service", "state": "Ready", "detail": "active"}],
    )
    monkeypatch.setattr(_dm, "_latest_backup_status", lambda: {"state": "Ready", "detail": "backup-ok"})

    report = run_visual_qa(tmp_path, mission_path="/does-not-exist")

    mission = next(page for page in report["pages"] if page["name"] == "mission_detail")
    assert report["ok"] is False
    assert mission["status_code"] == 404
    assert mission["ok"] is False
