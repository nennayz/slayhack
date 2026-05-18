# Fleet Dashboard Design System v2

This layer extends the ship theme into a repeatable dashboard design system for
NayzFreedom Fleet. The goal is clearer operations first, stronger atmosphere
second.

## Principles

- Keep operational status readable before theme language. Words like `ready`,
  `failed`, `blocked`, `approval`, `queued`, `scheduled`, and `live publish locked`
  stay visible anywhere they affect real action.
- Use the Fleet metaphor to identify workflow stations, not to rename the work.
  A Harbor Gate can support approval, but the page still says approval.
- Prefer CSS-native symbols and SVG station art for dashboard chrome. Generate
  raster images only when a screen needs character presence, product packaging,
  social media visual assets, or a scene that cannot be expressed cleanly in UI.
- Put crew portraits in crew/story surfaces. Do not use crew portraits as generic
  dashboard decoration where they compete with status and next actions.

## Station Vocabulary

| Station | System meaning | Primary symbol | Use it on |
|---|---|---|---|
| Command bridge | Fleet-wide attention and next decision | ship wheel | `/`, `/aurora` |
| Route map | planning, slate, next course | compass | Daily Slate, mission planning |
| Shipyard | generation, repair, build steps | gear / tool mark | Generation queue, dry-run controls |
| Harbor gate | approval, publish handoff, locked live gate | gate / lock | Approval queue, manual post handoff |
| Captain log | learning, proof, audit trail | logbook | Learning, metrics, command history |
| Engine room | ops, service health, recovery | engine gauge | `/ops`, production health |
| Crew quarters | roster, identity, review assets | crew portrait | `/aurora/crew` |

## Image Placement Rules

- Captain's Deck: use symbolic instruments near the hero and station icons inside
  action cards. Do not add a large decorative bitmap here unless the action state
  remains readable at mobile width.
- Aurora home: crew preview is appropriate because the route explains the ship
  and its people. Keep the Captain Action Console visually quieter than the hero.
- Daily Slate: add a route-map header visual or compact chart accent. Avoid crew
  portraits unless the task is assigned to a named PM/agent.
- Approval Queue and Manual Posting: use Harbor Gate, lock, checklist, and cargo
  visual cues. Keep `live publish locked` plain and visible.
- Generation: use Shipyard, build queue, tool, and dry-run cues. Do not imply real
  publishing from generation controls.
- Learning and Metrics: use Captain Log and proof markers. Show evidence before
  decoration.
- Crew pages and marketing/product pages: raster image generation can help here,
  especially group shots, character variants, product covers, and scene-based
  banners.

## Current Pilot

The v2 pilot is Captain's Deck:

- A `captain-deck-hero` class turns the command bridge into a two-column control
  surface on desktop and a stacked surface on mobile.
- `captain-command-instruments` introduces three persistent operational symbols:
  Command wheel, Route compass, and Live publish locked.
- Captain Action Console station icons are keyed by `data-station-icon` so tests
  can verify route map, shipyard, harbor gate, and captain log symbols are present.

## Skills and Tooling

- Use repo-native HTML/CSS first for dashboard controls, icons, and state badges.
- Use the `imagegen` skill when a page needs new bitmap assets: crew group images,
  product cover art, social content backgrounds, or rich hero scenes.
- Use browser/visual QA after UI changes to verify desktop and mobile layout.
- Keep `tools/dashboard_visual_qa.py` in the release path for dashboard CSS or
  template changes.

## Verification Contract

Every significant design-system change should include at least one of:

- A template test for the station class, symbol key, or critical safety label.
- A screenshot/visual QA check on desktop and mobile.
- A doc update when a new station, image rule, or asset placement rule is added.
