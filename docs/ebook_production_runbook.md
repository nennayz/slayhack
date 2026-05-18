# E-book Production Runbook

**Date:** 2026-05-17
**Status:** Working runbook
**Scope:** NayzFreedom Fleet monetization assets, starting with SlayHack

## Purpose

E-books are a monetization asset class for any Fleet page that has a clear audience, useful knowledge, and a brand voice strong enough to sell trust. The goal is not only to produce a PDF. The goal is to produce a reusable product package: source knowledge, content architecture, visual system, PDF, QA proof, launch copy, delivery path, and learning feedback.

The first pilot is SlayHack's `Age Like Fine Wine`, based on the existing handoff for the automated e-book pipeline.

## Source Handoff

The existing SlayHack handoff describes a working automated pipeline:

- YAML config per book
- Markdown source content
- character style prompt system
- OpenAI image generation
- WeasyPrint HTML-to-PDF rendering
- image manifest for resume support
- PDF, HTML, image, and execution-log outputs

Known production proof from the handoff:

| Metric | Value |
|---|---|
| Book | Age Like Fine Wine, Book 1.3 |
| Images | 22/22 generated |
| Time | 57.7 minutes |
| Pages | 61 |
| PDF size | 29.9 MB |
| Estimated cost | About 0.88 USD |

This proof means Fleet should harden and govern the pipeline instead of starting from a blank implementation.

## Operating Principle

Use two layers:

1. **Production engine:** YAML, Markdown, images, HTML, PDF, manifests, and output artifacts.
2. **Fleet governance:** opportunity gate, role ownership, QA certification, launch package readiness, Captain approval, and learning capture.

The production engine may generate assets. Fleet governance decides whether those assets are ready to sell.

## Workflow States

Use these states for dashboard tracking and future automation:

```text
idea
opportunity_qualified
product_brief_ready
source_audit_ready
outline_ready
chapter_draft_ready
editor_review_ready
visual_direction_ready
designed_pdf_ready
qa_ready
captain_approved
launch_package_ready
live
learning_review
```

Each state needs an artifact, not only a status label.

| State | Required artifact |
|---|---|
| `opportunity_qualified` | audience, pain point, transformation, and monetization role |
| `product_brief_ready` | one-page product brief with offer, promise, price tier, and CTA |
| `source_audit_ready` | source list split into verified knowledge, voice/opinion, risky claims, and off-brand topics |
| `outline_ready` | table of contents, chapter goals, exercises, checklists, and CTA placement |
| `chapter_draft_ready` | complete Markdown draft for all chapters |
| `editor_review_ready` | edited draft with tone, clarity, duplication, and claim notes resolved |
| `visual_direction_ready` | cover direction, typography, palette, character usage, image style, and target-reader fit |
| `designed_pdf_ready` | rendered PDF plus debug HTML, image manifest, and pipeline log |
| `qa_ready` | content, brand, visual, PDF technical, and monetization QA reviewed |
| `captain_approved` | explicit Captain approval before public sale or launch |
| `launch_package_ready` | sales page, mockup, checkout copy, delivery email, lead magnet, and content push |
| `live` | sale or distribution is active |
| `learning_review` | performance, buyer response, support questions, and next-product lessons captured |

## Role Ownership

| Role | Responsibility |
|---|---|
| Product PM | Owns audience, promise, product angle, and page fit. For SlayHack this is Slay, not Captain Nayz. |
| Knowledge Reviewer | Audits Drive, notes, prior posts, PM profile, brand docs, and risky claims. |
| Content Architect | Designs table of contents, chapter flow, workbook pages, exercises, checklists, and templates. |
| Writer | Writes the Markdown draft in the page voice. |
| Editor | Tightens clarity, flow, repetition, claims, and conversion logic. |
| Brand Reviewer | Checks tone, vocabulary, persona, target-reader match, and brand boundaries. |
| Visual Designer | Produces cover direction, chapter openers, panels, object portraits, mockups, and layout references. |
| PDF Producer | Runs the pipeline, exports PDF, verifies dimensions, links, font embedding, and file size. |
| Monetization Lead | Owns sales page, checkout, delivery, lead magnet, order bump, upsell, and tracking plan. |
| Captain Gate | Approves the sellable asset and launch package. Live publish and paid launch remain locked until this gate opens. |

