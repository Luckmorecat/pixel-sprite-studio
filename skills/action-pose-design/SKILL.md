---
name: action-pose-design
description: Stage an accepted pixel-art character for a requested action, pose, prop interaction or composition while preserving identity and using relevant supplied views. Use between character-identity (optionally multi-view-reference) and reusable refine-pixel-art; do not redesign the character or confuse an action study with an animation-ready native master.
---

# Action Pose Design

Read `references/runtime.md` before using tools or scripts; installation does not supply the required execution capabilities.

Preserve who the character is; choose how the character performs the requested action. This replaces the former broad design stage. Route a new identity or explicit redesign to `character-identity` instead of silently rebuilding identity here.

## Establish inputs and action

Read `references/project-contract.md`. Check the portable bundle when supplied, inspect accepted identity/native study and only the relevant accepted views. Views are optional; when absent, derive the needed pose from identity and disclose any newly invented hidden construction. Ask only if a missing choice blocks the action. Continue exact profile, approval authority, fixed native target and remaining ledger/budget through `references/run-records.md`.

Name the requested visible action, intended view/composition, gesture/emotion, contact/support roles, props and minimum semantic phases. Read `references/action-continuity.md` for linked limb/prop actions. Choose an action-ready rest/key pose; do not equate a pleasing still with a readable animation. Identity locks include proportions, face/species, outfit construction, distinctive markings and palette roles; legitimate pose deformation does not permit changing these.

## Make action-ready pixel art

1. Plan camera, ground/root anchor, scale, prop placement and native motion clearance. For planned local animation, identify the full original moving-part footprint (including tiny outline/attachment pixels), intended swept envelope and pixels that must be vacated. Leave clearance for all three; an old outline protected outside the mask can become a detached remnant. Define which anatomical limb performs each role using character-left/right and viewer-left/right explicitly; record support/occlusion/contact states so later phases do not duplicate a resting limb or switch hands accidentally. Distinguish required action from optional embellishments.
2. Generate the action study with imagegen, primary accepted identity reference plus relevant views. If there is an accepted native identity/master, use its exact nearest-neighbor enlargement as the primary pixel reference; large concept imagery is supplementary. Inspect all references first. Keep pixel-first clusters and a pose readable at the target size. Preserve identity rather than borrowing proportions from a concept or enlarging facial detail unrealistically.
3. Record exact prompt/parameters/reference hashes before the call; preserve returned source and measured dimensions. Normalize a native study with `prepare_pixels.sh --project project.json` after actual geometry inspection. Do not assert the generator returned a target-native image simply because that size was requested.
4. Review at 1× and enlargement. Check identity, face/eyes, gesture, limb count, silhouette, contact chain, prop/material separation and room for the intended phases. If the action will animate, state the hardest phase and how it remains visible. Do not count blink/bob motion as completion of a distinct requested action.
5. Use only preallocated targeted repair attempts. Repair the observed defect through imagegen with the accepted identity/views and current action source as appropriate. No manual painted fixes, procedural replacement art, secret prompt rescue or unlimited tries. Report `needs_revision` when readiness fails.
6. Accept the action design under the current user/delegated scope, recording exact hashes and concrete reasons. Keep status separate from technical checks. This acceptance approves action/composition, not automatically the final native pixels or a finished animation.

## Handoff

Deliver identity plus relevant views, action source/native study/enlargement, role/contact contract, profile and action-readiness review. Include preserved failed attempts, source geometry, exact approvals, unresolved invented details and remaining counters. Build/check the portable bundle described in `references/portable-handoff.md` so a fresh session can continue from artifacts and an ordinary request alone.

Use `refine-pixel-art` on the selected action study, or on an explicitly requested action set, before animation. Its output must separately accept native pixels. Do not send an unaccepted concept directly to animation as a locked master.
