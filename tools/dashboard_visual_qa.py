from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "8888"
VIEWPORTS = (("desktop", 1280), ("mobile", 390))


@dataclass(frozen=True)
class PageCheck:
    name: str
    path: str
    required_text: tuple[str, ...]
    min_links: int = 1
    forbidden_text: tuple[str, ...] = ()


class DashboardHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self.links: list[str] = []
        self.buttons: list[str] = []
        self.forms: list[str] = []
        self.headings: list[str] = []
        self._active_heading: str | None = None
        self._active_button = False

    @property
    def text(self) -> str:
        return " ".join(" ".join(self._parts).split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {name: value or "" for name, value in attrs}
        if tag == "a" and attrs_map.get("href"):
            self.links.append(attrs_map["href"])
        elif tag == "form":
            self.forms.append(attrs_map.get("action", ""))
        elif tag == "button":
            self._active_button = True
        elif tag in {"h1", "h2", "h3"}:
            self._active_heading = tag

    def handle_endtag(self, tag: str) -> None:
        if tag == "button":
            self._active_button = False
        elif tag == self._active_heading:
            self._active_heading = None

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if not cleaned:
            return
        self._parts.append(cleaned)
        if self._active_button:
            self.buttons.append(cleaned)
        if self._active_heading:
            self.headings.append(cleaned)


def _auth_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _render_local(path: str, root: Path, username: str, password: str) -> tuple[int, str]:
    os.environ.setdefault("DASHBOARD_USER", username)
    os.environ.setdefault("DASHBOARD_PASSWORD", password)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from fastapi.testclient import TestClient
    import dashboard

    dashboard.app.state.root = root
    client = TestClient(dashboard.app, raise_server_exceptions=True)
    response = client.get(path, headers=_auth_header(username, password))
    return response.status_code, response.text


def _fetch_remote(path: str, base_url: str, username: str, password: str) -> tuple[int, str]:
    import requests

    response = requests.get(
        f"{base_url.rstrip('/')}{path}",
        auth=(username, password),
        timeout=20,
    )
    return response.status_code, response.text


def _mission_detail_path(root: Path) -> str | None:
    output_dir = root / "output"
    if not output_dir.exists():
        return None
    job_paths = sorted(output_dir.rglob("job.json"), reverse=True)
    for path in job_paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        job_id = str(data.get("id") or path.parent.name)
        if job_id:
            return f"/jobs/{job_id}"
    return None


def _page_checks(root: Path, mission_path: str | None = None) -> list[PageCheck]:
    mission = mission_path or _mission_detail_path(root)
    checks = [
        PageCheck("captain_deck", "/", ("NayzFreedom Fleet", "Next best action", "Fleet", "Captain Attention Lane", "Captain Action Console", "Command history", "Learning Runbook Proof")),
        PageCheck("aurora", "/aurora", ("The Aurora", "Approval queue", "Generation queue", "Captain Attention Lane", "Captain Action Console", "Command history", "Learning Runbook Proof")),
        PageCheck("daily_slate", "/aurora/daily-slate", ("PM Command Slate", "Project filters", "All pages", "Ticket drawer", "Video package drawer", "PM action plan", "Approval queue")),
        PageCheck("approval_queue", "/aurora/approval-queue", ("Ready but Not Published", "Command lanes", "Approval route", "Next action")),
        PageCheck("manual_posting", "/aurora/manual-posting", ("Manual Post Command Lane", "Manual posting status", "Live publish locked", "Needs Captain")),
        PageCheck(
            "crew",
            "/aurora/crew",
            ("Crew Stations", "Aurora route map", "Fleet Command", "Page PMs", "Aurora Production Route", "Learning Loop", "Captain Nayz", "Stadium"),
            forbidden_text=("video-producer.svg",),
        ),
        PageCheck("crew_detail", "/aurora/crew/robin", ("Back to crew deck", "Station handoff", "Robin")),
        PageCheck("learning", "/aurora/learning", ("Aurora Learning Desk", "Manual Posting Lessons", "Daily Learning Brief intake", "Production canon")),
        PageCheck("ops", "/ops", ("Ops", "Production controls", "Ops summary")),
    ]
    if mission:
        checks.append(
            PageCheck(
                "mission_detail",
                mission,
                (
                    "Current next action",
                    "Live publish locked",
                    "Manual Post Kit",
                    "Download manual kit",
                    "Workflow stage",
                    "Cargo checklist",
                    "Output readiness",
                    "Artifacts",
                ),
            )
        )
    return checks


def _analyze_html(page: PageCheck, status_code: int, html: str) -> dict[str, Any]:
    parser = DashboardHTMLParser()
    parser.feed(html)
    missing = [item for item in page.required_text if item not in parser.text]
    forbidden = [item for item in page.forbidden_text if item in html or item in parser.text]
    duplicate_headings = sorted({heading for heading in parser.headings if parser.headings.count(heading) > 1})
    return {
        "name": page.name,
        "path": page.path,
        "status_code": status_code,
        "ok": status_code == 200 and not missing and not forbidden and len(parser.links) >= page.min_links,
        "missing_text": missing,
        "forbidden_text": forbidden,
        "links": len(parser.links),
        "forms": len(parser.forms),
        "buttons": len(parser.buttons),
        "headings": parser.headings[:8],
        "duplicate_headings": duplicate_headings[:5],
        "bytes": len(html.encode("utf-8")),
    }


def _css_checks(root: Path) -> dict[str, Any]:
    css_path = root / "static" / "style.css"
    if not css_path.exists():
        css_path = Path(__file__).resolve().parents[1] / "static" / "style.css"
    css = css_path.read_text(encoding="utf-8")
    required_patterns = {
        "mobile_media": r"@media\s*\(max-width:\s*860px\)",
        "daily_slate_mobile": r"\.daily-slate-grid",
        "pm_action_mobile": r"\.pm-action-panel",
        "slate_filter_mobile": r"\.slate-filter-tabs",
        "slate_drawer_mobile": r"\.slate-drawer summary",
        "approval_lane_mobile": r"\.approval-lane-board",
        "approval_next_action_mobile": r"\.approval-next-action",
        "captain_attention_mobile": r"\.captain-attention-grid",
        "captain_action_mobile": r"\.captain-action-grid",
        "next_action_mobile": r"\.next-action-panel",
        "workflow_blocks_mobile": r"\.workflow-block summary",
        "crew_sections_mobile": r"\.crew-section-heading",
        "crew_mobile": r"\.crew-grid",
        "no_negative_tracking": r"letter-spacing:\s*-\d",
    }
    checks = {
        key: bool(re.search(pattern, css))
        for key, pattern in required_patterns.items()
    }
    checks["no_negative_tracking"] = not checks["no_negative_tracking"]
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "viewports": [{"name": name, "width": width} for name, width in VIEWPORTS],
    }


