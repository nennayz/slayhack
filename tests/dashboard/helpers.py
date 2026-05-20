from __future__ import annotations
import base64
import html
import json
import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml
from fastapi.testclient import TestClient

# Set env vars before dashboard is first imported in this process
os.environ["DASHBOARD_USER"] = "admin"
os.environ["DASHBOARD_PASSWORD"] = "8888"

import dashboard as _dm  # noqa: E402

__all__ = [
    "base64",
    "html",
    "json",
    "os",
    "sys",
    "date",
    "Path",
    "patch",
    "MagicMock",
    "pytest",
    "yaml",
    "TestClient",
    "_dm",
    "_auth",
    "_section_after_eyebrow",
    "_make_pm_dict",
    "_write_job",
    "_write_slay_hack_project",
    "_write_stadium_project",
    "_write_ebook_registry",
    "_slay_hack_ticket_id",
    "_project_ticket_id",
    "client",
]


def _auth(user: str = "admin", pw: str = "8888") -> dict:
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _section_after_eyebrow(page: str, eyebrow: str) -> str:
    return page.split(f'<p class="eyebrow">{eyebrow}</p>', 1)[1].split("</section>", 1)[0]


def _make_pm_dict(page_name: str = "Slayhack") -> dict:
    return {
        "name": "Test PM", "page_name": page_name, "persona": "",
        "brand": {
            "mission": "m", "visual": {"colors": [], "style": ""},
            "platforms": [], "tone": "", "target_audience": "",
            "script_style": "", "nora_max_retries": 2,
        },
    }


def _write_job(tmp_path: Path, job_id: str, brief: str = "test brief",
               status: str = "completed", page: str = "Slayhack",
               stage: str = "init", publish_result: dict | None = None,
               performance: list[dict] | None = None,
               manual_post_kit: dict | None = None,
               published_at: str | None = None,
               video_package: dict | None = None,
               production_ticket: dict | None = None) -> None:
    job = {
        "id": job_id, "project": "nayzfreedom_fleet", "pm": _make_pm_dict(page),
        "brief": brief, "platforms": ["facebook"], "status": status,
        "stage": stage, "dry_run": False, "performance": performance or [], "checkpoint_log": [],
    }
    if publish_result is not None:
        job["publish_result"] = publish_result
    if manual_post_kit is not None:
        job["manual_post_kit"] = manual_post_kit
    if published_at is not None:
        job["published_at"] = published_at
    if video_package is not None:
        job["video_package"] = video_package
    if production_ticket is not None:
        job["production_ticket"] = production_ticket
    job_dir = tmp_path / "output" / page / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "job.json").write_text(json.dumps(job))


