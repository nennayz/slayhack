# SP-6 — Social Packaging / Auto-post Plan

Date: 2026-05-20
Status: Implemented in branch `sp6-social-packaging-v1`

## Goal

Connect the SP-0 → SP-5 lifecycle to a safe social packaging lane:

Trend/Idea → Production Loop → Social Packaging → locked local publish queue.

SP-6 does not silently live-post. It creates durable Knowledge Store artifacts and a local dashboard/manual handoff queue while preserving the existing live publish gate (`NAYZ_AUTO_POSTING_DISABLED` / `publish_control.ensure_auto_posting_enabled`).

## Task boundaries

1. Audit current publish surface
   - Reuse `ContentJob.publish_package`, `publish_execution`, and `publish_result` fields.
   - Reuse Knowledge Store `ContentObject` with open `kind`, adding `publish_package` objects without a schema migration.
   - Keep external platform API calls inside `PublishAgent`; SP-6 queue creation must not call platform APIs.

2. Build social packaging worker
   - Scan completed production jobs under `output/<page>/<job>/job.json`.
   - Package jobs that have a `GrowthStrategy` caption/hashtags and a ready production stage.
   - Write a `caption` ContentObject and a `publish_package` ContentObject to the KS.
   - Update the source job to `stage=publish_queued`, `status=awaiting_approval`.
   - Append a local `output/publish_queue.jsonl` entry for operator/dashboard handoff.
   - Mark source idea `done` best-effort when `idea_uid` exists.

3. Make it scheduler-driven
   - Run social packaging after the daily production loop when scout/pipeline automation is enabled.
   - Support `dry_run=True` without writes.
   - Keep failures non-fatal per job/page so the scheduler continues.

4. Verification gates
   - Unit tests for package creation, idempotency, and dry-run behavior.
   - Scheduler test proving SP-6 runs after production loop.
   - Targeted publish/dashboard regression tests.
   - Full repo test suite and ruff lint before PR.

## Safety rules

- SP-6 queue creation is local-only and sets every platform result as `dry_run=True`.
- No social platform API method is called by `social_packaging.py`.
- Live auto-post remains a separate explicit action through `PublishAgent`, guarded by the existing publish control gate.
- Re-running SP-6 is idempotent for jobs already marked with `source=social_packaging_v1`.
