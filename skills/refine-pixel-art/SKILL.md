---
name: refine-pixel-art
description: Refine one accepted pixel-art identity, view, action study or consistent set for its native grid using generated adaptation plus deterministic normalization. Lock native PNG masters with separate technical/visual acceptance and reusable portable handoffs; refinement does not mean hand-pixel cleanup.
---

# Refine Pixel Art

Read `references/runtime.md` before using tools or scripts; installation does not supply the required execution capabilities.

Make reusable accepted native assets from identity, views or action studies. This stage works on a single asset or an explicit set at any point in the workflow; it is not restricted to the step immediately before animation.

## Establish single or set scope

Read `references/project-contract.md`. Check a supplied handoff bundle and inspect all assets to be refined plus their accepted identity/profile and approvals. Rebuild context from files, not conversation. Select requested assets and roles; do not refine an unrequested full set. If an input lacks the relevant design approval, obtain it or route to its design stage. Continue the same frozen run/budget through `references/run-records.md`.

Lock native canvas, view(s), palette roles/limit, alpha, padding, anchor convention, intended downstream use and identity invariants. For sets, record common camera/projection where applicable, head/body scale, grid/normalization geometry, palette mapping, ground anchor and per-view legitimate deviations. Use one common approved palette for final set conversion. Missing views or poses required by the task remain explicit blockers, not placeholders quietly packaged as accepted.

## Adapt, normalize, review

1. Inspect source and target-native studies. If already technically and visually fit, document that regeneration and lossy normalization are unnecessary, retain the exact PNG bytes, and run review/QA on them. Do not quantize an already accepted native source merely to exercise a converter. Otherwise use imagegen for native-grid adaptation and every creative repair, preserving accepted identity and pose. Use accepted native references enlarged exactly by nearest-neighbor when available, and source/concept only as supplementary context. Request deliberate clusters, readable face/hands/props and motion clearance. This is generated-art refinement, never a claim of hand-pixel cleanup.
2. Preserve original returned images and measure their actual dimensions/cell geometry. Normalize via `prepare_pixels.sh --project project.json`; read `references/pixel-tooling.md`. Use a matching-aspect measured canvas/crop, nearest-neighbor sampling, no dither, approved palette and binary alpha. A grid lock must match measured geometry. Do not trim/recenter individual set members or stretch mismatched source aspect ratios. Creative defects go back through imagegen, not code drawing.
3. Review each native PNG at 1× and integer enlargement for silhouette, clusters, face/gaze, anatomy, costume/material roles, prop contacts and padding. Measure bounds/margins and root/ground anchors; different views can have different silhouette widths. Technical normalization cannot establish pixel craft, identity or action readability.
4. For sets, compare all native members together: shared size/grid, palette and role assignments, proportions/apparent scale, anchor convention, accessory side and identity. Revalidate the entire selected set if a common palette/grid rule changes. Do not present independent good-looking assets as a consistent set without this review.
5. For intended animation, verify action readiness at native scale with `references/action-continuity.md`: contact points, moving-material separation, enough trajectory clearance and stable root. For local motion, inspect the entire original moving part and its attachment/outline at native size on white, dark and checker backgrounds. Record source footprint, expected motion envelope and vacated area before locking the mask; require the later generated key/adjacent composite review to reveal no protected old-part remnants. Record motion mode: local changes use predeclared regions/shaped mask; full-body motion uses identity/root/contact/scale criteria without freezing all body pixels. An accepted neutral view may require action design before a particular animation.
6. Run native QA under the shared project contract. A one-frame or refinement set is a static scope: it must honor native/format/set requirements, not pretend to satisfy future animation duration or drawing-count constraints. Keep complete technical and visual reports. Inspect unsuccessful checks rather than hiding them.
7. Accept each native master and the set (if relevant) separately with current user approval or clearly quoted creative delegation. Record exact hash, actual dimensions, source/normalization provenance, palette/anchor and unresolved limitations. No approval follows automatically from a helper exit code. Preserve accepted native PNGs unchanged.

## Portable delivery

Deliver selected native PNG(s), unchanged generated/source rasters, integer previews, technical QA, visual/set/action-readiness review, approvals and remaining counters. Roles distinguish identity/view/action studies from `native_master` assets; multiple native masters retain an explicit source-role/view/pose mapping. Follow `references/portable-handoff.md` and validate a copied bundle. The next step may be more views, action design, animation or simple delivery; do not force animation.

Animation receives the actual accepted native master(s), exact hashes, normalization geometry, approved palette, anchor/contact/scale limits and current approval scope. It must use an exact integer enlargement of the native master as its primary imagegen reference, not substitute an earlier high-resolution concept. A later creative master change returns here for new acceptance.
