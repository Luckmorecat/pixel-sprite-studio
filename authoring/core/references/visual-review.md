# Visual review and playback evidence

Technical scripts prove limited pixel/container facts, not animation quality. Judge against the actual request, approved master and profile. Use `assets/visual-review.template.json`; preserve the report in the compact delivery review or, for a full run, append it as a review event. Record artifact hashes and which export version was viewed.

## Per-pose checks

View every frame at native size and an integer nearest-neighbor enlargement, on contrasting backgrounds when transparency matters. Review:
- Face/gaze/expression remains readable; identity, proportion, costume and palette roles stay coherent
- The claimed semantic pose is actually present, with hand/prop interaction where relevant
- No extra anatomy, dangling/severed attachments, torn contours, or action clipped by canvas/mask
- Static anchor and props do not jump; no independent whole-image recentering
- Localized composite has no visible rectangle edge, foreign color patch or unnatural movement cutoff
- On white, dark and checker backgrounds, the whole original moving part disappears or deforms coherently; no protected outline/skin/prop fragment remains just outside the mask when the part moves
- Compare master→key and every newly formed adjacent pair at native size and exact integer enlargement before final phase acceptance; do not wait until final playback to inspect old-part remnants

For prop/limb actions, also compare the action-continuity contract: the same active and support parts, attachment, occlusion and visible anatomy count must remain coherent across adjacent phases. Do not accept an extra hand merely because the paper/prop looks clearer. For accepted poses, state an observable reason, not "looks good". Preserve failures and tie any generation repair to one named defect/pose. Do not silently repaint pixels or patch artwork outside its declared masks.

## Transition and loop checks

Inspect every ordered transition, including the last-to-first wrap. Name source/destination semantic IDs and durations. Matching endpoints does not establish a coherent cycle. Check action spacing, abrupt volume/silhouette change, stray flash pixels, eye/face pops, tail/book/foot jitter, disappearing pages, overlong holds and duplicated endpoint pauses. A page-turn claim requires an observable page state/trajectory and plausible hand contact, not just a moving arm. Distinguish character motion from a whole-sprite offset.

Open packaged `playback.html` or another capable viewer and run at intended speed, native size and integer enlargement. The HTML viewer uses unchanged PNGs plus exact timeline metadata, so it is an additional review route when GIF has format limits. Observe at least two cycles when the available tool genuinely supports continuous video/frame observation. If the tool offers only isolated screenshots, record samples with time/frame indices across the loop plus a full frame/transition inspection; label this `sampled_playback`, not continuous viewing. Starting a player or seeing the first frame is `launched_only`, not a playback pass. If local browser viewing is unsupported, use an available native viewer in read-only playback mode without changing security settings or saving image edits. If no capable viewer can be opened, mark playback `unavailable` and visual motion approval `unverified`. Record which primary-action phases were actually sampled at native size: seeing only a resting frame while a player runs does not verify the action. Static phase inspection may supplement, but cannot be relabeled as native-speed playback. Slower/stepped diagnostic viewing must be distinguished from intended-speed viewing and must not alter final timing.

## Independent checkpoints

Keep technical checks and immediate creator review of every output. When clean independent workers are supported, obtain a separate review of:
- The completed requested multi-view set before set acceptance
- The hardest distinctive animation key after normalization/composition and creator review, before dependent frames
- The final animation, including exact order/timing, transitions/wrap and actual playback evidence

One still/view/cel needs no mandatory extra reviewer; use one when uncertainty warrants it. Reuse-existing-poses authorizes no generation: check the hardest supplied key, or reuse a current independent pass bound to the same bytes and constraints, then use a fresh final reviewer.

Use a fresh, clean reviewer at each checkpoint, without the creator conversation or verdict. Its initial packet contains the ordinary request, relevant constraints, accepted references and roles/hashes, actual candidate PNGs at native size and integer enlargement, and for animation the semantic IDs, exact timeline and playable export. Include needed technical facts, not expected defects, earlier trial conclusions or leading instructions. A context-contaminated reviewer is not independent.

Require actual pixel inspection. Preserve its own report alongside the creator report in existing review evidence; the optional `checkpoint_review` section can hold it without changing approval schemas. Reuse the existing native/enlarged, pose, transition, criterion and playback fields. Identify inspected hashes and missing evidence; each finding names the view/frame/transition, region, concrete observation, severity (blocking/major/minor), and narrow next step. A hash, filename or text description alone is not visual evidence. `pass` requires adequate observation and no unresolved blocking/major defect. `needs_revision` blocks dependent generation/set acceptance/final success; `unverified` is not pass. Preserve disagreements and resolve them against evidence, never silently prefer the creator. Minor optional polish does not require another generation.

Review grants no acceptance authority or new call/repair allowance. Use only already-permitted bounded repairs; the same reviewer may perform one focused re-review per repair, checking the changed area and affected identity/adjacency. At caps retain unresolved `needs_revision`/incomplete. Changed artwork hashes invalidate affected reviews; changed timing/order invalidates affected transition/playback evidence. Preserve previous reports. Packaging-only changes do not require regenerating unchanged art.

If clean independent workers are unavailable, perform the same creator checks, record `self_review_only`, keep independent verdict `unverified`, and disclose the capability limit. Supported creator acceptance under existing authority remains possible; do not invent independence. A reviewer that cannot inspect available pixels must report missing evidence, not pass. Each reviewer records only its own playback observation: launched-only, sampled, continuous or unavailable. It cannot inherit the creator's viewing claim; unavailable or resting-frame-only playback leaves motion unverified.


## Decision

Classify each requested action/criterion `pass`, `revise`, `fail`, or `uncertain`, with evidence. `technical_pass` plus a readable still is not sufficient for a finished animation. Do not claim more observation than tools supplied. Report overall `visual_pass` only when pose, transition and playback evidence adequately support it; sampled playback can support a qualified review, with its limitations explicit. If any central action remains uncertain or fails, deliver the reviewable package with that status rather than claiming completion.

Timing/order changes can be automated decisions inside the current action/limits. Log the reason, old/new timings, and export a new version. Creative pose repairs must use imagegen within the bounded budget. Report a tool/skill defect with its evidence; do not change installed instructions to turn a failed artifact into an accepted one.


For local masks, review declared original footprint, future/actual envelope and vacated area separately. A containment check validates only what was declared. Disconnected-component diagnostics can flag a newly isolated shape, but dots, detached accessories or existing highlights can be intentional; neither zero warnings nor a preflight pass proves anatomy or clean erasure. Record actual observation and remaining uncertainty. Undercoverage is a plan failure, not permission to enlarge a mask after observing drift or to report technical preservation as a visual pass.
