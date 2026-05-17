# Crew Static Production Asset Audit

Date: 2026-05-17

Scope: current production portraits under `static/crew/`. This audit records
the existing live/dashboard asset state. It does not overwrite, regenerate, or
move any portrait files.

## Verdict

The current `static/crew/` portrait set is the production canon for dashboard
crew cards. It is not a straight promotion of `review/crew_final_style_v7/`.
Only `iris-gauge.png` and `sage-ledger.png` match the v7 review files by SHA256.
The rest of the production portraits are separate manual/static assets.

Recommended path: keep `static/crew/` as production canon, keep v7 as historical
review evidence, and require a new versioned review folder before any future
portrait replacement.

Risk if skipped: future sessions may treat v7 review notes as permission to
copy assets over `static/crew/`, or may treat current production portraits as
unreviewed because older notes still say "do not promote."

## Production Asset Inventory

| File | Dimensions | Production status | Audit note |
|---|---:|---|---|
| `static/crew/captain-nayz.png` | 941 x 1672 | approved production | Captain authority asset; keep distinct from PM Slay. |
| `static/crew/slay.png` | 1023 x 1537 | approved production | SlayHack PM asset; not Captain Nayz. |
| `static/crew/stadium.png` | 887 x 1774 | approved production | Stadium Sweethearts PM asset. |
| `static/crew/robin.png` | 1002 x 1569 | approved production | Chief Officer / route command asset. |
| `static/crew/mia.png` | 971 x 1620 | approved production | Blue signal-scout direction is intentional. |
| `static/crew/zoe.png` | 978 x 1608 | approved production | Idea cartographer asset; monitor crop readability. |
| `static/crew/bella.png` | 982 x 1602 | approved production | Scribe asset. |
| `static/crew/lila.png` | 1023 x 1537 | approved production | Visual Director asset. |
| `static/crew/vera-reel.png` | 1023 x 1537 | approved production | Video Producer asset. |
| `static/crew/nora.png` | 997 x 1577 | approved production | QA Inspector asset. |
| `static/crew/roxy.png` | 864 x 1821 | approved production | Growth Strategist asset; keep electric-lime distribution cues distinct from Captain styling. |
| `static/crew/emma.png` | 864 x 1821 | approved production | Community Keeper asset; keep reply/community props visible in crops. |
| `static/crew/iris-gauge.png` | 1024 x 1536 | approved production | Matches v7 by SHA256. |
| `static/crew/sage-ledger.png` | 1003 x 1568 | approved production | Matches v7 by SHA256. |
| `static/crew/nami.png` | 1023 x 1537 | approved concept portrait | Future Freedom card only; no private workflow access implied. |
| `static/crew/genie.png` | 864 x 1821 | approved concept portrait | Future Lyra card only; no music workflow access implied. |

## Gates For Future Replacement

Before replacing any file under `static/crew/`:

1. Create a new versioned review folder under `review/`.
2. Add review notes with lock/rework/concept-only status.
3. Compare the proposed portrait against this production audit.
4. Check dashboard crops separately from full-body images.
5. Get explicit Captain Nayz approval for the specific file replacement.
6. Deploy only after tests and production smoke pass.

## Boundaries

- `review/crew_final_style_v7/` remains historical review evidence and style
  anchor material.
- `static/crew/` is the current dashboard production source.
- Concept-only portraits can be visible in planning cards, but they must not
  imply live access to private Freedom or Lyra workflows.
