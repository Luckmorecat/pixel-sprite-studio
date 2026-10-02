---
name: character-identity
description: Create a recognizable pixel-art-first character identity in a neutral pose, study it at the intended native size, and preserve fixed proportions, outfit and palette roles. Use for a new character or explicit identity redesign before optional multi-view-reference, action-pose-design, refinement or animation.
---

# Character Identity

Read `references/runtime.md` before using tools or scripts; installation does not supply the required execution capabilities.

Establish who the character is before choosing an action. Design pixel art from the first generated source; do not begin with a detailed illustration and call its downsample a finished sprite. Produce an accepted identity plus target-native study, not a silently approved final master.

## Begin from the contract

Read `references/project-contract.md`. For existing work, check the supplied portable bundle with `scripts/artifact_bundle.py check` and inspect its assets before using them. Ask only for missing blocking choices. Record native canvas, expected use, view, visual style, identity requirements, palette/alpha/padding, total call and repair caps, and approval authority in project/profile files. Use `references/run-records.md` before the first generation in a full flow or trial; freeze all participating skills and retain one ledger/budget across stages and sessions.

Use imagegen for all raster creation and creative repairs. Follow its tool instructions and inspect local edit inputs. Code may normalize, select generated pixels through declared masks, package and measure; never draw substitute artwork. Any sexualized design must be explicitly adult with adult visual portrayal; do not add sexualization to a nonsexual brief.

## Design for native readability

1. Plan one neutral, unobstructed identity pose: relaxed hands separated from silhouette where possible, readable face, clear costume construction. A neutral full-body or suitably framed identity must not be defined by a later prop/action pose. Use user references when supplied; avoid adding unrequested equipment or gestures.
2. If exploration is requested, make the requested number of genuinely distinct identity candidates. Otherwise default to one focused candidate plus a bounded repair allowance; do not spend animation budget on unnecessary alternatives. Freeze stage allocations within the single project cap before generation. Count every attempt, including failed calls.
3. Write a pixel-art-first prompt with the intended native size, cluster economy, deliberate hard edges, clear silhouette, minimal shading and readable material/color separation. Specify proportions (head/body relation, limb lengths, ears/tail and distinctive marks), outfit components and palette roles. These become invariants after selection. Avoid high-resolution painterly detail that cannot survive the native grid.
4. Record exact prompt, parameters, reference roles/hashes and start event before imagegen; preserve every original returned source unchanged. Measure actual returned dimensions. Model output size/cell geometry is not guaranteed by prompt or reference size.
5. Run `prepare_pixels.sh --project project.json` for a deterministic target-native study using inspected matching-aspect geometry. Read `references/pixel-tooling.md` for options. Inspect both 1× and integer enlargement. Grade silhouette, face/expression, limbs and costume separation at the target, not merely at generation size. A helper pass establishes format only. Record downsampling damage and unmet criteria.
6. Select and record the identity only if recognizable and coherent at native scale. Obtain user approval when a checkpoint is reserved; an end-to-end request delegating creative decisions permits assistant acceptance for that task. Record the actual actor, quoted evidence and exact accepted artifact hash. Never claim the user approved unseen pixels. A beautiful large source with a weak native study remains `needs_revision`.

## Deliver and route

Deliver preserved source, native study/enlargement, identity/profile, technical and visual reviews, exact approval/delegation, call/repair counters and a self-contained handoff bundle. Mark each artifact `study`, `accepted` or `needs_revision`; an accepted identity study is not automatically an accepted `native_master`. Include dimensions, source/hash, role, approval scope, limitations and next step. Follow `references/portable-handoff.md`; validate the copied bundle independently.

Use `multi-view-reference` only for requested/helpful angles, `action-pose-design` for the desired action/composition, or `refine-pixel-art` directly to lock the neutral identity as a native master. Do not force optional views or action design when the task does not need them. Standalone identity work ends here with honest readiness. Locate downstream skills by their catalog/frontmatter names, never assumed sibling folders.
