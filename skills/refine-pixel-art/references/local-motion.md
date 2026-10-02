# Local-motion coverage and composition

Read before generating or composing local-motion art. Use local mode only for bounded changes to an accepted native master; full-body articulation follows `full-body-motion.md`. A local failure does not silently authorize switching modes or widening the selection.

Preserve the original accepted master byte-for-byte and keep it as the coverage/reference anchor for every phase. Use its exact integer nearest-neighbor enlargement as the primary generation reference, plus accepted native action keys/neighbors for continuity. Source concepts are supplementary. Record calls, sources, reviews and remaining caps using the chosen standalone or full-run record; this procedure does not itself require a full ledger or bundle.

## 1. Declare complete coverage before generation

Start from `assets/local-motion-plan.template.json`, schema version 2. Define a bounded effective selection with `motion_regions`, `motion_mask`, or their explicitly declared intersection. Rectangles use half-open native coordinates. Shaped masks are native-size opaque binary black/white PNGs; white selects generated candidate pixels. Mask-only selection uses `mask_semantics:"white_selects"`; combined rectangles and mask use `mask_semantics:"intersection"`. Empty and full-canvas effective selections are invalid.

Declare all three footprints, using each field's rectangle list or shaped-mask alternative:
- `original_moving_regions` / `original_moving_mask`: the **whole original moving part**, including tiny outline, attachment and edge pixels
- `motion_envelope_regions` / `motion_envelope_mask`: the complete intended swept area, including extreme poses
- `vacated_regions` / `vacated_mask`: old occupied pixels needing generated erasure or replacement; an explicit empty region list is valid only when none are needed

All three must fit within the effective selection. Enough room around a hand is not enough if an old finger or sleeve outline remains protected outside it. Technical containment tests the declared footprints; it cannot identify the true anatomy or infer an omitted cell.

Choose optional `anchor_regions` only for landmarks whose candidate RGBA must match exactly. Otherwise inspect alignment visually: differing raw candidate pixels outside the selection may be discarded safely, but dimensions alone never prove geometric alignment.

## 2. Inspect and lock the plan

Use a new output directory for each check:

```sh
python3 <skill>/scripts/local_motion_review.py preflight \
  --master masters/master.png --regions animation/regions.json \
  --output reviews/mask-preflight-v1
```

Inspect native and integer-nearest-neighbor previews on white, dark, checker and high-contrast backgrounds, including coverage overlays and pixels just outside every boundary. Verify the whole original moving part, envelope and vacated area; exact protection can preserve unwanted old-pose remnants.

Only after inspection set `coverage_review` to `status:"passed"`, with the exact `master_sha256`, `contract_sha256` emitted by preflight and concrete observations in `notes`. The contract hash binds geometry/masks independently of the review object. Run preflight again on the completed review. Undercoverage or failed/unreviewed coverage blocks generation/composition under this plan; no exit code supplies visual acceptance. Use schema 2 for new work, even though legacy rectangles remain technically supported.

## 3. Review the generated candidate, then compose

Preserve returned originals unchanged in unique attempt paths and normalize measured source geometry to the locked native canvas without independent trimming, stretching or recentering. Use the shared palette/alpha requirements. Before composition inspect stationary landmarks, attachment/contact alignment and the candidate's actual moving/erased footprint against the locked coverage.

For each candidate, save a new contract version with unchanged geometry and an `alignment_review` containing `status:"passed"`, exact `master_sha256`, exact `candidate_sha256` and concrete notes from actual inspection. Do not overwrite the predeclared plan or use its versioning to widen the mask.

```sh
bash <skill>/scripts/assemble_generated_patches.sh \
  --master masters/master.png --candidate candidates/attempt-0004/native.png \
  --regions animation/regions-key-v1.json \
  --output animation/frames/attempt-0004/key.png
```

Assembly copies generated candidate RGBA only inside the effective selection, including transparent pixels needed to erase the old pose. Every outside-master RGBA pixel must remain exact. Preserve the PNG, emitted selection mask and assembly sidecar with source/output hashes. Do not procedurally draw or hand-clean a seam. Repair creative defects through imagegen within the current caps.

## 4. Review actual composites and adjacent motion

```sh
python3 <skill>/scripts/local_motion_review.py compare \
  --master masters/master.png --candidate animation/frames/attempt-0004/key.png \
  --regions animation/regions-key-v1.json --output reviews/master-to-key-v1

python3 <skill>/scripts/local_motion_review.py compare \
  --master masters/master.png --neighbor animation/frames/attempt-0003/neighbor.png \
  --candidate animation/frames/attempt-0004/key.png \
  --regions animation/regions-key-v1.json --output reviews/adjacent-key-v1
```

`--candidate` and `--neighbor` are already composed native frames. Keep `--master` bound to the original accepted master, never rebind it to a neighbor to evade protected-pixel checks. Both composed frames must preserve original outside-selection pixels; neighbor→candidate deltas are additional transition evidence.

Review master→key and relevant adjacent pairs/triples at native size and integer enlargement on white, dark and checker backgrounds; inspect high-contrast diagnostics too. Check:
- The full original moving part and newly vacated area, including erased outlines
- The actual motion envelope, clipping, inside/outside boundaries, seams and attachment pixels
- Stray components or protected old-part remnants, contact/material continuity, duplicated limbs and phase readability

Component, split and delta reports are alerts, not anatomy recognition. Decorative islands may be intentional, and no alert does not prove cleanliness. Diagnostic backgrounds/overlays are review aids only; never use them as generation sources or final frames.

Record a concrete visual coverage/readiness review bound to the original master, contract, candidate/composite and neighbor hashes as applicable. Keep technical preservation and visual/action acceptance separate, with actual user approval or assistant acceptance under quoted delegation. Successful checks do not grant approval of unseen art.

## 5. Handle failure honestly

An original footprint, actual envelope or vacated area outside the effective selection blocks acceptance. So do protected remnants, broken contacts or unreadable required phases. Do not spend futile regeneration calls on an undercovered plan or silently enlarge its mask to make QA pass. Preserve the failed plan, source, composites and reviews; report `needs_revision` and the need for a separately documented replan. Obtain any new user choice or reserved approval before continuing; replanning does not reset generation or repair caps.

Local comparison supplements, not replaces, the intended-speed playback review in `visual-review.md`. Deliver only the evidence actually observed, with unavailable playback or visual checks marked `unverified`.
