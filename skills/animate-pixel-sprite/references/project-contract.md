# Project and acceptance contract (4.2)

## Select records from the request

- **Standalone:** one requested stage or existing-art assembly ending this session uses `standalone-records.md`. Keep request, unchanged sources, bounded attempts, reviews and authority in a compact task record. No skill snapshot, full ledger or bundle is required merely to deliver it.
- **Full:** a requested multi-stage outcome or cross-session project uses `run-records.md` plus `portable-handoff.md`, retaining one run/budget. Snapshot only participating runtime packages for reproducible continuation.
- Never downgrade a supplied full run or reset its counters. If a standalone task expands, use the documented evidence-only bundle migration in `standalone-records.md`; do not initialize a replacement history.

The common route is identity → optional views/action → refinement → optional animation. Run only requested or necessary stages. Discover skills by catalog/frontmatter names, never assumed sibling paths.

## Pipeline configuration

Keep data outside installed skills. Pipeline commands use `project.json` and its relative `profile.json`. Start from the templates, replace examples with actual choices and remove the animation object for static work. Validate with `python3 scripts/project_config.py project.json`. Project schema `3.0` remains compatible with 4.1 helpers:

- asset_id, exact brief, profile relative JSON path, native_canvas_px [width,height]
- limits: palette_max, binary_alpha:true, min_margin; unsupported partial alpha is a blocker, never silently threshold it
- optional measured anchor_px; do not copy an example anchor
- budget: max_calls, max_total_repairs, repairs_per_pose and optional planned stage allocations as integers
- animation only when relevant: mode local|full_body, duration_ms, max_unique_drawings, max_timeline_entries, optional min_unique_drawings

Use the same config in normalization, assembly and packing. Omitted helper values inherit it; explicit contradictions fail. Static QA applies native/format/set constraints without pretending to satisfy future animation timing/counts. Never change requirements to conceal failed QA.

Profile records actual identity/style: pixel_art medium, silhouette/proportions, face/species markers, outfit, asymmetric details, palette roles, projection and permitted deformations. Record supplied references and inferred hidden details. Examples are neither user preferences nor approval.

## Source and generation safeguards

Use imagegen for creative raster creation/repair, following its current instructions and inspecting edit inputs. Code may normalize, select generated pixels through declared masks, measure and package; it must not draw substitute artwork. Existing fit native art need not be regenerated or lossy-normalized.

Reserve a stable attempt ID before every generation. Preserve every returned original unchanged in a fresh attempt-scoped path; keep rejected sources, prompts, exact arguments and reference roles/hashes. Candidates and repairs use new paths. Never rename a rejected source and reuse its filename, overwrite a master, or trust historical paths without matching hashes.

Plan caps before calling the generator. Standalone tasks use narrow task-specific caps; full-flow defaults are at most 24 calls, 6 total targeted repairs and 2 repairs per semantic pose unless the user specifies otherwise. Count failed, cancelled and pending starts. One project counter spans stages/sessions; renaming a pose or changing stages cannot reset repairs. A cap is not purchase authorization. At exhaustion report incomplete/needs_revision.

Measure returned dimensions and crop geometry; requested size never proves actual output size. Normalize only matching-aspect measured canvases/crops, nearest-neighbor and no dithering. Do not independently trim/recenter set members. Changed geometry needs a documented equivalent transform or rejection, not a grid-lock bypass. See the relevant `pixel-tooling.md` section before using a command.

## Acceptance is role-specific

Each artifact has a role and status study|accepted|needs_revision; technical passed|failed|unverified and visual accepted|rejected|unverified stay separate. Identity/view/action studies are not native masters. Normalization/QA cannot approve identity, action or pixel craft.

Acceptance binds exact asset/source hashes, role, concrete review, authority evidence and actor user|assistant. User-reserved checkpoints require actual approval. Delegated creative decisions allow assistant acceptance within the quoted current scope; never report that as the user approving unseen pixels. Preserve unresolved limits and actual evidence level.

Native masters additionally bind measured canvas, palette/grid/anchor, source normalization provenance and intended use. Animation uses their exact integer nearest-neighbor enlargements as primary pixel references and preserves canonical PNGs unchanged; large concepts are supplementary. A creative master change requires new acceptance.

For sets, preserve common native canvas, palette/material roles, grid, anchor convention, identity, proportions and camera assumptions. Declare member roles/view/pose and required members. Silhouette width may legitimately vary. Review set consistency visually; matching metadata or color counts cannot certify it.

## Delivery and continuation

Standalone delivery includes the requested art, previews, compact record and limitations. Full boundaries use the checked self-contained bundle in `portable-handoff.md`, preserving accepted sources, approvals, role/readiness, budgets and records. Verify hashes and inspect actual pixels after relocation. A fresh session needs the bundle plus ordinary request, never hidden chat context. A missing required accepted asset blocks readiness; optional unrequested views do not.
