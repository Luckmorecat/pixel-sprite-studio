# Multi-stage and cross-session records

Use the bundled `scripts/run_ledger.py` (Python 3 standard library with POSIX file locking (Linux/macOS/WSL)). Exact stored schemas and complete options are in `run-ledger-interface.md`. It records evidence and budgets; it does not invoke imagegen, choose art, certify quality, or grant permission. For this full continuation path, snapshot the participating runtime packages so later sessions can use the same helper versions. Standalone tasks use `standalone-records.md` instead. Locate every participating installed directory through the catalog/frontmatter first, including all downstream stages needed after a session split. Never assume sibling names. Resolve installed skill, run and evidence directories to canonical real paths before use; symlink roots or parents are intentionally rejected. Use a `--copy` skill install or resolve the actual target of a symlink installation.

## Initialize once, before generation

Save the exact ordinary user request in `request.txt`, then run:

```sh
python3 <this-skill>/scripts/run_ledger.py init run-001 \
  --skill character-identity=<resolved-identity-directory> \
  --skill multi-view-reference=<resolved-views-directory> \
  --skill action-pose-design=<resolved-action-directory> \
  --skill refine-pixel-art=<resolved-refinement-directory> \
  --skill animate-pixel-sprite=<resolved-animation-directory> \
  --request-file request.txt --project sprite-project \
  --max-attempts 24 --max-new-poses 24 --max-stage-repairs 6 --max-pose-repairs 2 --max-total-repairs 6
```

The parent directory must exist; the run path must not exist. Counts above are full-flow defaults only: use any tighter user cap. Snapshot only participating skills; optional unused stages are not required. Always supply stable distinct `--pose` IDs for candidate/master/animation calls (for example `identity-a`, `master`, `page-lift`) so the new-pose cap applies; the global attempt cap also counts pose-less calls. Stage-specific stricter caps in the project contract still apply, even if a generic helper cap is higher.

Outputs: `run.json` with exact request, budgets and each skill's per-file hashes/aggregate version identity; `snapshots/<label>/` with read-only copies; append-only `events.jsonl`; read-only copied input/output evidence under `evidence/`. Snapshots include scripts, references, assets and VERSION. Local permissions plus hashes are tamper-evident evidence, not cryptographic authentication or a storage lock against the owner. Preserve this directory unchanged after finalization and record the reported terminal hash in the delivery record.

## Record every generation attempt

Create a UTF-8 prompt file and JSON file containing exact actual tool arguments (except secrets; prompt may also be in its own file). Inspect edit targets as required by the imagegen tool. Before calling it:

```sh
python3 <frozen-skill>/scripts/run_ledger.py generation-start run-001 \
  --stage animation --pose page-lift --tool ACTUAL_IMAGE_TOOL_NAME \
  --prompt-file prompts/page-lift.txt --parameters-file prompts/page-lift-args.json \
  --reference primary-native-master=references/master-8x.png --reference accepted-neighbor=references/rest-8x.png
```

Use the returned `attempt_id` and artifact namespace. Only invoke imagegen if this command succeeded. Preserve returned original bytes in a fresh source path containing that exact attempt ID before generation-end, such as sources/attempt-0001/original.png. Use candidates/attempt-0001/native.png for its conversion; every repair receives a new namespace. Never rename a rejected source and reuse its old path. It captures exact prompt text, parameters, references with role/path/hash, start time and budget usage. Log tool call arguments faithfully; do not substitute a paraphrased "prompt summary." Preserve every returned original raster before conversion. New CLI runs reject nameless/reused original paths. Normalize new sources with --run RUN --attempt-id ATTEMPT to bind the source hash and candidate name to that attempt.

```sh
python3 <frozen-skill>/scripts/run_ledger.py generation-end run-001 \
  --attempt attempt-0001 --outcome success --output original=sources/attempt-0001/original.png
```

Optional `--response-file` captures a sanitized tool response, never base64-heavy or credential-bearing data unnecessarily. PNG/GIF header dimensions are measured; use `--dimensions role=WIDTHxHEIGHT` for a supported supplied measurement of other formats. Failure/cancellation uses `--outcome failed` or `cancelled` and `--error` with the actual nonsecret blocker. Failed calls still consume budget. If a call never returns, preserve the incomplete attempt; do not call it a success.