def _write_slay_hack_project(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "slay_hack"
    project_dir.mkdir(parents=True)
    (project_dir / "pm_profile.yaml").write_text(
        'name: "Slay"\npage_name: "Slay Hack"\npersona: "PM for Slay Hack"\n'
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


def _write_stadium_project(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "stadium_sweethearts"
    project_dir.mkdir(parents=True)
    (project_dir / "pm_profile.yaml").write_text(
        'name: "Stadium"\npage_name: "Stadium Sweethearts"\npersona: "PM for sporty fan-cam content"\n'
    )
    (project_dir / "brand.yaml").write_text(
        'mission: "sporty fan-cam stories"\nvisual:\n  colors: ["#0047ab", "#ffffff"]\n  style: "glossy sports editorial"\n'
        'platforms: ["instagram", "facebook", "tiktok", "youtube"]\ntone: "playful"\n'
        'target_audience: "sports fans"\nscript_style: "stadium bestie"\n'
        'allowed_content_types: ["video", "image", "infographic", "article"]\n'
    )
    (project_dir / "weekly_calendar.yaml").write_text(
        'monday:\n'
        '  short_video_1: "Touchdown Reaction"\n'
        '  long_video: "Game day glow-up story"\n'
        '  article_1: "Fan-cam safety notes"\n'
        '  infographic_1: "Replayable moments card"\n'
    )


def _write_ebook_registry(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "slay_hack"
    project_dir.mkdir(parents=True, exist_ok=True)
    drive_root = tmp_path / "Drive" / "Slay Hack"
    ebook_drive_dir = drive_root / "Ebook Project"
    ebook_drive_dir.mkdir(parents=True, exist_ok=True)
    (ebook_drive_dir / "20260517-Age_Like_Fine_Wine_v1.pdf").write_bytes(b"%PDF-1.4 fine wine proof")
    (ebook_drive_dir / "slay_hack_ebook_updated.docx").write_bytes(b"docx source")
    (ebook_drive_dir / "ebook_universe_map.png").write_bytes(b"png map")
    (ebook_drive_dir / "20260517-Ebook-Knowledge-Base.md").write_text("# Knowledge Base\n")
    (ebook_drive_dir / "20260517-Slay-Ebook-Visual-Strategy.md").write_text("# Visual Strategy\n")
    proof_path = tmp_path / "docs" / "monetization" / "slay_hack" / "artifacts"
    proof_path.mkdir(parents=True, exist_ok=True)
    (proof_path / "20260518-Age_Like_Fine_Wine_v3_visual_proof.pdf").write_bytes(b"%PDF-1.4 fine wine v3 proof")
    (project_dir / "project_bridge.yaml").write_text(
        f'project: slay_hack\n'
        f'display_name: "Slay Hack"\n'
        f'pm: "Slay"\n'
        f'drive_root: "{drive_root}"\n'
    )
    (project_dir / "ebooks.yaml").write_text(
        'factory:\n'
        '  state: "Registry-backed governance ready"\n'
        '  safe_boundary: "Live publish and checkout stay locked until Captain approval."\n'
        '  runbook_path: "docs/ebook_production_runbook.md"\n'
        '  spec_path: "docs/superpowers/specs/2026-05-17-ebook-production-dashboard-design.md"\n'
        '  next_action: "Run Fleet QA against the existing PDF proof, then prepare the launch package."\n'
        'stages:\n'
        '  - key: designed_pdf_ready\n'
        '    label: Designed PDF ready\n'
        '    state: active\n'
        'roles:\n'
        '  - role: Product PM\n'
        '    owner: Slay\n'
        '    responsibility: "Audience and product angle."\n'
        'hardening:\n'
        '  - "Remove hardcoded API key fallback."\n'
        'launch_assets:\n'
        '  - sales page\n'
        '  - 7-day content push\n'
        'monetization_lanes:\n'
        '  - id: fine_wine_35_44\n'
        '    label: "Fine Wine 35-44 Monetization Lane"\n'
        '    audience: "women 35-44"\n'
        '    status: strategy_locked_checkout_locked\n'
        '    strategy: "Start with the strongest real audience before expanding the full 22-SKU universe."\n'
        '    boundary: "Checkout, live publish, and public sales stay locked until Captain approval."\n'
        '    next_action: "Use this lane as the source of truth for sales page and launch assets."\n'
        '    products:\n'
        '      - role: lead_magnet\n'
        '        title: "Slay Basics: 30 Hacks"\n'
        '        status: pdf_ready\n'
        '        purpose: "Email capture and trust step."\n'
        '        next_action: "Bridge readers into Age Like Fine Wine."\n'
        '      - role: paid_pilot\n'
        '        title: "Age Like Fine Wine"\n'
        '        status: designed_pdf_ready\n'
        '        purpose: "First paid low-ticket product."\n'
        '        next_action: "Finish QA and launch asset review."\n'
        '      - role: order_bump\n'
        '        title: "Fine Wine 7-Day Glow Routine"\n'
        '        status: planned\n'
        '        purpose: "Small practical companion."\n'
        '        next_action: "Draft checkout bump copy."\n'
        '      - role: next_book\n'
        '        title: "The Glow Within"\n'
        '        status: roadmap\n'
        '        purpose: "Confidence continuation."\n'
        '        next_action: "Produce after pilot approval."\n'
        '      - role: next_book\n'
        '        title: "She\'s Got It Together"\n'
        '        status: roadmap\n'
        '        purpose: "Life-ease continuation."\n'
        '        next_action: "Produce after bundle validation."\n'
        '    offer_source:\n'
        '      promise: "Help women 35-44 look more polished and feel more intentional."\n'
        '      audience: "Women 35-44 in the USA."\n'
        '      core_offer: "Age Like Fine Wine PDF with routines, checklists, and character-led tips."\n'
        '      pain_desire:\n'
        '        - "Old makeup techniques stop working the same way after 35."\n'
        '      what_inside:\n'
        '        - "Fine Wine Manifesto"\n'
        '        - "30-day glow-up checklist"\n'
        '      bonuses:\n'
        '        - "Fine Wine 7-Day Glow Routine"\n'
        '      guarantee: "Refund policy is not active until checkout terms are approved."\n'
        '      cta: "Start your Fine Wine glow-up"\n'
        '      checkout_boundary: "Checkout copy is draft-only and cannot be activated until Captain approval."\n'
        '    launch_copy_assets:\n'
        '      - key: sales_page\n'
        '        label: "Sales page draft"\n'
        '        launch_asset: sales page\n'
        '        status: review_ready\n'
        '        path: "docs/monetization/slay_hack/age_like_fine_wine_sales_page.md"\n'
        '        review_note: "Use as the first reviewable sales page source; checkout remains locked."\n'
        '      - key: checkout_copy\n'
        '        label: "Checkout copy draft"\n'
        '        launch_asset: checkout copy\n'
        '        status: review_ready\n'
        '        path: "docs/monetization/slay_hack/age_like_fine_wine_checkout_copy.md"\n'
        '        review_note: "Draft checkout and order-bump copy only; no payment link is live."\n'
        'ebooks:\n'
        '  - id: age_like_fine_wine\n'
        '    title: "Age Like Fine Wine"\n'
        '    project: SlayHack\n'
        '    pm: Slay\n'
        '    audience: "women 35-44"\n'
        '    status: designed_pdf_ready\n'
        '    role: "first paid low-ticket monetization pilot"\n'
        '    proof: "Prior handoff reports 22 generated images, 61 PDF pages, 29.9 MB, 57.7 minutes, and about 0.88 USD cost."\n'
        '    source_integrity:\n'
        '      status: pending\n'
        '      proof_path: "docs/monetization/slay_hack/artifacts/20260518-Age_Like_Fine_Wine_v3_visual_proof.pdf"\n'
        '      proof_sha256: "59a2559db88baea300303778be24fcc43a387842ef476065aa30b2df94e410e8"\n'
        '    checkout_setup_gate:\n'
        '      label: "Checkout setup and delivery test"\n'
        '      status: test_setup_packet_ready_checkout_locked\n'
        '      boundary: "Test-mode checkout and delivery smoke must pass before public checkout can open."\n'
        '      next_action: "Record test-mode checkout and delivery smoke evidence."\n'
        '      test_checkout:\n'
        '        provider: "Stripe Checkout Sessions or Payment Links"\n'
        '        mode: "test mode"\n'
        '        product_name: "Age Like Fine Wine"\n'
        '        price_label: "Captain price pending"\n'
        '      secure_delivery:\n'
        '        internal_delivery_route: "/aurora/ebooks/delivery-proof/age_like_fine_wine?project_slug=slay_hack"\n'
        '      receipt_delivery:\n'
        '        delivery_email_asset: "docs/monetization/slay_hack/age_like_fine_wine_delivery_email.md"\n'
        '      public_checkout_gate:\n'
        '        status: locked\n'
        '      smoke_checks:\n'
        '        - key: test_mode_checkout_setup\n'
        '          label: "Test-mode checkout setup"\n'
        '          status: PARTIAL\n'
        '          note: "Setup packet is ready."\n'
        '        - key: secure_delivery_link\n'
        '          label: "Secure delivery link"\n'
        '          status: PENDING\n'
        '          note: ""\n'
        '    drive:\n'
        '      folder: "Ebook Project"\n'
        '      artifacts:\n'
        '        - key: pdf\n'
        '          label: "Rendered PDF proof"\n'
        '          path: "20260517-Age_Like_Fine_Wine_v1.pdf"\n'
        '          expected: "Prior handoff reported 61 pages and 29.9 MB."\n'
        '        - key: docx_source\n'
        '          label: "Editable source document"\n'
        '          path: "slay_hack_ebook_updated.docx"\n'
        '          expected: "Source document for review edits before any regenerated PDF."\n'
        '        - key: universe_map\n'
        '          label: "E-book universe map"\n'
        '          path: "ebook_universe_map.png"\n'
        '          expected: "Visual map for the broader Slay e-book universe."\n'
        '        - key: knowledge_base\n'
        '          label: "E-book knowledge base"\n'
        '          path: "20260517-Ebook-Knowledge-Base.md"\n'
        '          expected: "Source knowledge for the product lane and PM review."\n'
        '        - key: visual_strategy\n'
        '          label: "Visual strategy"\n'
        '          path: "20260517-Slay-Ebook-Visual-Strategy.md"\n'
        '          expected: "Visual direction before PDF or launch mockup revisions."\n'
        '    qa_gates:\n'
        '      - gate: Content QA\n'
        '        status: PARTIAL\n'
        '        check: "Promise and chapter value."\n'
        '      - gate: Brand QA\n'
        '        status: PARTIAL\n'
        '        check: "SlayHack voice."\n'
        '      - gate: Visual QA\n'
        '        status: PARTIAL\n'
        '        check: "Cover and image consistency."\n'
        '      - gate: PDF Technical QA\n'
        '        status: PARTIAL\n'
        '        check: "Dimensions and links."\n'
        '      - gate: Monetization QA\n'
        '        status: PARTIAL\n'
        '        check: "Sales page and checkout copy."\n'
        '    launch_assets:\n'
        '      - name: sales page\n'
        '        status: review_ready\n'
        '        note: "Sales page draft exists."\n'
        '      - key: product_mockup\n'
        '        name: product mockup\n'
        '        status: review_ready\n'
        '        path: "docs/monetization/slay_hack/age_like_fine_wine_product_mockup.md"\n'
        '        note: "Product mockup draft exists."\n'
        '      - name: checkout copy\n'
        '        status: review_ready\n'
        '        note: "Checkout copy draft exists."\n'
        '      - name: 7-day content push\n'
        '        status: review_ready\n'
        '        note: "Manual publish handoff draft exists; live posting remains locked."\n'
        '      - key: post_purchase_next_step\n'
        '        name: post-purchase next step\n'
        '        status: review_ready\n'
        '        path: "docs/monetization/slay_hack/age_like_fine_wine_post_purchase_next_step.md"\n'
        '        note: "Post-purchase next step draft exists."\n'
        '      - key: tracking_plan\n'
        '        name: tracking plan\n'
        '        status: review_ready\n'
        '        path: "docs/monetization/slay_hack/age_like_fine_wine_tracking_plan.md"\n'
        '        note: "Tracking plan draft exists."\n'
    )
    copy_dir = tmp_path / "docs" / "monetization" / "slay_hack"
    copy_dir.mkdir(parents=True, exist_ok=True)
    (copy_dir / "age_like_fine_wine_sales_page.md").write_text(
        "# Age Like Fine Wine - Sales Page Draft\n\nStart your Fine Wine glow-up.\n"
    )
    (copy_dir / "age_like_fine_wine_checkout_copy.md").write_text(
        "# Age Like Fine Wine - Checkout Copy Draft\n\nCheckout copy is draft-only.\n"
    )
    (copy_dir / "age_like_fine_wine_product_mockup.md").write_text(
        "# Age Like Fine Wine - Product Mockup Draft\n\nSales page hero mockup.\n"
    )
    (copy_dir / "age_like_fine_wine_post_purchase_next_step.md").write_text(
        "# Age Like Fine Wine - Post-Purchase Next Step Draft\n\nYour Fine Wine glow-up guide is ready.\n"
    )
    (copy_dir / "age_like_fine_wine_tracking_plan.md").write_text(
        "# Age Like Fine Wine - Tracking Plan Draft\n\nMeasure traffic, conversion, delivery, support, and learning.\n"
    )


def _slay_hack_ticket_id(tmp_path: Path, suffix: str) -> str:
    slate = _dm._calendar_slate(tmp_path)
    assert slate is not None
    return next(ticket.ticket_id for ticket in slate.tickets if ticket.ticket_id.endswith(suffix))


def _project_ticket_id(tmp_path: Path, project_slug: str, suffix: str) -> str:
    slate = _dm._calendar_slate(tmp_path, project_slug)
    assert slate is not None
    return next(ticket.ticket_id for ticket in slate.tickets if ticket.ticket_id.endswith(suffix))


def client(tmp_path):
    _dm.app.state.root = tmp_path
    return TestClient(_dm.app, raise_server_exceptions=True)
