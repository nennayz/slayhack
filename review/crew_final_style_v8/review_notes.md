# Crew Final Style v8 Approved Production Notes

Date: 2026-05-16

Scope: final approval notes after Nayz manually updated and approved every crew
portrait for production.

## Production Decision

Nayz manually updated every crew picture and approved the set for production.

System action taken:

- Approved portraits are now live in `static/crew/`.
- Production deploy completed through PR #39.
- This v8 note is no longer an active review gate; it is the historical approval
  record for the production art set.

## Captain Decision Applied

Nayz approved keeping Mia's blue-haired scout direction.

System action taken:

- Mia is no longer a rework target for hair.
- `docs/fleet_character_roster_v2.md` now treats Mia as the short ice-blue
  signal scout.
- `crew_registry.py` now describes Mia as a blue-haired signal scout.

## Approved Production Locks

These characters are locked as the approved production direction unless Nayz
opens a new review pass:

| Character | Status |
|---|---|
| Captain Nayz | approved production portrait |
| Slay | approved production portrait |
| Stadium | approved production portrait |
| Robin | approved production portrait |
| Mia Trend | approved blue signal-scout portrait |
| Zoe Spark | approved production portrait |
| Bella Quill | approved production portrait |
| Lila Lens | approved production portrait |
| Vera Reel | approved production portrait |
| Nora Sharp | approved production portrait |
| Roxy Rise | approved production portrait |
| Emma Heart | approved production portrait |
| Iris Gauge | approved production portrait |
| Sage Ledger | approved production portrait |
| Nami | approved concept-card portrait |
| Genie | approved concept-card portrait |

## Future Review Only

Use the prompt pack below only if Nayz opens a future revision pass.

## Prompt Pack

Use the shared style for every target:

```text
realistic cinematic 3D character render, glossy semi-realistic AAA fashion-game
render, adult high-fashion pirate crew, visible skin pores, realistic hair
strands, leather grain, metal scratches, polished wet ship deck, stormy aurora
or specialist workstation lighting, full-body runway pose, non-cartoon face,
distinct facial structure, distinct silhouette, tasteful sexy fashion editorial,
no nudity, no lingerie, no explicit pose, no same-face glamour, no generic mage
props, role tool clearly visible in hand
```

### Zoe Spark

```text
Zoe Spark, adult Black and East Asian mixed creative cartographer of ideas,
coral-orange micro-braided bob with two glowing ribbon ties, bright expressive
face, playful but sharp creative energy, asymmetrical coral map-room pirate
fashion, layered belts, glowing route-map ribbons wrapping around her hands,
spark pen drawing multiple content routes in the air, idea compass at her hip,
ship map room under aurora light, confident full-body runway stance, coral
accent visible but not overpowering, clearly an idea strategist not a mage
```

Avoid:

- huge generic curly glam hair that hides the cartographer silhouette
- random magic cards without content-route logic
- face/body posing that makes the role secondary

### Roxy Rise

```text
Roxy Rise, adult female trade-winds growth strategist, electric-lime and chrome
distribution commander, clearly not Captain Nayz, distinct upbeat tactical face,
high-energy feminine silhouette, black ship-ready fashion with electric-lime
signal panels, chrome megaphone in one hand, launch cards and hashtag route
signals orbiting like tactical UI, posting-time compass on wrist, platform
distribution map behind her, glossy leather, scratched chrome, confident
full-body runway pose on sunset deck with lime glow, growth strategist not
performer
```

Avoid:

- black-gold Captain authority language
- warm-gold social fantasy that overlaps Zoe or Emma
- unclear prop set; megaphone and launch cards must be readable

### Emma Heart

```text
Emma Heart, adult warm community keeper, rose harbor-host energy, rich mahogany
shoulder-length coils with rose-gold cuffs, practical coral rose-gold community
officer coat, heart-stamped reply cards, glowing reply tablet, harbor lantern,
folded message cards, kind direct eye contact, full-body but approachable
stance, cozy ship communication room, warm light, realistic skin texture,
fashion editorial but operational, clearly drafts audience replies and FAQ
support
```

Avoid:

- romantic fantasy princess framing
- props that look like Bella's writing desk instead of community replies
- hearts becoming childish or cartoon

### Nami Crop/Status

```text
Nami, planned concept-only Life Alignment Keeper for The Freedom, serene
Japanese/Okinawan inspired sea-priestess secretary elegance, seafoam-black low
wave with pearl pins, compass locket, life-domain journal, pearl shawl, brass
hourglass charm, calm private-ship presence, beautiful but future-bound,
dashboard crop must preserve concept-only softness and not imply active private
data access
```

Avoid:

- live workflow UI, dashboards, private data, real personal notes, or anything
  that suggests current Freedom access
- Captain authority symbols

## Future Crop Review Checklist

Before any future `static/crew/` replacement:

1. Create square avatar crops in a separate review folder.
2. Confirm every crop keeps the face, hair silhouette, and signature prop
   readable at dashboard-card size.
3. Confirm Mia still reads as the blue signal scout.
4. Confirm Roxy does not resemble Captain Nayz.
5. Confirm Emma does not collapse into Bella's writer lane.
6. Confirm Nami is visibly concept-only in copy and placement.
7. Run tests and local smoke before any asset copy.

## Production Boundary

The current set is approved and deployed. Future portrait replacements still
require a new review folder, test pass, and explicit approval before deploy.
