# Daily Learning Brief: Crew Deck v2

Date: 2026-05-17

## What Nayz Asked For

Nayz approved continuing after the Captain and Stadium portrait update, then
asked to analyze and run the next UX/UI improvement. The next logical task was
to make the crew deck easier to understand now that the crew roster includes
Fleet Captain, page PMs, production crew, and learning specialists.

## What Changed

- The crew deck should not treat every visible character as one flat route.
- Captain Nayz is Fleet Command, not a page PM and not a production worker.
- Slay and Stadium are page PMs with separate island ownership.
- Robin through Emma are the main Aurora production route.
- Iris and Sage belong to the learning loop after publish.
- Old unused asset references should be guarded by visual QA after cleanup.

## Reusable Rule

When a dashboard page mixes strategic owners, PMs, workflow crew, and learning
roles, group them by responsibility before adding more cards. A complete roster
is useful only if the user can quickly see who decides, who manages a page, who
does production, and who captures lessons.

## What To Repeat

- Keep Captain Nayz visually and operationally distinct from Slay and Stadium.
- Keep every visible crew card tied to a production portrait in `static/crew/`.
- Add dashboard visual QA markers when UX hierarchy becomes important.
- Remove unused legacy image references only after checking there are no live
  references.

## What To Avoid

- Do not flatten all roles into one "crew" list when the roles have different
  authority levels.
- Do not imply concept or future ship roles have live workflow access unless the
  underlying workflow exists.
- Do not overwrite portrait files as part of UX cleanup.

## Next Action

After Crew Deck v2, continue with mobile polish on Daily Slate and Approval
Queue so SlayHack and Stadium Sweethearts actions stay clearly separated.
