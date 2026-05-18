# Age Like Fine Wine - Test Checkout Setup Packet

Status: test_setup_packet_ready
Boundary: Test mode only. No public checkout, live payment link, paid traffic, live publish, or automatic fulfillment is active.

## Product

- Product: Age Like Fine Wine
- Project: SlayHack
- Audience: women 35-44
- Delivery file: `docs/monetization/slay_hack/artifacts/20260518-Age_Like_Fine_Wine_v3_visual_proof.pdf`
- Proof SHA-256: `59a2559db88baea300303778be24fcc43a387842ef476065aa30b2df94e410e8`
- Price: pending Captain price confirmation before Stripe test product creation

## Checkout Surface

Recommended test setup: Stripe test mode using either Payment Links for the simplest no-code smoke or Checkout Sessions if Fleet later needs server-created checkout state.

Do not create a live-mode product, public payment link, or buyer-facing checkout from this packet. The first payment artifact should be test mode only and should use the exact product title, confirmed price, and proof SHA above.

## Secure Delivery Smoke

Internal protected proof route:

`/aurora/ebooks/delivery-proof/age_like_fine_wine?project_slug=slay_hack`

This route is for Fleet-authenticated smoke testing of the approved PDF proof. A buyer-facing delivery link still needs a separate signed-link or delivery-provider setup before public checkout opens.

## Receipt And Email Smoke

Use the approved delivery email draft:

`docs/monetization/slay_hack/age_like_fine_wine_delivery_email.md`

The first email smoke should prove:

1. receipt or delivery email arrives after a test purchase
2. product title is correct
3. support inbox is visible
4. download link opens the correct PDF
5. disclaimer and refund boundaries match the checkout terms

## Support And Refund Smoke

Use the approved checkout terms:

`docs/monetization/slay_hack/age_like_fine_wine_checkout_terms.md`

Smoke these paths in test mode before any public checkout gate:

1. failed-download support request
2. duplicate-purchase refund path
3. access issue that support cannot resolve
4. no general change-of-mind refund unless Nayz separately approves it

## Fleet Recording

Record each result on `/aurora/ebooks` under `Checkout setup and delivery test`.

Required smoke checks:

- Test-mode checkout setup
- Secure delivery link
- Receipt and delivery email
- Mobile PDF open
- Desktop PDF open
- Support path
- Refund path

When all checks pass, Fleet should move only to `test_mode_passed_public_checkout_locked`. Public checkout and live sale still require a separate Captain live checkout gate.
