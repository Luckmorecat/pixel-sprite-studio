# Shared project and acceptance contract

Keep project data outside installed skills. All paths within a handoff bundle are bundle-relative. Resolve other skill packages by catalog/frontmatter name, not assumed directory names. Version 4.1.0 is a label; frozen per-file and aggregate hashes identify the exact version.

## Routing

Character Identity → optional Multi-view Reference → Action Pose Design → Refine Pixel Art → Animate Pixel Sprite is a common flow, not a mandatory five-stage chain. Refinement works after identity, views, action or on a consistent selected set. Skip optional views or action design when unnecessary. Animation requires separately accepted native PNG master(s). Format-specific export is a separate task after core output.

- Identity: neutral pixel-first design + native study; fixed recognizable proportions/outfit/palette roles
- Views: requested consistent angles derived from accepted identity; explicit invented hidden details
- Action: identity-preserving action/composition study, anatomical/support/prop roles, native readiness
- Refinement: generated adaptation only as needed, deterministic normalization, single/set review, accepted native master(s)
- Animation: accepted native master enlarged exactly for primary generation reference; accepted new drawings + ordered timeline; local or full-body checks; playback evidence

Design acceptance is not native-master acceptance. Source illustration dimensions are not native output dimensions. Native normalization is not hand-pixel cleanup. Technical QA is not visual approval. Separate each judgment and its evidence.

## Required project files

Use `project.json`, `profile.json`, unchanged `sources/`, versioned `candidates/`, accepted assets, reviews and run evidence. Start from `assets/project.template.json` and `assets/profile.template.json`; examples are not user approvals or universal style defaults. Before use replace the brief, scope and limits with the actual task. Validate with `python3 scripts/project_config.py project.json`.

`project.json` schema "3.0" includes:
- asset_id, exact ordinary brief, profile relative JSON path, native_canvas_px [width,height]
- limits {palette_max, binary_alpha:true, min_margin}; unsupported alpha is a blocker, never silently imposed
- optional measured anchor_px; do not guess an anchor from the example
- budget with max_calls, max_total_repairs, repairs_per_pose and planned stage allocations as integer fields
- optional animation {mode:local|full_body, duration_ms, max_unique_drawings, max_timeline_entries, min_unique_drawings optional}

Use the same config in normalization, pose-plan assembly and direct manifest packing. Missing helper values inherit it; explicit contradictions reject, even when an explicit alternative sounds stricter. Do not alter project requirements to conceal failed QA. Static refinement uses explicit static scope to apply native/format/set checks without pretending to satisfy future animation timing. Final animation uses animation scope.

Style/identity belongs in `profile.json`: medium pixel_art, silhouette, proportion anchors, face/species markers, outfit components, asymmetric details, palette role assignments, projection/angle convention and permitted deformations. Record user references and inferred hidden details. Do not save example taste as a user preference. No fixed face size, anime look, character species or palette is universally required.

## Approval and status

Every deliverable has a role plus status `study`, `accepted` or `needs_revision`. Also record technical status `passed|failed|unverified`, visual status `accepted|rejected|unverified`, source/native geometry, exact file/hash, source/hash, review, approval scope and unresolved limits. A study may be accepted as identity/view/action reference without becoming role `native_master`.

For accepted assets record user approval or assistant acceptance under current quoted delegation, exact asset and source hashes, evidence file, actor and timestamp. For assistant acceptance include the delegation file. A request delegating the finished artifact's creative decisions covers necessary gates unless the user reserves a checkpoint; never relabel that as the user personally approving unseen pixels. An unapproved study cannot be made ready by renaming its status.

## Geometry and sets

Measure actual generated dimensions before conversion; prompts and reference geometry do not guarantee returned dimensions, cell spacing or alignment. Preserve originals. Normalize from fixed full-canvas/matching-aspect measured crop with no dither and nearest-neighbor sampling. Do not auto-trim/recenter each pose. A source geometry change needs a documented equivalent transform or rejection/regeneration, not a blind grid-lock bypass.

For sets, preserve common native canvas, approved palette, grid, anchor convention, identity/proportions and camera assumptions. Record set_id and member roles/view/pose; validate required members. Silhouette width/bounds may legitimately vary by view/pose. Palette union and material roles both matter; exact color counts alone do not preserve materials. Refinement set consistency requires human/model visual review, not just matching metadata.

## Calls, repairs and portable continuation

Plan total and per-stage allowances before the first generation. Default full-flow ceiling is 24 calls, up to 6 targeted repairs total and 2 per semantic pose, unless the user specifies other limits. Simpler tasks should plan fewer; this is a work limit, never permission for additional purchases. Count failed/cancelled/pending starts. Views, action, refinement and animation all use one counter. Splitting sessions, switching stages, reusing a refined set or renaming a pose cannot reset budgets.

Keep exact prompts, tool arguments, references with roles/hashes, returned originals, actual dimensions, decisions and failures in the run ledger. Include attempts and remaining counters in portable handoffs; verify them against evidence rather than trusting a prose number. An interrupted attempt still uses a call. Never reset a run because its remaining budget is inconvenient.

## Handoff

Use `references/portable-handoff.md`. The complete artifact bundle and an ordinary task request must suffice in a fresh session. It includes project/profile, accepted identity/native assets and relevant optional views, source/normalization evidence, role/contact/readiness, approvals/delegation, limitations, budget counters and frozen run evidence. Do not require private memory, earlier chat, original machine paths or an extra parent rescue message. Verify hashes and inspect actual pixels before proceeding.


## Attempt-unique immutable artifacts

For each generation use its reserved ledger ID in source and candidate paths, e.g. `sources/attempt-0004/original.png` and `candidates/attempt-0004/native.png`. Preserve returned original bytes before conversion; if the tool used an unrelated filename, copy its bytes into the fresh attempt directory and retain the returned original too. Never rename a rejected source out of the way and reuse its former filename for a later candidate. Keep rejection/acceptance in review records; repairs get a new attempt ID and new paths. Native assembly and accepted delivery aliases are also new files, never replacements for historical candidates.

New ledger CLI runs enforce attempt-scoped original output names and reject path reuse. For newly generated normalization use `--run RUN --attempt-id ATTEMPT`: it validates the captured original hash and source/candidate namespaces. Imported assets without a generation attempt retain their own immutable input/provenance and do not invent one. A historical source path is advisory: verify the recorded hash; resolve renamed/reused paths with `run_ledger.py resolve RUN --sha256 HASH --source-path OLD_PATH`. Use the verified immutable evidence copy, never a newer image at the old name. Normalization accepts that exact captured evidence path with --run/--attempt-id; the new replay candidate still needs the original attempt namespace. Do not rewrite an old sidecar/ledger to match a changed path.
