---
name: multi-view-reference
description: Derive a consistent requested set of pixel-art views from an accepted character identity, preserving proportions, outfit construction and palette roles. Use for front/side/back/three-quarter references and unseen-detail decisions before posing, reusable refinement or animation; do not independently redesign each angle.
---

# Multi-view Reference

Read `references/runtime.md` before using tools or scripts; installation does not supply the required execution capabilities.

Turn one accepted identity into the requested angles. Views are reference evidence, not a second design competition. A turn exposes hidden construction; separate inferred details from facts present in the identity.

## Establish the common identity

Read `references/project-contract.md`. If a bundle is supplied, run `artifact_bundle.py check`, read its project/profile/budget/readiness and inspect the actual accepted identity plus native study. Rebuild context from these files; do not depend on earlier conversation. Obtain identity acceptance or route to `character-identity` if missing. Continue the same ledger/frozen version and remaining project budget through `references/run-records.md`.

Record exactly which angles are requested, view convention (character-left/right versus viewer-left/right), common native canvas, head/body scale, ground/root anchor, proportions, outfit construction, palette roles and silhouette features. Reuse an accepted identity angle when appropriate instead of regenerating it. Do not invent a full turnaround if only one additional view is needed.

## Derive, compare, accept

1. Generate each missing view separately using imagegen. Use the accepted identity as the primary reference and relevant accepted neighboring view as a supplementary geometry reference. For native accepted sources use exact integer nearest-neighbor enlargements; retain original and enlarged reference hashes. Inspect references before editing. State reference roles explicitly; never rely only on the previous generated view, which can drift away from identity.
2. Prompt pixel-art-first at the native target with the same proportions, outfit, material/color assignment and projection. Change only the requested camera/view relationship. Do not mirror asymmetric details blindly or accidentally reverse handedness. Name visible and hidden features and any interpretation needed for the new view.
3. Preserve returned originals and actual dimensions. Create target-native studies with `prepare_pixels.sh --project project.json` after measuring geometry; do not per-view auto-trim/recenter or distort to force matching height. A grid lock requires actual source geometry to match, not merely the same requested size. Read `references/pixel-tooling.md`.
4. Inspect each view at 1× and enlargement beside the identity and earlier views. Check face/species, head/body ratio, limb/ear/tail lengths, accessory side, garment seams/layers, silhouette, palette roles, root/ground placement and consistent apparent scale. View-dependent silhouette width is legitimate; identical bounding boxes are not an identity requirement.
5. Record invented hidden details explicitly: what was unseen, chosen construction, why it is consistent, and whether acceptance is still needed. Do not report these as recovered facts. For a conflict, use a targeted imagegen repair with identity and relevant accepted views; never hand-paint corrections or redefine identity to excuse drift. Retain failed candidates and counters.
6. Accept each angle and the set separately under the current approval scope. A set with missing requested angles or an unresolved identity contradiction remains `needs_revision`/incomplete. Technical canvas/palette checks cannot certify cross-view identity.

## Portable output

Write one asset per view with role `view`, angle/side convention, exact source/native paths and hashes, target dimensions, anchor/palette metadata, status, visual/technical review and approval evidence. Include the unchanged identity, profile, inferred-detail decisions, requested/completed angles, set-consistency review and remaining generation/repair budget. Follow `references/portable-handoff.md`, create/check the self-contained bundle, then inspect it after copying to a different directory.

Route to `action-pose-design` for an action, or to `refine-pixel-art` for native refinement of one view or the entire view set. A consistent view study may be accepted for reference without claiming finished native masters. Never add optional views after budget exhaustion or require missing unrequested views as a blocker.
