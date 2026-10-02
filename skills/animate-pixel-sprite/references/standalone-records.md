# Standalone task record

Use for one bounded task without an existing run. No skill snapshots, full ledger, portable bundle or improvement trial are required. Existing ledger projects must continue their full path and counters; never downgrade them or initialize another allowance. This helper records evidence and reuses bundled safety/counter functions without calling imagegen.

## Initialize

Work outside installed skills. Save the exact ordinary request in `request.txt`. Create a minimal real `profile.json` containing relevant pixel style, identity/shape, palette roles and view. Existing project schema `3.0` and pipeline inputs remain unchanged. Replace these illustrative values with actual requirements and a small planned allowance:

```json
{"schema_version":"3.0","asset_id":"requested-study","brief":"Exact actual request",
 "profile":"profile.json","native_canvas_px":[64,64],
 "limits":{"palette_max":16,"binary_alpha":true,"min_margin":1},
 "budget":{"max_calls":2,"max_total_repairs":1,"repairs_per_pose":1}}
```

For static work omit `animation` entirely. Omit unmeasured anchors. All three budget caps above are required; use smaller/zero caps when appropriate, not an inherited 24-call allowance. Additional project stage allocations still constrain planning.

```sh
python3 <skill>/scripts/standalone_record.py init task \
  --project project.json --request-file request.txt
# Supplied input: add --source supplied-master=original.png
```

`task` must not exist. Exact configuration/profile bytes land in `task/config/`, unique read-only evidence in `task/evidence/`, and the compact record in `task/task.json`. Imported sources have unknown prior generation usage and no invented approval. Counters cover this task only; importing older work never erases known calls.

## Calls and repairs

Save exact prompt text and actual secret-free tool arguments. Inspect edit inputs first. Include roles/hashes for the actual reference files supplied:

```sh
python3 <skill>/scripts/standalone_record.py start task \
  --stage identity --pose neutral --tool ACTUAL_IMAGE_TOOL_NAME \
  --prompt-file prompt.txt --parameters-file arguments.json \
  --reference identity=input.png
```

Omit references when absent. Only generate after successful start. It reserves/counts `attempt-0001` and returns its unique source directory. Create that directory; copy every returned original there unchanged, retaining the tool-returned files too:

```sh
python3 <skill>/scripts/standalone_record.py end task \
  --attempt attempt-0001 --outcome success \
  --output original=task/sources/attempt-0001/original.png
```

Failures use `--outcome failed --error 'Actual nonsecret error'`; cancellations use `cancelled`. Unfinished calls remain `pending`. All starts count. Repairs use `start ... --repair-of attempt-0001` with matching stage/semantic pose; repair caps remain cumulative across stages. IDs, links and counters are validated, never manually trusted. Do not reuse source names or relabel poses to evade caps.

## Normalize and deliver

`end` reports preserved output paths/hashes. Normalize that preserved output or imported input:

```sh
<skill>/scripts/prepare_pixels.sh --project task/config/project.json \
  --input PRESERVED_SOURCE --output candidates/attempt-0001/native.png
```

Do not pass `--run`/`--attempt-id`: those flags require a full ledger. Preserve conversion sidecars and inspect native-size/enlarged results. Deterministic-only work needs no invented generation attempt.

Copy `assets/standalone-record.template.json` to `delivery.json`; its paths are relative to that file. It is a delivery spec, not a replacement for generated `task.json`. Fill artifact/source paths, role, separate technical/visual statuses, review, provenance and limitations:

```sh
python3 <skill>/scripts/standalone_record.py deliver task --spec-file delivery.json
python3 <skill>/scripts/standalone_record.py check task
```

`accepted` requires technical `passed`, visual `accepted`, and approval containing `actor` (`user`/`assistant`), `role`, exact `asset_sha256`/`source_sha256`, `scope`, `reason`, and `evidence_file`. Assistant acceptance also requires `delegation_file` quoting actual current delegation. Never invent user approval of unseen pixels. Unaccepted deliveries have null approval. Decisions append under unique IDs. To replace an already recorded study/rejection, add `"supersedes":"earlier-delivery-id"` to a new accepted delivery spec. The earlier delivery must be unaccepted, not already superseded, and have the same role and applicable native set/semantic pose. Its evidence remains unchanged; replacement still needs its own valid authority and all acceptance gates. Keep other rejected candidates in attempts/reviews rather than final deliveries.

For `native_master`/`pose`, provide `set_id` and the native contract from `portable-handoff.md`: `native.grid_px:1`, measured `anchor_px`, shared hex `palette`, and `grid` with `source_canvas_px`/`crop`. Poses additionally name `pose_id` and earlier `master_id`. Real PNG decoding via ImageMagick enforces canvas/palette/alpha/margin/grid/anchor and set consistency; accepted poses require accepted masters.

`check` validates current evidence, recorded gates and derived counters. `task_ready` means all active deliveries are accepted with no pending calls; explicit supersession removes only the earlier study from active scope. `all_deliveries_accepted` still describes the entire preserved history, not proven artistic quality or truthful authority. Original dimensions are header-only. This editable local record is not authenticated history. Preserve the whole directory; don't rewrite attempts. Deliver the requested result with honest status/limits, adding its record archive when useful.

## Upgrade to a portable handoff

```sh
python3 <skill>/scripts/standalone_record.py budget-evidence task budget-evidence-v1.json
```

Use normal `artifact_bundle.py` creation/checking from `portable-handoff.md`: set `project` to `task/config/project.json`, `budget_evidence_file` to the export, supply required assets/reviews/authority, and include request support plus `{"directory":"task","role":"provenance"}`. Paths are bundle-spec-relative. The result is `evidence_only`, never `same_run`; exported attempts preserve failures, pending work, repairs, source-record hash and unknown imported history.

Bundle creation/checking cross-checks the export against exactly one included compact task checkpoint: actual record validity, hash, attempts, counters, history and captured project/profile. A stale export fails; export again to a new filename after any record change. This detects local inconsistency, not authenticated history.

Resume by copying `support-trees/task/` out of the immutable bundle checkpoint. Continue the same record/config/counters and export a fresh budget file/new bundle afterward. Never edit the old bundle, substitute empty attempts, or initialize a fresh original allowance. Uncaptured historical skill snapshots cannot be invented. Existing full ledgers retain `same_run` continuation.
