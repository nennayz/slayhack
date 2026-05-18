# Age Like Fine Wine - Source Repair Packet

Status: review_ready
Boundary: Source repair and revision plan only. This does not approve checkout, public sale, live publish, paid traffic, or automatic fulfillment.

## Current Proof

- PDF proof: `Google Drive / Slay Hack / Ebook Project / 20260517-Age_Like_Fine_Wine_v1.pdf`
- PDF SHA-256: `92b6baa2e0bc7cc53ed3d33d9aabe4e33f5d70680dd9b4e96391c5807e236e63`
- Observed proof: 39 pages, 6 x 8 inches, about 9.5 MB, text extractable, bookmarked
- Registered editable DOCX: `Google Drive / Slay Hack / Ebook Project / slay_hack_ebook_updated.docx`
- Source blocker: the registered DOCX opens as a different `40 Life Hacks` product, not Age Like Fine Wine.

## Source Of Truth Decision

Until a matching editable source is produced, the rendered PDF proof is the only confirmed Age Like Fine Wine source. The next source file should be regenerated or rebuilt from the PDF proof and saved with an explicit product filename, for example:

`20260517-Age_Like_Fine_Wine_v1_source.docx`

Do not overwrite or relabel the existing `slay_hack_ebook_updated.docx` unless the content is actually replaced with the Age Like Fine Wine manuscript.

## Required Source Fix

1. Create a matching editable source for the current Age Like Fine Wine PDF.
2. Add PDF metadata before export:
   - title: `Age Like Fine Wine`
   - author: `SlayHack`
   - subject: `Beauty and confidence guide for women 35-44`
3. Replace the final live-looking shop CTA with a locked CTA until checkout is approved.
4. Re-export the PDF and record the new file name, page count, file size, and SHA-256.
5. Keep the old proof as historical proof instead of treating it as the final sale file.

## Claims And Disclaimer Patch

Add this near the front of the guide before skincare guidance:

This guide is for general beauty education and personal routine planning. It is not medical advice, dermatology advice, or a substitute for care from a qualified professional. Skin needs vary by person. Patch test new products, follow product labels, use SPF as directed, and talk with a licensed professional if you have a medical skin concern, active irritation, prescription skincare, pregnancy-related restrictions, or uncertainty about ingredients such as retinoids or collagen supplements.

Add this short note anywhere collagen supplements, retinol, SPF, hyperpigmentation, or skin cancer risk are mentioned:

Check product labels and professional guidance before making skincare or supplement changes. Results vary by person.

## Visual Revision Patch

The current proof has a strong cover but the interior reads too text-heavy for the B+C Hybrid visual strategy. The regenerated version should add visual structure before Visual QA can pass:

- Character portrait or mini-panel at each chapter opener.
- One icon-led checklist per major routine.
- One side-by-side before-routine / after-routine planning panel per technical chapter.
- Consistent character tip card treatment for Auntie V, Bella Mist, Sera, Sunny, Wanda, and Conceal.
- Remove the near-blank page before the final CTA by moving the tip block into the prior section or making it a full visual recap page.

## CTA Patch

Until checkout is approved, replace the final shop CTA with:

Age Like Fine Wine is in final QA review. Public checkout opens only after Captain approval.

Once checkout is approved, the CTA can become:

Start your Fine Wine glow-up at slayhack.com/shop

## Approval Rule

Content QA can move to PASS only after the matching editable source exists and the claims/disclaimer patch is applied. PDF Technical QA can move to PASS only after the revised PDF has metadata, an intentional CTA/link decision, and updated proof metadata. Visual QA can move to PASS only after a redesigned proof satisfies the visual-first requirements above.
