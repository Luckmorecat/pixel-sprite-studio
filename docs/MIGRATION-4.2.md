# 4.2 migration

The six public skill names remain unchanged. Core packages advance from 4.1.0 to 4.2.0; exporter packaging documentation advances from 1.0.1 to 1.0.2 without changing its encoder. No license is introduced.

- Existing project schema 3.0, pose-plan schema 1, local-coverage schema 2, full run ledgers and portable bundles remain supported. Continue an existing run with its captured helper versions and original counters; do not upgrade its frozen runtime mid-run.
- New standalone work may use the compact record format described by `references/standalone-records.md`. Its absence of full skill snapshots is deliberate, not evidence that old work used zero calls.
- Full multi-stage/cross-session work retains full ledger/bundle evidence. A compact task expanding into full work must preserve prior attempts, approvals and caps through the documented standalone continuation path. Never label a newly initialized full ledger as the entire history if earlier attempts exist.
- Maintainer evaluation and bounded skill-improvement procedures move outside installable runtime instructions into `docs/maintainers/evaluation.md`.
- Canonical authoring sources live in `authoring/`; `skills/` remains the generated, independently installable distribution. Run the build and parity check after source changes.

Source preservation, user-versus-delegated authority, technical-versus-visual acceptance, local moving-footprint coverage, native-master continuity and explicit-only exact Aseprite export remain required.

## Bounded compatibility corrections

Compact handoffs now require a fresh export matching the actual included task record, attempts, derived counters, history and captured configuration. Stale checkpoint assembly fails rather than reporting an older budget. Ordinary legacy evidence-only bundles and full same-run bundles remain supported.

A new accepted compact delivery may explicitly `supersedes` an earlier active unaccepted delivery of the same role/native set/semantic pose. All historical decisions and evidence remain; `all_deliveries_accepted` retains its historical meaning while `task_ready` uses active deliveries. Existing records without supersession behave as before.

For a requested static single cel, use the existing refinement-stage identity/master/pose envelope described in `portable-handoff.md`. Real animation-stage handoffs still require a timeline. No project or full-run schema migration, exporter encoder change, budget reset or license change is introduced.

The corrected pre-review build has 190 tests per core package plus 42 exporter tests (992 executions, 232 unique tests), with generated-resource parity. Frozen first-pass results, correction retests and the subsequent independent-review policy evaluation are distinct evidence phases; none rewrites earlier artistic failures.

## Separate independent-review policy

The shared visual-review reference now specifies clean reviewers at completed multi-view sets, hardest animation keys and final animations when available. Routine single stills remain optional, creator review/authority and existing budgets remain required, and unavailable independence or playback stays explicit. The existing visual-review template has an optional additive `checkpoint_review` field; no ledger/project schema or exporter change is required. Prior reports remain valid evidence of what they actually observed, not retroactive independent passes.
