# Fleet Dashboard Theme v1

This guide keeps the NayzFreedom Fleet dashboard visually consistent as new
routes, ships, and operating lanes are added.

## Theme Goal

The ship theme should make the system easier to read. It is not decoration over
status. A user should still be able to tell what is ready, blocked, approved,
missing, scheduled, or waiting for Captain review without learning new fantasy
language first.

## Page To Station Map

| Route | Station | Theme class |
|---|---|---|
| `/` | Command bridge | `fleet-hero-command` |
| `/aurora` | Aurora command bridge | `fleet-hero-command` |
| `/aurora/crew` | Crew quarters | `fleet-hero-crew` |
| `/aurora/daily-slate` | Route map | `fleet-header-map` |
| `/aurora/approval-queue` | Harbor gate | `fleet-header-harbor` |
| `/aurora/generation` | Shipyard | `fleet-header-shipyard` |
| `/aurora/workflow` | Navigation chart | `fleet-header-chart` |
| `/aurora/learning` | Captain log | `fleet-hero-learning` |
| `/aurora/missions` | Voyage board | `fleet-header-voyage-board` |
| `/aurora/islands/{project}` | Island map | `fleet-hero-island` |
| `/readiness` | Preflight dock | `fleet-hero-readiness` |
| `/ops` | Engine room | `fleet-header-engine` |
| `/metrics` | Captain log | `fleet-header-logbook` |
| `/jobs/{job_id}` | Voyage log | `fleet-hero-log` |
| Approval gates | Harbor gate | `fleet-header-harbor` |

## Asset Rules

- Fleet UI assets live under `static/theme/fleet/`.
- Crew portraits live under `static/crew/` and must not be replaced without a
  separate review folder, crop check, and explicit Captain approval.
- SVG station art is preferred for dashboard chrome because it is lightweight,
  versionable, and easy to verify in tests.
- Route-specific hero art should not include readable text. The template owns
  all labels so the UI stays accessible and localizable.

## Language Rules

- Keep operational words visible: approval, failed, ready, scheduled, queued,
  blocked, missing, live publish locked.
- Use Fleet words to clarify sections:
  - route map for planning views
  - cargo checklist for output readiness
  - harbor gate for approvals
  - shipyard for generation
  - Captain log for learning and audit
  - voyage board for mission lists
- Do not hide live publish risk behind playful wording. Any page near platform
  posting must keep `live publish locked` or equivalent plain language visible.

## Future Expansion

When adding a new dashboard route, choose a station first, then add the smallest
visual treatment that makes the route easier to scan. Add a test assertion for
the station class if the route is operationally important.
