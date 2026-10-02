# Pixel tooling: exact inputs, outputs and limits

## Prerequisites and preserved artwork

Check Bash, Python 3 and ImageMagick 7 (`magick`) before work. The core packaging helper also supports legacy `convert`; normalization/assembly require `magick`. No automatic software install or paid model fallback. These tools perform deterministic normalization, generated-pixel mask compositing, export and verification; they do not draw poses or repair faces. Imagegen is the artwork source. Preserve original sources and approved assets unchanged; all output paths must be fresh.

## Normalize a generated raster

```sh
bash <this-skill>/scripts/prepare_pixels.sh --input sources/attempt-0001/original.png \
  --output candidates/attempt-0001/native.png --project project.json \
  --run run-001 --attempt-id attempt-0001
```

For new generated sources pair `--run RUN --attempt-id ATTEMPT` after generation-end. This verifies source content against its immutable captured output and enforces attempt-scoped source/candidate names. Existing outputs still cannot be overwritten. Imported sources without a generation attempt omit both flags and retain explicit provenance. Prefer `--project project.json`: native dimensions and color limit inherit the shared config; explicit `--width`, `--height` or `--colors` must agree. Actual returned raster geometry is still measured. Inputs: one still image; exact native width/height (1–4096); color limit (2–256); fresh PNG path. Optional `--crop WxH+X+Y` uses measured nonnegative source coordinates; optional `--palette master/master.png` maps generated colors to the approved palette. For later poses, `--grid-lock master/master.provenance.json` requires the same source/native dimensions and measured crop as the master conversion and records its hash; it does not prove geometric alignment. Outputs: native PNG, `*-6x.png`, `*.provenance.json` with source/output hashes, real dimensions, crop, palette and alpha settings. The source/crop aspect must match the target; no distortion. No opaque background removal: use imagegen for that creative edit.

This uses nearest-neighbor, no dithering and binary-alpha thresholding. Use only when this matches the contract; do not silently threshold a requested partially transparent/antialiased asset. Normalization can damage small faces or select wrong material colors. Inspect at 1× and enlargement and run QA; requested color limit is not proof of measured union. For animation use the same measured crop/scale/grid and approved palette, never independently trim or recenter each pose.

## Core package from native PNGs

Every core package bundles matching helpers and shared configuration; no runtime dependency on a guessed sibling path. Run only the relevant tools for the current stage.

```sh
python3 <this-skill>/scripts/pixel_pipeline.py qa animation-input.json --project project.json --output qa-before.json
python3 <this-skill>/scripts/pixel_pipeline.py pack animation-input.json exports/loop-v1 --project project.json --scale 6 --columns 4
```

Inputs: a direct JSON manifest described in `project-contract.md`, positive native width/height, existing master PNG, nonempty frames (`file`, integer `duration_ms`), and tag. Paths resolve relative to the manifest. A manifest may include `project` relative to itself or the command can use `--project`; both must agree. The shared loader fills omitted native/limit/count requirements and rejects contradictions. Static refinement manifests set `scope:"static"`; this applies native/format requirements without future animation duration/counts and rejects animation-only fields. Final loop scope is `animation`. Optional `palette_max`, `min_margin`, `motion_regions`, `motion_mask`, `animation_mode`, and `constraints` enforce agreed limits. `constraints` accepts exact `timeline_frame_count`, exact `distinct_drawing_count`, minimum `min_distinct_drawing_count`, exact `total_duration_ms`, maximum `max_timeline_frame_count`, and maximum `max_distinct_drawing_count`. An empty motion-region list permits no changed pixels; omit it only for openly declared unconstrained motion. Errors are nonzero; preserve stdout/stderr and log the failure rather than ignore it.

The output parent must exist and the export directory must not. Core output saves read-only byte-identical `master.png` and `sequence/frame-0000.png` entries, portable `manifest.json`, exact `timing.json`, `spritesheet.png`, indexed `contact-sheet.png` (`contact-sheet-index.json`), exact-size `playback-native.gif`, enlarged `playback.gif`, local `playback.html`, and `qa.json`. The HTML viewer uses native PNGs and timeline durations and provides native/enlarged playback. Open it using the available browser/viewer; report how it was actually observed. Any local HTTP server needed is preview infrastructure, not artwork modification.

`qa` checks dimensions, binary alpha, palette union, margin/constraint limits, unique decoded RGBA count, per-frame/master and adjacent/loop-boundary changed counts/bounds, and changes outside declared motion. It cannot infer semantic action or artistic quality. `pack` additionally compares sheet pixels and verifies GIF decoded visual pixels/timing against the original timeline, permitting lossless merging of identical adjacent holds. GIF inputs are explicitly indexed with their exact existing RGB entries before encoding, preventing the implicit truecolor palette conversion from merging nearby colors even in a small palette. This is a lossless representation/export step, not artwork editing. Transparent hidden RGB bytes need not survive GIF; visible colors/alpha must.