## Opportunity Gate

Before production starts, answer these questions:

1. Who is the exact buyer or subscriber segment?
2. What problem is painful enough to justify downloading or buying this?
3. What transformation does the e-book promise?
4. Does the page have enough source knowledge and voice to support the promise?
5. Is this best as a lead magnet, low-ticket product, bundle, membership incentive, or upsell?
6. What claims need extra review before public sale?
7. What would the next offer be after someone reads this?

Gate result:

- `do_not_build_yet`
- `lead_magnet_candidate`
- `paid_product_candidate`
- `bundle_or_membership_asset`

## Pipeline Hardening Requirements

Before the automated pipeline becomes a Fleet-native production tool:

- Remove any hardcoded API key fallback.
- Read `OPENAI_API_KEY` only from the environment or approved secret storage.
- Make content directory, output directory, and config path configurable.
- Keep generated images, manifests, logs, and PDFs inside a project-safe output root.
- Add image compression before PDF embedding.
- Preserve `image_manifest.json` resume support.
- Write `pipeline_log.json` with inputs, outputs, failures, duration, and model choices.
- Keep text out of generated images; title and quote text should stay in the HTML/PDF layer.
- Add PDF bookmarks or an interactive table of contents when possible.

## QA Certification

Use PASS, PARTIAL, or FAIL for each gate.

| Gate | Checks |
|---|---|
| Content QA | promise is clear, chapters are useful, no filler, exercises/checklists add value, risky claims are handled |
| Brand QA | page voice, PM direction, vocabulary, character usage, and audience maturity match |
| Visual QA | cover, chapter openers, panel style, palette, typography, and image consistency match the product |
| PDF Technical QA | dimensions, mobile readability, links, font embedding, image resolution, file size, and metadata |
| Monetization QA | sales page, mockup, checkout copy, delivery email, lead magnet, upsell, and tracking plan |

The e-book is not ready to sell until all five gates are PASS or Captain explicitly accepts a documented PARTIAL risk.

## SlayHack Pilot: Age Like Fine Wine

Registry source: `projects/slay_hack/ebooks.yaml`

| Field | Value |
|---|---|
| Product | Age Like Fine Wine |
| Type | paid low-ticket product candidate |
| Audience | women 35-44 |
| Role | first SlayHack monetization pilot |
| Existing proof | rendered PDF exists from prior pipeline handoff |
| Current Fleet posture | import the handoff, harden the pipeline, certify QA, then prepare launch package |

Required pilot assets:

- product brief
- source audit
- 10-chapter outline
- chapter Markdown source
- visual direction
- rendered PDF
- cover and mockup
- sales page copy
- checkout and delivery copy
- lead magnet
- 7-day content push
- learning and tracking plan

Current local Drive proof is tracked from `projects/slay_hack/project_bridge.yaml` plus `projects/slay_hack/ebooks.yaml`. The dashboard checks the mounted Slay Hack Drive folder for these read-only artifacts before QA:

- `Ebook Project/20260517-Age_Like_Fine_Wine_v1.pdf`
- `Ebook Project/slay_hack_ebook_updated.docx`
- `Ebook Project/ebook_universe_map.png`
- `Ebook Project/20260517-Ebook-Knowledge-Base.md`
- `Ebook Project/20260517-Slay-Ebook-Visual-Strategy.md`

If the Drive root is not mounted on the current host, the dashboard should show the artifacts as registered external proof instead of marking the e-book as locally verified. Production VPS checks can prove the registry and route render; local Mac checks prove the actual file presence.

## Launch Package Gate

Before launch, the package must include:

- sales page headline, promise, sections, objection handling, and CTA
- product mockup and cover image
- checkout name, description, price, and fulfillment instructions
- delivery email
- lead magnet and opt-in copy
- 7-day social content push
- post-purchase next step
- tracking plan for clicks, opt-ins, purchases, refunds, and audience questions

## Safe Boundary

This runbook does not authorize automatic sale, live publish, platform posting, or paid traffic. It authorizes planning, production, QA, and dashboard visibility. Captain approval is required before any public launch or real checkout activation.