Repairs add `--repair-of attempt-0001`, keep matching stage/pose, state the failed observable criterion in the new exact prompt, and retain earlier evidence. Global attempt, new-pose, stage-repair, total-repair and per-pose-repair caps are checked before the call. With max-total-repairs configured, reuse the same semantic pose ID across stages so its cumulative repair limit cannot reset at a stage boundary. A blocked attempt is recorded and must not be followed by generation. Changing a pose ID to evade a cap is not permitted.

## Decisions, operations, checks and failures

Save a JSON object describing the actual event, then:

```sh
python3 <frozen-skill>/scripts/run_ledger.py event run-001 --type decision --data-file decisions/plan.json
python3 <frozen-skill>/scripts/run_ledger.py event run-001 --type check --data-file checks/package.json \
  --artifact manifest=exports/loop-v1/manifest.json --artifact qa=exports/loop-v1/qa.json
python3 <frozen-skill>/scripts/run_ledger.py event run-001 --type review --data-file reviews/visual.json
python3 <frozen-skill>/scripts/run_ledger.py event run-001 --type failure --data-file failures/pose.json
```

Each JSON should contain `stage`, `operation`, relevant exact command/tool arguments, input/output paths and SHA-256 hashes, rationale, observed results, start/end or durations, status, and limitations as applicable. Use repeated `--artifact role=path` to preserve immutable copies of derived PNGs, normalization/assembly sidecars, plans, QA output, playback evidence and other relevant files. Include selected/rejected candidate IDs, approval/delegation evidence, native crop/palette/alpha settings, alignment and masks, semantic pose plan, exact old/new timeline timings, failed QA output, playback observation method and defects. Attach normalization/assembly sidecar facts and package QA content to these records, not just "passed." The helper accepts JSON but cannot prove these statements were true; they must match actual execution. Do not include hidden reasoning, credentials, private unrelated context, or secrets.

```sh
python3 <frozen-skill>/scripts/run_ledger.py verify run-001
python3 <frozen-skill>/scripts/run_ledger.py finalize run-001 --status incomplete \
  --summary 'Core package produced; page motion failed native-size review.'
python3 <frozen-skill>/scripts/run_ledger.py verify run-001
```

Use `succeeded`, `failed`, or `incomplete` honestly. Keep detailed technical/visual statuses in the project/review. `verify` checks chain continuity, snapshot inventory/hashes, captured evidence and missing generation completions; a pass is integrity only. Finalization prevents further helper events. It does not delete failed artifacts. Reports should preserve the exact terminal event hash and version identities.

## Continue in a fresh session

Before the boundary, create/check the self-contained artifact bundle with its complete open `run_directory`. Copy the bundle and use only the copied assets/project and `run/` paths afterward. Inspect the copied run and continue it, including its original frozen snapshots and remaining counters; do not initialize a fresh allowance. Run metadata may record original paths for provenance, but operative snapshot/evidence references are run-relative. Read assets/approvals/readiness and the ordinary next task from the bundle rather than relying on history. Keep earlier bundle versions unchanged as checkpoint evidence; use a fresh copy for continuation.

Do not finalize the ledger at the identity/views session boundary when work will continue. A finalized run is terminal. If an interrupted session cannot safely continue, preserve it and carry its used counters and source/version evidence into an explicitly documented continuation; never represent prior calls as zero. The normal planned split uses the same open portable run.

## Historical source resolution

```sh
python3 <frozen-skill>/scripts/run_ledger.py resolve RUN \
  --sha256 <recorded-source-sha256> --source-path <historical-source-file>
```

The command checks ledger integrity, locates matching immutable evidence by hash and reports whether the old path still matches. It does not repair or rewrite history. A missing/reused original path must not silently resolve to current bytes. Keep old normalization/assembly sidecars unchanged and record the chosen content-addressed resolution in a new check event. After relocating a bundle, resolve against its copied run; original absolute paths need not exist.
