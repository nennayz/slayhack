# Crew Final Style v8 Review Plan

Date: 2026-05-16

Scope: targeted continuation after the v7 review. This is still review-only and
does not approve overwriting `static/crew/` or deploying.

## Captain Decision Applied

Nayz approved keeping Mia's blue-haired scout direction.

System action taken:

- Mia is no longer a rework target for hair.
- `docs/fleet_character_roster_v2.md` now treats Mia as the short ice-blue
  signal scout.
- `crew_registry.py` now describes Mia as a blue-haired signal scout.

## Current Locks

These characters are locked as the current v7/v8 direction unless Nayz changes
the taste decision:

| Character | Status |
|---|---|
| Captain Nayz | lock direction |
| Slay | lock direction |
| Robin | lock direction |
| Mia Trend | lock blue signal-scout direction |
| Bella Quill | lock direction |
| Lila Lens | lock direction |
| Vera Reel | lock direction |
| Nora Sharp | lock direction |
| Iris Gauge | lock direction |
| Sage Ledger | lock direction |
| Genie | lock direction |

## Remaining Targeted Work

| Character | Target | Why |
|---|---|---|
| Zoe Spark | sharper idea-cartographer identity | current image is attractive, but the route/map logic can read more clearly |
| Roxy Rise | electric-lime growth strategist | current image is improved, but needs clearer launch/distribution tools and less warm-gold overlap |
| Emma Heart | practical community keeper | current image is warm, but needs stronger reply/tablet/lantern signal and less romantic fantasy |
| Nami | concept-only crop/status handling | image can stay beautiful, but the dashboard must not imply live Freedom data access |

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

## Crop Review Checklist

Before any `static/crew/` promotion:

1. Create square avatar crops in a separate review folder.
2. Confirm every crop keeps the face, hair silhouette, and signature prop
   readable at dashboard-card size.
3. Confirm Mia still reads as the blue signal scout.
4. Confirm Roxy does not resemble Captain Nayz.
5. Confirm Emma does not collapse into Bella's writer lane.
6. Confirm Nami is visibly concept-only in copy and placement.
7. Run tests and local smoke before any asset copy.

## Gate

No deploy and no live-asset overwrite until Nayz approves the v8 targeted output.