def run_visual_qa(
    root: Path,
    *,
    username: str = DEFAULT_USERNAME,
    password: str = DEFAULT_PASSWORD,
    base_url: str | None = None,
    mission_path: str | None = None,
) -> dict[str, Any]:
    pages = []
    for page in _page_checks(root, mission_path=mission_path):
        if base_url:
            status_code, html = _fetch_remote(page.path, base_url, username, password)
        else:
            status_code, html = _render_local(page.path, root, username, password)
        pages.append(_analyze_html(page, status_code, html))
    css = _css_checks(root)
    return {
        "ok": all(page["ok"] for page in pages) and css["ok"],
        "mode": "remote" if base_url else "local",
        "root": str(root),
        "base_url": base_url,
        "pages": pages,
        "css": css,
    }


def _print_text(report: dict[str, Any]) -> None:
    state = "pass" if report["ok"] else "fail"
    print(f"dashboard_visual_qa={state} mode={report['mode']}")
    for page in report["pages"]:
        page_state = "pass" if page["ok"] else "fail"
        print(
            f"{page_state} {page['path']} status={page['status_code']} "
            f"links={page['links']} forms={page['forms']} buttons={page['buttons']} bytes={page['bytes']}"
        )
        if page["missing_text"]:
            print(f"  missing={', '.join(page['missing_text'])}")
        if page["forbidden_text"]:
            print(f"  forbidden={', '.join(page['forbidden_text'])}")
        if page["duplicate_headings"]:
            print(f"  duplicate_headings={', '.join(page['duplicate_headings'])}")
    css_state = "pass" if report["css"]["ok"] else "fail"
    print(f"{css_state} css_mobile_rules={report['css']['checks']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run dashboard UX route and mobile CSS QA checks.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--base-url", help="Optional remote dashboard base URL, for example https://fleet.nayzfreedom.cloud")
    parser.add_argument("--username", default=os.environ.get("DASHBOARD_USER", DEFAULT_USERNAME))
    parser.add_argument("--password", default=os.environ.get("DASHBOARD_PASSWORD", DEFAULT_PASSWORD))
    parser.add_argument("--mission-path", help="Optional mission detail path to check, for example /jobs/20260517_...")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    report = run_visual_qa(
        args.root.resolve(),
        username=args.username,
        password=args.password,
        base_url=args.base_url,
        mission_path=args.mission_path,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_text(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