Default `--gif-fidelity strict` rejects quantization/timing mismatch and does not create the final export directory; capture its error in the ledger. `timing.json` records `unit: milliseconds`, loop flag, total duration, timeline count and frames with file/duration/start/end and optional pose ID. GIF delays use 10 ms units: choose multiples of 10 ms. Each frame supports at most 256 visible RGB colors when fully opaque, or 255 visible RGB colors plus one transparency entry. Frames beyond this capacity are rejected in both strict and report modes rather than quantized silently; report mode can still retain a declared timing-only fidelity failure. `--gif-fidelity report` preserves a review package with explicit GIF fidelity failure (`passed:false`, `package_created:true`, exit code 2); it is not a pass or a silent waiver of a requested exact format. Exact PNGs/timeline remain authoritative. A viewer may clamp short delays even when encoded timing is exact. Read `exports.gif_fidelity_passed`, detailed `exports.gif`/`native_gif` pixel/timing results, `file_hashes`, and `visual_status` before claiming a final. Technical output starts visually unreviewed.

## Interpret results honestly

- Timeline entries and distinct RGBA drawings are different counts
- Native dimensions/palette/alpha and structural package validity do not prove pixel craft
- Changed pixels do not prove the requested action happened
- No edge contact is useful evidence; edge contact alone does not prove clipping
- A still/contact sheet, launched viewer, sampled playback, and continuously observed loops are different evidence levels
- Matching first/last images does not prove coherent intermediate motion or timing

Use native/transition/playback review rather than replacing it with a structural score.

## Semantic pose-plan packaging

```sh
python3 <this-skill>/scripts/pixel_pipeline.py plan animation/pose-plan.json exports/loop-v1 --project project.json --scale 6 --columns 4
```

The plan has `schema_version: 1`, `width`, `height`, `tag`, `master_pose`, `poses` keyed by semantic ID with `{file,status}`, and `timeline` entries `{pose_id,duration_ms}`. New plans use `accepted`, requiring `sha256` and `quality_review:{status:"accepted",artifact_sha256:"...",notes:"concrete native review"}` bound to the actual PNG. Draft `study` and `needs_revision` cannot package. Legacy `approved`/`generated` remain compatible declarations, not proof of visual approval. Optional `required_phases` lists semantic phase IDs; timeline `phase` entries must cover all of them. Every required pose must exist. See `assets/pose-plan.template.json`. Optional native limits/constraints pass through as in the direct manifest. Duplicate JSON keys, undefined pose IDs, absent files, bad statuses/sizes and unmet constraints fail. The plan command resolves paths, constructs exact frame order/durations and invokes the same packager; it neither generates missing art nor quietly substitutes another pose. Complete-loop workflow must generate/inspect/normalize missing poses first. Preserve the semantic plan and selection/timing rationale in the ledger.

## Generated-patch assembly

```sh
bash <this-skill>/scripts/assemble_generated_patches.sh --master master/master.png \
  --candidate native/page-lift.png --regions animation/regions.json --output animation/frames/page-lift.png
```

For new local runs start from `assets/local-motion-plan.template.json` with schema_version:2 and complete its coverage declarations/review below. Legacy compatibility accepts a nonempty rectangle list or an object with `animation_mode:"local"`, `motion_regions`, optional `motion_mask` and optional alignment/anchor review. `motion_mask` is an opaque binary black/white native PNG: white selects candidate pixels. A standalone mask uses `mask_semantics:"white_selects"` (default); combining rectangles and a mask requires explicit `mask_semantics:"intersection"`. Native dimensions, binary values, nonempty/non-full-canvas selection and mask hash are checked. `--mask mask.png` is an alternative to specifying the mask in the JSON, not both. Declare it before generation from the approved native master and motion plan. Rectangles are half-open native coordinates with motion clearance; a full-canvas union is rejected. Inputs must already share dimensions and alignment. The helper does not automatically align poses.

The helper copies candidate RGBA, including transparency needed to erase the old pose, only within the declared effective selection and keeps master pixels elsewhere. Outputs: PNG, `*-mask.png` and `*.assembly.json` with actual source/output hashes, region/mask map and hashes, and exact outside-selection preservation checks. Candidate drift metrics reveal raw generated differences; they do not by themselves prove geometric misalignment. Inspect stationary landmarks before assembly, and inspect seams/attachments and intended action afterward. Discarded outside-mask pixels need not equal the master, but the assembled output must. Do not use widening masks or independent recentering to conceal an unusable pose. Creative repair uses imagegen within the declared cap.

