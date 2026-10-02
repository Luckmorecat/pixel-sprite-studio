# Visual review and playback evidence

Technical scripts prove limited pixel/container facts, not animation quality. Judge against the actual request, approved master and profile. Use `assets/visual-review.template.json`, then append the completed report to the run ledger as a review event. Record artifact hashes and which export version was viewed.

## Per-pose checks

View every frame at native size and an integer nearest-neighbor enlargement, on contrasting backgrounds when transparency matters. Review:
- Face/gaze/expression remains readable; identity, proportion, costume and palette roles stay coherent
- The claimed semantic pose is actually present, with hand/prop interaction where relevant
- No extra anatomy, dangling/severed attachments, torn contours, or action clipped by canvas/mask
- Static anchor and props do not jump; no independent whole-image recentering
- Localized composite has no visible rectangle edge, foreign color patch or unnatural movement cutoff
- On white, dark and checker backgrounds, the whole original moving part disappears or deforms coherently; no protected outline/skin/prop fragment remains just outside the mask when the part moves
- Compare master→key and every newly formed adjacent pair at native size and exact integer enlargement before final phase acceptance; do not wait until final playback to inspect old-part remnants

For prop/limb actions, also compare the action-continuity contract: the same active and support parts, attachment, occlusion and visible anatomy count must remain coherent across adjacent phases. Do not accept an extra hand merely because the paper/prop looks clearer. For accepted poses, state an observable reason, not "looks good". Preserve failures and tie any generation repair to one named defect/pose. Do not silently repaint pixels or patch a trial outside its declared masks.

## Transition and loop checks

Inspect every ordered transition, including the last-to-first wrap. Name source/destination semantic IDs and durations. Matching endpoints does not establish a coherent cycle. Check action spacing, abrupt volume/silhouette change, stray flash pixels, eye/face pops, tail/book/foot jitter, disappearing pages, overlong holds and duplicated endpoint pauses. A page-turn claim requires an observable page state/trajectory and plausible hand contact, not just a moving arm. Distinguish character motion from a whole-sprite offset.

Open packaged `playback.html` or another capable viewer and run at intended speed, native size and integer enlargement. The HTML viewer uses unchanged PNGs plus exact timeline metadata, so it is an additional review route when GIF has format limits. Observe at least two cycles when the available tool genuinely supports continuous video/frame observation. If the tool offers only isolated screenshots, record samples with time/frame indices across the loop plus a full frame/transition inspection; label this `sampled_playback`, not continuous viewing. Starting a player or seeing the first frame is `launched_only`, not a playback pass. If local browser viewing is unsupported, use an available native viewer in read-only playback mode without changing security settings or saving image edits. If no capable viewer can be opened, mark playback `unavailable` and visual motion approval `unverified`. Record which primary-action phases were actually sampled at native size: seeing only a resting frame while a player runs does not verify the action. Static phase inspection may supplement, but cannot be relabeled as native-speed playback. Slower/stepped diagnostic viewing must be distinguished from intended-speed viewing and must not alter final timing.

A second visual reviewer is useful when available, but is not independent proof. Give it the ordinary request, approved reference and output artifacts; avoid leaking intended findings. Report disagreements or uncertainty instead of replacing them with structural QA.

## Decision

Classify each requested action/criterion `pass`, `revise`, `fail`, or `uncertain`, with evidence. `technical_pass` plus a readable still is not sufficient for a finished animation. Do not claim more observation than tools supplied. Report overall `visual_pass` only when pose, transition and playback evidence adequately support it; sampled playback can support a qualified review, with its limitations explicit. If any central action remains uncertain or fails, deliver the reviewable package with that status rather than claiming completion.

Timing/order changes can be automated decisions inside the current action/limits. Log the reason, old/new timings, and export a new version. Creative pose repairs must use imagegen within the bounded budget. A tool/skill defect found during an isolated run belongs in its failure report and later improvement cycle, not a live rewrite of the tested skill.


For local masks, review declared original footprint, future/actual envelope and vacated area separately. A containment check validates only what was declared. Disconnected-component diagnostics can flag a newly isolated shape, but dots, detached accessories or existing highlights can be intentional; neither zero warnings nor a preflight pass proves anatomy or clean erasure. Record actual observation and remaining uncertainty. Undercoverage is a plan failure, not permission to enlarge a mask after observing drift or to report technical preservation as a visual pass.
