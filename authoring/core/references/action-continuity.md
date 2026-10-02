# Native action readability and contact continuity

Read this for prop interactions or articulated actions whose meaning depends on several related poses. It is a planning/review method, not permission to modify a locked master or a promise that image generation will succeed. Use the current profile and limits; no fixed coordinates, palette, camera, or solution applies to every character.

## Before accepting the design/master

At native size, identify the part that must move and the stationary support. A pleasant still with a readable face may still be unusable for the requested action. Require enough visible action surface, clear contact points and movement space before approving the animation-ready master. For turning a page in an already-open book, the open page surfaces/spine must be identifiable rather than a red slab or an almost edge-on sliver. Do not shrink the face to rescue the prop: simplify secondary costume detail or choose a suitable view/composition while design selection is still open.

Check the moving material against its future background and nearby anatomy. Similar page, skin and sleeve colors can merge after normalization even when their high-resolution source is distinct. Preserve the requested palette/clothing and create separation through shape, value or an existing outline/shadow role; do not silently recolor the character or exceed a palette limit. A thin physical object may need a broad visible plane and clear contour on the native grid, rather than a one-pixel ribbon. Record what specifically remains visible at 1×.

If the chosen master cannot support the requested action, fix this through the refinement stage's declared imagegen budget before locking it. For an already approved imported master, report the conflict and get any required permission to change it; do not quietly redesign during animation.

## One action contract across all phases

For the planned action, record:
- Direction/view convention and names for the moving actor part, support part and prop; map left/right explicitly in viewer coordinates
- Fixed anchors/attachment points, the moving object's origin and destination, and the active hand/limb count
- Which original resting parts move, disappear through occlusion, or remain; moving a hand must not leave its old resting copy behind
- For every semantic phase: intended visible shape, contact/attachment, moving/support part states, expected occlusion, and its difference from the preceding/following phase
- Native-scale recognition criterion and a concrete rejection condition for each phase

Use `assets/action-continuity.template.json` in animation, or equivalent project data. This evidence does not change the technical pose-plan schema. It is a visual acceptance record, not something pixel-count QA can certify.

For a page turn, a reasonable contract follows the same leaf from one stack, across the same spine, onto the other stack. The same turning hand stays attached or releases deliberately; any intentional handoff must be planned and visibly continuous; the other hand supports consistently. Lift/cross/settle need visibly different paper silhouettes and believable contact, not unrelated hand poses. Reject a forearm-shaped pale blob, an unplanned/unexplained active-hand switch, unexplained new hand, detached paper, or a page that vanishes instead of settling. Do not add cosmetic motion to disguise an unreadable requested action. Every explicitly requested action remains an acceptance requirement.

## Test the hardest meaningful pose first

Choose the pose that best demonstrates the central action's recognizability, such as the visible mid-turn page, before spending the remaining pose budget. Generate, normalize, assemble and review that pose at native size alongside the master. If it cannot be recognized as the intended object/action without relying on its filename or enlarged illustration, spend a bounded targeted repair on that problem first. Do not generate an entire dependent sequence from an unresolved ambiguous key.

The first key and its repairs use the master plus any available approved references; they cannot require a neighboring key that does not yet exist. After an acceptable anchor key exists, generate connected phases sequentially. Each call uses the immutable master for identity plus the accepted adjacent/action key for contact and geometry. State reference roles explicitly. A later phase must continue the same actor/object state; a repair should reference the accepted neighbor and may additionally include the rejected candidate as a negative diagnostic. Do not provide only the master for every dependent phase, and do not chain solely from the immediately previous generated image, which can accumulate identity drift. Independent actions such as a blink may be generated separately after the high-risk action is viable; if the user requested them, they must still be completed for an overall pass.

After each new phase, inspect the ordered pair or three-pose strip at native size before proceeding: same moving part, plausible trajectory, consistent support/occlusion and distinct readable object states. Do not infer continuity because prompts used the same nouns. Reject extra anatomy even if the page shape improved. A single review failure can invalidate a phase without invalidating preserved good keys.

## Repair and stop honestly

Use the existing global/stage/per-pose caps. Prioritize a central ambiguity or broken transition, not a uniform repair call for every pose. Each repair states the failed visible criterion and carries forward the identity/contact contract; record why it is preferable to another unchanged attempt. Do not spend more calls merely because allowance remains. At an exhausted central-action gate, stop the dependent sequence or deliver a clearly incomplete review package. Do not change the skill, widen masks, hand-paint art, rename poses to evade caps, or relabel an uncertain phase as accepted.

Preserve failed action evidence and report the observed blocker; do not conceal it by changing acceptance criteria.


## Local-motion coverage readiness

Before locking a local mask, identify the entire old moving limb/prop/material footprint, including perimeter and tiny outline pixels, the intended swept envelope, and areas that need generated transparency or background replacement when vacated. All declared footprints must fit the effective mask, with measured clearance. Preserve stationary support separately. Use the schema-2 local-motion preflight and contrast previews; inspect native and integer views on white, dark and checker backgrounds. After the hardest generated key, compare old→new and new neighboring phases, including mask exterior. Reject detached old-part remnants, duplicate anatomy or clipped envelopes even if every protected pixel is unchanged. Do not auto-widen a fixed mask to hide an inadequate plan.
