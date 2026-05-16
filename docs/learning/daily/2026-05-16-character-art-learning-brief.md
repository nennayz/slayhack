# Daily Learning Brief - 2026-05-16 Character Art Review

## Captain Intent

- Main goal: continue character art review and daily learning loop.
- Active ship/page/project: NayzFreedom Fleet, with Aurora crew and page-owner
  characters under review.
- Today's mode: review / learn.
- Do not touch: `static/crew/` assets and production deploys until Nayz approves.

## What Nayz Asked For

- Read `CLAUDE.md` before continuing repo work.
- Use `docs/learning_loop_v1.md` and `review/crew_final_style_v7/` as context.
- Continue the character art review.
- Preserve the preferred character style: realistic cinematic 3D, glossy
  semi-realistic AAA fashion-game render, visible skin pores, realistic hair,
  leather grain, metal scratches, sexy fashion editorial, non-cartoon, and
  distinct faces/silhouettes.

## What Nayz Liked

- The direction should move away from cartoon/anime simplicity and toward
  glossy cinematic 3D fashion-game character renders.
- Character identity should be visible through face, silhouette, prop, outfit,
  material detail, and role signal.
- Review assets should stay separate from live dashboard assets until approved.

## What Nayz Disliked Or Corrected

- Do not overwrite `static/crew/` without explicit approval.
- Do not deploy creative changes during a review-only art pass.
- Do not merge Captain Nayz and PM Slay; these are separate identities.

## Decisions Made

| Decision | Why it matters | Durable? |
|---|---|---|
| Treat `review/crew_final_style_v7/` as the current review anchor, not live art | Keeps taste review separate from production state | yes |
| Keep v7's cinematic AAA fashion-game direction as the preferred art lane | Prevents drift back to generic portraits or cartoon styling | yes |
| Require a character-specific correction pass before live promotion | Avoids locking role confusion into the dashboard | revisit after approval |

## System Lessons

- The learning loop needs a written art verdict before any image-copy step.
- Review folders should contain their own notes so future sessions know why an
  image was approved, held, or rejected.
- Dirty worktree state must be respected; existing `static/crew/` changes may
  be user/current-session work and should not be reverted.

## Creative Lessons

- v7 is strong because it combines full-body runway framing, ship-deck
  atmosphere, glossy materials, and role-specific props.
- The highest-confidence locks are Captain Nayz, Slay, Robin, Bella, Lila,
  Vera, Nora, Iris, Sage, and Genie.
- Mia's blue scout direction is accepted and should be written into the roster
  bible. Zoe, Roxy, Emma, and Nami still need targeted review before promotion
  because they either need sharper role signals or risk status ambiguity.

## Operational Lessons

- `docs/learning/daily/` did not exist yet, so the daily learning artifact path
  had to be created before writing this brief.
- `docs/templates/daily_learning_brief.md` is the right structure for this kind
  of work block.
- Do not use a deploy or asset-copy flow during art review unless Nayz switches
  the task from review to approval/implementation.

## Beginner Guidance For Nayz

Recommended next action: approve the review-note categories first: locks,
targeted reworks, and concept-only holds.

Reason: this prevents spending time regenerating the full roster when only a
small subset needs correction.

Risk if skipped: a beautiful set can still become confusing if the wrong role,
hair identity, or authority level gets promoted.

Smallest safe step: revise the remaining v8 targets only: Zoe, Roxy, Emma, and
Nami status/crop handling. Mia no longer needs a regenerate pass for hair.

## What Sage Should Store

- v7 is the current best style anchor for realistic cinematic AAA fashion-game
  Fleet character art.
- Review assets stay in `review/` until Nayz approves live promotion.
- Future portrait prompts should preserve skin texture, realistic hair, leather
  grain, metal scratches, strong full-body silhouettes, and role props.

## What Iris Should Check Later

- After these characters appear in public-facing content, compare engagement
  between character-forward posts and non-character posts.
- If dashboard users hesitate or misread roles, treat that as identity feedback,
  not just UI copy feedback.

## What Should Stay Private Or Unstored

- Any personal/private meaning behind characters should stay out of repo docs
  unless Nayz explicitly makes it project-safe.
- Nami and Lyra-related private workflows should remain concept-only until data
  and privacy boundaries are built.

## Tomorrow's Suggested Route

1. Nayz reviews `review/crew_final_style_v7/review_notes.md`.
2. Regenerate or revise only the targeted characters.
3. After approval, create dashboard-safe crops in a separate review folder
   before touching `static/crew/`.
