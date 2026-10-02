# Full-body motion contract

Use when articulated locomotion or another action moves most of the character. Declare `animation.mode: "full_body"` before generation. This mode is not a fallback that converts a failed local mask into success.

## Plan native evidence

Specify the action's actual semantic phases, camera and root/ground model: walk-in-place holds the character in place while limbs articulate; travel across the frame may move the root by a planned trajectory. Choose requested behavior instead of forcing one definition. Record contact feet/points per phase, support changes, expected floor, root tolerance, apparent-scale tolerance and intended silhouette changes. Exact numerical tolerances must be project-specific measured choices, not arbitrary universal defaults.

Keep identity proportions, outfit structure, distinctive marks and palette roles. Pose-dependent foreshortening and silhouette size are permitted when coherent. Do not require exact head/body pixels or an invariant alpha bounding box. Do not animate the whole sprite by translation and claim a walk.

## Source and pose checks

Use the exact integer nearest-neighbor enlargement of accepted native master as primary imagegen reference, plus accepted native action-neighbor references. Keep large concepts supplementary. Generate one semantic phase at a time, normalize its measured source geometry with shared project requirements, and retain the entire native PNG. Local patch assembly is not used.

Technical tools can measure changed bounds, occupied margins, centroid/bbox scale summaries and compare declared anchor/contact/scale evidence bound to current PNG hashes. They cannot infer skeleton, identity, correct anatomy or genuine foot support from opaque pixels alone. Missing visual/landmark evidence stays `unverified`; a helper must not invent a pass.

Review at 1× and enlargement: consistent apparent body mass/proportions, facial identity, grounded support foot, no skating/floating, deliberate passing/contact poses, plausible limb count and occlusion, root drift appropriate to in-place/travel intent, and contact changes continuous across wraparound. Tolerated planned root movement is not a global ban on pixel changes. A stationary image bob is not articulated motion.

## Outcome

Canonical drawings remain native PNGs with per-frame timing. Run full technical QA and intended-speed playback review. Distinguish synthetic helper coverage from an actual generated full-body art test; only the latter can support a claim that the workflow produced a readable requested full-body animation.