Optional `anchor_regions` in the regions object identifies exact static landmark rectangles: mismatching candidate/master RGBA there rejects the candidate before compositing. It is deliberately optional because generated static pixels may be discarded safely outside the motion mask. For every accepted candidate, record `alignment_review` with `status: passed`, exact `master_sha256`, exact `candidate_sha256`, and concrete `notes` after actual visual landmark inspection. The helper validates those hashes; absent evidence remains `unreviewed`, and dimensions alone never establish alignment. Preserve the predeclared region geometry, adding candidate-specific review records in a new version rather than widening masks.


## Accepted native reference enlargement

```sh
python3 <skill>/scripts/native_reference.py --input masters/master.png \
  --output references/master-8x.png --scale 8 \
  --acceptance reviews/master-native-acceptance.json --project project.json
```

Acceptance JSON is `{status:"accepted",artifact_sha256:"actual SHA-256",notes:"observed native acceptance"}` after the separate authority/approval gate. The helper verifies source pixels/hash, copies each RGBA cell at an integer scale, verifies exact enlargement and writes `*.reference.json`. The unchanged native master remains canonical. This enlargement is the primary imagegen reference for animation; accepted neighbor enlargements provide motion continuity. Concept images are supplementary only. A correct reference does not predict generator output dimensions, cell geometry, camera alignment or crop.

## Full-body declared geometry and review evidence

Set `animation_mode:"full_body"` before generation; omit local masks/regions. Whole native frames remain unchanged in the package. Optional `geometry_constraints` supports:
- max_centroid_shift_px; bbox_width_ratio and bbox_height_ratio as [minimum,maximum]
- root_anchor_px paired with max_root_drift_px
- contact_y_px paired with max_contact_drift_px

Choose measured tolerances appropriate to the requested motion, not a false pixel lock. Bbox/centroid are alpha-shape measurements, not anatomical identity or scale proofs. `full_body_reviews` is a list indexed by timeline `frame`, with exact master_sha256 and frame_sha256. Each can contain identity, landmarks and contact review objects `{status:"passed"|"failed",notes:"observed finding"}`; landmarks may include root_px and contact may include contact_px lists. Required declared root/contact checks need those measured reviewed points. Missing identity/contact review remains `unverified`; copied assertions are not an automated recognition claim. See `full-body-motion.md` for visual criteria.


## Local-motion coverage and contrast review (v4.1)

Before accepting a local mask, declare `schema_version:2`, `animation_mode:"local"`, its effective motion_regions/motion_mask, and all three footprints:
- original_moving_regions or original_moving_mask: the WHOLE original moving part, including outlines and small edge cells
- motion_envelope_regions or motion_envelope_mask: intended complete swept area; compare actual generated keys to it afterward
- vacated_regions or vacated_mask: the old occupied area needing generated erasure/replacement; an explicit empty region list is allowed only when none is needed

These declarations may use rectangles or shaped binary masks. They must fit inside the effective selection. Mask images are native-size opaque binary black/white. A containment pass validates declared pixels only; it does not discover the true hand, page, foot or anatomy automatically.

```sh
python3 <skill>/scripts/local_motion_review.py preflight \
  --master masters/master.png --regions animation/regions.json --output reviews/mask-preflight-v1
```

Inspect the emitted source/native/NN and white/dark/checker/high-contrast previews, including coverage overlays and exterior boundaries. Set coverage_review only after actual inspection: `{status:"passed",master_sha256:"...",contract_sha256:"...",notes:"concrete footprint/envelope/vacated observations"}`. Use hashes emitted by preflight; contract hash covers geometry/masks independently of the review object. Run a new preflight after filling review. Schema-2 assembly rejects undercoverage, stale binding and missing/failed review. Legacy specs remain technically usable but unverified; use schema2 for new work.

After assembly, compare master→key and each relevant adjacent pair:

```sh
python3 <skill>/scripts/local_motion_review.py compare \
  --master masters/master.png --candidate animation/frames/attempt-0004/key.png \
  --regions animation/regions.json --output reviews/master-to-key-v1
```

Candidate is the already composed frame, not raw drifting generator output. For adjacent poses add `--neighbor animation/frames/attempt-0003/neighbor.png`; keep --master pointing to the original accepted master. Three-column strips show master→neighbor→candidate, both composed frames are checked against original protected pixels, and neighbor→candidate deltas remain separate. Never rebind coverage approval to a neighbor just to bypass the original master. The helper never composes, redraws or accepts art. Native/NN snapshots preserve RGBA; background/overlay strips are diagnostic only and must never become generation sources or final frames. Outside-selection drift blocks a valid local comparison. Component/split/remnant alerts require visual investigation; decorative islands can be intentional, and no alert does not prove semantic cleanliness. Report incomplete old-part coverage or clipping rather than widening a fixed mask to make technical QA pass.
