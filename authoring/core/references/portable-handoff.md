# Portable handoff: one bundle, ordinary request

Use this for full-path stage boundaries, cross-session work and explicitly requested portable delivery. Standalone same-session delivery uses `standalone-records.md` instead. A fresh session must need only the bundle and normal next task. Do not rely on prior chat, private memory, original absolute paths or a parent supplying missing instructions. The bundle preserves task-local approval/delegation evidence; it does not grant authority beyond that evidence and the current request.

## Create from actual evidence

```sh
python3 <skill>/scripts/artifact_bundle.py template handoff-spec.json
# Fill the spec from actual files, reviews and approvals; do not leave placeholders.
python3 <skill>/scripts/artifact_bundle.py create handoff-spec.json handoff-v1
python3 <skill>/scripts/artifact_bundle.py check handoff-v1
```

Raster assets and source entries are PNG-only in this checker. For an imported non-PNG source, preserve the original as supporting evidence and document any decoded-pixel-preserving PNG conversion as derived provenance; do not claim it was the original generator file. Use a new output directory. Source paths in the spec are relative to the spec. The helper copies selected inputs and writes bundle-relative references and an inventory of measured hashes/dimensions. It verifies structure/integrity, not whether a visual judgment is true. Read its output and resolve actual failures before claiming readiness.

The spec records:
- project JSON (which references profile), current stage `identity|views|action|refinement|animation`, status `study|accepted|needs_revision`, technical status `passed|failed|unverified`, visual status `accepted|rejected|unverified`, and concrete next_step
- assets with stable id, file, role `identity|view|action|native_master|pose`, status and separate technical/visual status; source {file,kind:generated|supplied|derived}, review_file and provenance_file. Identity/view/action asset files are target-native studies with originals in source.file; they do not claim a native-master contract. View assets need a view label
- accepted asset approval with matching role, concrete reason, and actor `user|assistant`, exact asset_sha256 and source_sha256, evidence_file; assistant acceptance also needs delegation_file. Record reasons/limitations and timestamp in the evidence itself
- for native_master/pose roles, mandatory set_id and native metadata `grid_px:1`, measured anchor_px, exact lowercase hex shared palette list, grid {source_canvas_px:[w,h],crop:null|[x,y,w,h]}. Pose assets also need pose_id and master_id; source-role mapping belongs in metadata/review. Do not attach the native-master contract to an identity/view/action study. Set members must meet the common native grid/anchor/palette contract
- required_assets as an array of stable asset IDs, naming the members that must be accepted for this particular next step. Do not omit a missing required asset merely to make the checker pass. Optional unrequested views are not requirements
- supports for request, profile decisions, source/normalization provenance, technical QA, visual/set/action-readiness reviews, role/contact contracts, approval/delegation, inferred hidden details, and failed attempts needed to explain limits
- complete open run_directory for continuing a workflow, so original frozen snapshots, run.json, events and evidence move together. The helper validates the ledger and derives used/remaining budget counters

Generate a current template for exact required field names before filling; optional metadata does not replace the declared asset/approval fields. The authoritative readiness fields and asset paths are in the bundle manifest. Original source paths may remain provenance text; they are never required to exist on the receiving machine.

## Readiness by next stage

- Views need accepted identity plus profile/native study and explicit requested angles
- Action design needs accepted identity, relevant views if they exist, and current action/prop intent; missing optional views alone do not block it
- Refinement needs accepted identity/view/action design(s), source-role mapping and requested single/set scope
- Animation needs separately accepted native_master(s), exact hashes, palette/grid/anchor, action readiness, motion mode/constraints, approval scope and remaining counters

Every boundary carries identity/profile plus only the relevant views; retain all accepted required sources. A reference study accepted for identity is still not a native_master. Mark unresolved hidden-detail decisions or action-readiness problems clearly. Do not write `ready` when the required accepted assets are absent, corrupt or outside their approved role.

## Static single-cel handoff

For one requested cel, use `stage: refinement` with accepted `identity`, `native_master` and requested `pose` assets in `required_assets`; the pose names its master and shares the native contract. Preserve the explicit single-cel request and reviews. No timeline or playback claim is needed: this envelope describes static native assets, not a completed animation. `stage: animation` still requires a real timeline and its poses. Pipeline static QA may use a single-entry duration placeholder internally; that is not a user-requested animation or a reason to deliver a fabricated loop.

## Budget and continuation

Keep all starts, including failure/cancellation/pending, with stable attempt ID, stage, semantic pose, repair link and outcome. Budget_state reports attempted_calls, repairs_total, repairs_by_pose, remaining_calls, remaining_repairs_total and remaining_repairs_by_pose. These are computed from run evidence or an explicit self-contained attempts evidence file, then checked against the unchanged project caps. Do not reset counts at stage/session boundaries or rename a repaired semantic pose to escape its limit.

For planned split sessions keep the ledger open. Copy the whole checked handoff into a fresh directory, validate there, inspect the accepted images and continue from its `run/` frozen snapshots and counters. Do not reuse original machine paths, initialize a new allowance, or finalize session 1 as though the overall task ended. Preserve the first bundle as a checkpoint; continue a separate working copy so later writes do not change delivered evidence. Check that copy before continuing. Once its run records or files change, its old bundle inventory is intentionally stale: treat it as the active project, not a newly received immutable handoff. At the next boundary create/check a new bundle from current evidence; never rewrite the old inventory merely to hide changes.

For a compact standalone task expanding into continuation, follow the evidence-only migration in `standalone-records.md`: preserve the entire task directory as a support tree, export all attempts as budget evidence and continue its counters. Do not invent a same_run ledger or initialize a fresh allowance.

For an imported asset without a prior ledger, supply the actual available task-local evidence, state unknown historical generation use, and establish the new task's budget explicitly. Do not invent zero historical calls or a user approval. A budget allowance and acceptance must come from the current task or preserved evidence.

## Fresh-session acceptance check

Copy the completed bundle to an unrelated directory and run check again. Inspect manifest/project/profile, actual native/source images, reviews, authority, required roles, next_step and remaining budget. Verify every needed file is contained and its hash matches. Successful copying proves portability/integrity only; visual readiness remains a separately recorded judgment. If something is missing, return an explicit incomplete handoff rather than asking the next session to reconstruct it from history.


## Preserve linked support directories (v4.1)

For playback or other files with local links, use a complete bounded support tree rather than separately flattened files:

```json
{"directory":"exports/loop-v1","role":"playback","entrypoint":"playback.html","dependencies":["timing.json"]}
```

A support entry uses exactly one of file or directory. Directory contents retain relative structure under support-trees/<directory-basename>; choose distinct source basenames because conflicting destinations reject. The helper preserves bytes, inventories files/empty directories and checks local HTML/CSS/known embedded frame references and explicit dependencies. It rejects escaping paths, symlinks, collisions and absent required targets. Standalone HTML/CSS/JS support files must use directory form; unrelated flat support files stay compatible. Do not scatter a viewer and its PNG sequence into separate hashed filenames.

Entrypoint and dependencies are optional tree-root-relative files; declare JS/runtime-loaded files explicitly because no static parser proves arbitrary dynamic dependencies. External references are counted but never fetched. A relocated directory passing these checks has static reference integrity, not observed or guaranteed browser playback. Independently open/observe actual playback as the animation skill requires. Keep linked trees bounded: at most 10,000 entries, 64 MiB per file and 256 MiB total; parsed linking files at most 8 MiB. Use a separate archive as supporting delivery when a tree exceeds these supported limits, and disclose that its contents were not validated as a live tree.
