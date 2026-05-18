# E-book Production Dashboard - Design Spec

**Date:** 2026-05-17
**Status:** Proposed
**Scope:** Aurora monetization lane for e-book products

## Problem

SlayHack already has evidence of a working automated e-book pipeline, including a rendered `Age Like Fine Wine` PDF. The gap is Fleet governance: the dashboard needs to show where each e-book sits, which role owns the next step, which QA gates are incomplete, and what Captain must approve before the product is sold.

Without this surface, the pipeline can render a file but the business process remains scattered across Drive, local handoffs, and chat context.

## Solution Overview

Add an Aurora e-book product surface at:

```text
/aurora/ebooks
```

The first version is read-only and planning-focused. It does not run the image generator, render PDFs, publish content, activate checkout, or call platform APIs.

The page should show:

- e-book factory posture
- current pilot asset
- production stages
- role ownership
- QA certification gates
- pipeline hardening checklist
- launch package readiness
- documentation paths
- safe next action

## Navigation

Add an `E-books` link under the Voyage navigation group. The route is part of Aurora because e-books are monetization assets for pages managed by Aurora PMs.

## Data Shape

Initial data can be static Python dictionaries while the system is still in governance design. Future versions can move this into YAML or a durable asset registry.

Suggested shape:

```python
{
    "factory_status": "Governance design ready",
    "safe_boundary": "Read-only planning surface; live publish and checkout stay locked.",
    "pilot": {
        "title": "Age Like Fine Wine",
        "project": "SlayHack",
        "audience": "women 35-44",
        "status": "designed_pdf_ready",
        "next_action": "Run Fleet QA and prepare launch package.",
    },
    "stages": [...],
    "roles": [...],
    "qa_gates": [...],
    "hardening": [...],
    "docs": [...],
}
```

## Page Layout

### Hero

Title: `E-book Product Factory`

Purpose copy: e-books are monetization products, not just PDFs.

Primary actions:

- `Open production runbook`
- `Open dashboard spec`

These can display local doc paths in v1. Later they can link to Drive or authenticated doc routes.

### Status Cards

Cards:

- Pilot
- Current state
- QA gates
- Safe boundary

### Pilot Panel

Show:

- `Age Like Fine Wine`
- SlayHack
- women 35-44
- Book 1.3 production proof
- 22 images, 61 pages, 29.9 MB, about 57.7 minutes, about 0.88 USD
- current state: `designed_pdf_ready`
- next action: Fleet QA and launch package

### Production Stages

Render the canonical state sequence:

```text
idea -> opportunity_qualified -> product_brief_ready -> source_audit_ready -> outline_ready -> chapter_draft_ready -> editor_review_ready -> visual_direction_ready -> designed_pdf_ready -> qa_ready -> captain_approved -> launch_package_ready -> live -> learning_review
```

`designed_pdf_ready` should be marked as the current pilot state. Later states stay locked until QA and Captain approval.

### Role Ownership

Show a compact table:

- Product PM
- Knowledge Reviewer
- Content Architect
- Writer
- Editor
- Brand Reviewer
- Visual Designer
- PDF Producer
- Monetization Lead
- Captain Gate

### QA Certification

Show five gates:

- Content QA
- Brand QA
- Visual QA
- PDF Technical QA
- Monetization QA

Default status for the imported pilot should be `PARTIAL` until Fleet QA is run against the actual PDF and launch package.

### Hardening Checklist

Show technical blockers from the handoff:

- remove hardcoded API key fallback
- make content path configurable
- make output path configurable
- compress images before PDF embed
- keep manifest resume support
- write execution logs
- add PDF bookmarks or interactive TOC

### Launch Package

Show required launch assets:

- sales page
- mockup
- checkout copy
- delivery email
- lead magnet
- 7-day content push
- post-purchase next step
- tracking plan

## Safety Rules

- Do not run live publish from this page.
- Do not activate checkout from this page.
- Do not call OpenAI image/PDF generation in v1.
- Do not mark `captain_approved` automatically.
- Keep PM Slay and Captain Nayz separate in labels and approval copy.

## Test Plan

Add focused dashboard tests:

- `/aurora/ebooks` requires auth through the existing dashboard auth dependency.
- authenticated route renders `E-book Product Factory`.
- route renders `Age Like Fine Wine`.
- route renders `designed_pdf_ready`.
- route renders the five QA gates.
- route renders `Live publish and checkout stay locked`.
- Aurora navigation includes `E-books`.

Run:

```bash
python -m pytest tests/test_dashboard.py -k ebook -q
python -m pytest
```

## Future Work

Once governance is proven:

1. Add an e-book asset registry under `projects/<slug>/`.
2. Add forms for recording QA results.
3. Add Drive sync/readback for e-book artifacts.
4. Add safe dry-run command generation for the pipeline.
5. Add PDF technical inspection helpers.
6. Add launch package checklist state.
7. Add learning review intake after sales or opt-in performance exists.
