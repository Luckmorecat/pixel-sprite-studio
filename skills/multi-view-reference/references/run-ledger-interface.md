# Run ledger: interface and evidence contract

`run_ledger.py` uses Python 3's standard library on Linux/macOS (POSIX `flock`). It records evidence; it does **not** invoke a generator, edit art, decide visual quality, or certify that the caller reported events honestly. Hash chains detect changes relative to their stored hashes; they are not signatures against an attacker rewriting the whole run. Save the returned chain-tip hash outside the run if independent anchoring is needed; otherwise deletion of complete trailing events cannot be detected from the remaining chain alone.

## Required operating sequence

1. Create one **new, nonexistent** run directory before any generation. Snapshot all participating skills, including their complete resources and scripts, in this single run. Supply the actual user request, not an expanded generation prompt. Skill source directories must not be edited during initialization.
2. Read/use the pinned `RUN/snapshots/LABEL/` skills throughout this trial. Invoke scripts explicitly using `python3` or `bash`; snapshots are read-only. A later source edit does not change this run's pinned version.
3. Record each actual planning decision, chosen candidate/pose, actual check result, failure, and review. Attach logs, manifests and screenshots when applicable. A `check` event must report the check performed and measured results, not just an intention to check.
4. Immediately **before every external generation call**, record `generation-start`. Proceed only if it returns exit 0 and an attempt ID. Use the exact prompt, all tool arguments, and every supplied reference. Start records reserve budget, including calls subsequently failing, cancelled, or lacking a returned result. Never launch the call first and backfill a start record.
5. After the call returns, record `generation-end` for that attempt. Copy the **original returned files**, before cleanup/resizing/assembly, using `--output`. Record a failed/cancelled outcome and a redacted error when the call fails. Include raw, secret-free tool response metadata with `--response-file` if available.
6. Record derived artifacts and their checks separately using `event --artifact`. Do not relabel a derived export as an original generator output.
7. `finalize` once with the actual result: `succeeded`, `failed`, or `incomplete`. Failed attempts and checks remain in the event history even if a later bounded repair succeeds. An interrupted call can remain missing only in a failed/incomplete run.
8. `verify` checks the evidence. A clean validation trial, changed skill snapshot, corrupt event chain, or changed budget requires a **separate newly initialized run**. Do not modify or remove prior evidence to turn a failed trial into a clean one. Link the earlier run ID and changed version hashes in a new run's `decision` event.

## Budgets and pose semantics

The four legacy nonnegative integer limits are mandatory at init and immutable within the run. Version 4 adds `--max-total-repairs`; always supply it for new workflow runs:

- `max_attempts`: every recorded generation-start across the entire run, including initial concepts, new poses, repairs, failures, cancellations, and still-pending calls
- `max_new_poses`: number of distinct `(stage, pose)` pairs introduced by initial attempts across the run; reference reuse and deterministic assembly do not spend this generation budget
- `max_stage_repairs`: number of repair calls in each named stage, across its poses
- `max_total_repairs` (v4): maximum repair calls across every stage and pose; failed repairs count
- `max_pose_repairs`: number of repair calls for a semantic pose across stages when max_total_repairs is supplied; legacy runs retain the `(stage, pose)` rule

Use `--pose POSE` whenever generating an intended animation pose. Stage/pose pairs must remain stable: do not rename the same pose or stage to evade a cap. This simple interface supports one intended pose per call; do not batch multiple new poses under one pose ID. Different candidate renderings of that same intended pose are targeted repairs after its first stage attempt. Pose-less concept candidates can have repeated initial calls in the same stage; they consume global attempts, not repair slots or new-pose slots.

A targeted repair **must** use `--repair-of ATTEMPT`, matching that attempt's stage and pose (including null). The linked attempt must already be completed. Repairs of pose-less concept candidates spend stage repair budget but have no per-pose budget. With v4 total-repair accounting, the same semantic pose retains its per-pose repair counter across stages. A first call with the same pose name at another stage is another distinct `(stage, pose)` entry and spends a new-pose slot. A subsequent call for the same stage/pose must name `--repair-of`. Repair failures still spend all applicable limits. Budget denial appends `generation-blocked` and exits 2; it does not authorize a generator call or spend another attempt.

Limits are per run. If a project authorizes several trials under one total project cap, reserve each run's allowance in that project plan first; this helper does not silently grant a fresh overall project allowance.

## CLI

New CLI init runs enable artifact_policy.attempt_unique_paths. generation-end original outputs must contain their exact attempt ID as a directory or filename prefix and may not reuse an earlier output path. The Python init_run API retains an optional immutable_attempt_paths parameter for compatibility; new workflows must pass True.

Example caps below are illustrative. In a real project, pass exactly its max_calls, max_total_repairs and repairs_per_pose; a portable continuation rejects a ledger/config budget mismatch.

Each command prints one JSON result. Exit 0 means the command succeeded. `verify` returns 1 for integrity errors or missing generation completions. Invalid arguments, malformed evidence, corrupt chains/manifests, exceeded budgets and denied writes return 2 with a non-secret JSON error on stderr. A valid, fully recorded run with status `failed` can pass integrity verification: integrity is not quality or task success.

```sh
python3 run_ledger.py init /absolute/new-run \
  --project reading-animation \
  --skill design=/absolute/design-skill \
  --skill refinement=/absolute/refinement-skill \
  --skill animation=/absolute/animation-skill \
  --request-file /absolute/user-request.txt \
  --max-attempts 12 --max-new-poses 4 \
  --max-stage-repairs 3 --max-pose-repairs 1 --max-total-repairs 3

python3 /absolute/new-run/snapshots/animation/scripts/run_ledger.py generation-start /absolute/new-run \
  --stage animation --pose page-turn \
  --tool ACTUAL_IMAGE_TOOL_NAME \
  --prompt-file /absolute/exact-prompt.txt \
  --parameters-file /absolute/exact-tool-arguments.json \
  --reference approved-master=/absolute/master.png \
  --reference previous-pose=/absolute/previous-pose.png
# Only after success: invoke the tool exactly once. Example returned ID: attempt-0001.

python3 run_ledger.py generation-end /absolute/new-run \
  --attempt attempt-0001 --outcome success \
  --output original-1=/absolute/sources/attempt-0001/tool-original.png \
  --response-file /absolute/tool-response.json

python3 run_ledger.py generation-start /absolute/new-run \
  --stage animation --pose page-turn --repair-of attempt-0001 \
  --tool ACTUAL_IMAGE_TOOL_NAME --prompt-file /absolute/repair-prompt.txt \
  --parameters-file /absolute/repair-arguments.json \
  --reference approved-master=/absolute/master.png

python3 run_ledger.py generation-end /absolute/new-run \
  --attempt attempt-0002 --outcome failed --error 'Tool returned a rendering error'

python3 run_ledger.py event /absolute/new-run \
  --type check --data-file /absolute/check-result.json \
  --artifact check-log=/absolute/check.log \
  --artifact playback=/absolute/playback.gif

python3 run_ledger.py finalize /absolute/new-run \
  --status incomplete --summary 'Reading loop assembled; page-turn quality remains unresolved'
python3 run_ledger.py verify /absolute/new-run
```

- `--skill LABEL=DIR`, `--reference ROLE=PATH`, `--output ROLE=PATH`, and `--artifact ROLE=PATH` can repeat
- `generation-end --dimensions ROLE=WIDTHxHEIGHT` optionally records dimensions for formats without built-in header support. PNG/GIF dimensions are read from headers automatically; supplied sizes must match these headers. Header dimensions are metadata, **not** an image validity check
- `generation-end --outcome` is `success`, `failed`, or `cancelled`. Non-success outcomes require `--error`; partial original outputs can still be attached
- `event --type` is `decision`, `check`, `failure`, or `review`; `--data-file` must be a nonempty JSON object. Include actual measurements, commands, exit statuses, selected artifact IDs, assumptions, reasoning summaries, and timestamps where relevant. Never include private chain-of-thought
- `finalize --summary` is required and must honestly state the achieved result and unresolved issues
- Labels are 1–96 ASCII letters/digits/underscore/dot/hyphen and must begin with a letter/digit

## Stored schema (`pixel-run-ledger/v1`)

`run.json` is a read-only JSON object:

```json
{
  "schema": "pixel-run-ledger/v1",
  "run_id": "UUID hex",
  "project": "project-label",
  "created_at": "UTC ISO timestamp",
  "user_request": "exact UTF-8 request including whitespace",
  "request_file": {"role": "user-request", "source_path": "/original/path", "path": "evidence/UUID/file.txt", "sha256": "hex", "bytes": 42},
  "budgets": {"max_attempts": 12, "max_new_poses": 4, "max_stage_repairs": 3, "max_pose_repairs": 1},
  "skills": [{
    "label": "animation", "source_path": "/original/skill", "snapshot_path": "snapshots/animation",
    "version_sha256": "content identity", "directories": ["scripts"],
    "files": [{"relative_path": "SKILL.md", "path": "snapshots/animation/SKILL.md", "sha256": "hex", "bytes": 42}]
  }]
}
```

`events.jsonl` is append-only, one canonical JSON object per line:

```json
{
  "seq": 2,
  "time": "UTC ISO timestamp",
  "type": "generation-start",
  "previous_hash": "previous event SHA256; 64 zeros on first event",
  "data": {},
  "hash": "SHA256 of this event without its hash field"
}
```

Canonical encoding: UTF-8 JSON, sorted keys, separators `,` and `:`, Unicode unescaped, no NaN/Infinity. Event hashes exclude the terminal newline. The initialization event pins the SHA256 of the exact `run.json` bytes (including its newline). Skill version identity hashes the ordered list of `{relative_path, sha256, bytes}` objects; directory inventory is additionally pinned by the manifest. Unix modes, ownership and mtime are not part of file-content identity.

Event payloads:

- `run-initialized`: manifest SHA256 and run ID
- `generation-start`: `attempt_id`, `stage`, nullable `pose`, nullable `repair_of`, `kind` (`initial`, `new-pose`, `repair`), `tool`, exact `prompt`, copied `prompt_file`, parsed `parameters`, copied `parameters_file`, copied `references`
- `generation-end`: matching `attempt_id`, `start_event_hash`, `outcome`, nullable `error`, `finished_at`, `elapsed_seconds`, copied `outputs`, optional copied `response_file`. Elapsed time is wall-clock time from the start record through completion recording and includes operator/tool overhead
- `generation-blocked`: stage, pose, repair link, reason and attempted-call count
- `decision` / `check` / `failure` / `review`: `details` (the supplied object), `artifacts` (copied files)
- `run-finalized`: final status, summary, attempted-call count, missing completion IDs

Every copied artifact carries role, original absolute source path, run-relative copy path, byte count and SHA256. Image artifacts can additionally carry `dimensions: [width, height]` and `dimensions_source: header|supplied|supplied_and_header`. Copies use fresh UUID directories and exclusive file creation, never overwrite original files, and become read-only. The `.lock` file serializes writer operations; it is operational state, not evidence.

`verify` returns `integrity_ok`, errors, final/open status, attempted generation count, missing completion IDs and the current chain-tip hash. It validates the entire event chain, manifest hash, snapshot inventory, copied artifacts and recorded hashes. It does not rerun artistic/technical QA, compare later installed skill files with the pinned copy, or prove an external tool call actually used the recorded arguments. If interrupted before an event could be appended, an unreferenced copy may remain; retain it as partial evidence rather than cleaning the run.

## Privacy and recovery

Only explicitly supplied files are read. Environment variables, credential stores and account state are never collected. Do not supply credentials, private keys, tokens, secret-bearing URLs, or sensitive unrelated data. Common secret filenames, credential JSON fields and recognizable token/private-key forms are rejected; this is defense in depth, **not** a complete secret detector. Redact sensitive tool-error/response fields before recording and say in the associated event which fields were redacted. Image/binary evidence must also be safe to retain.

Symlinks and special files are rejected in snapshots; supplied evidence must be a regular non-symlink file. An initialization error leaves `INITIALIZATION_FAILED.txt` and any already copied safe files in place. Never reinitialize that directory. Do not patch a damaged JSONL tail: preserve the damaged run, start a new one, and cite the interruption. Finalization is permanent; no event can be appended afterward.

Tests: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_run_ledger.py` from the scripts directory. Tests use synthetic data/header bytes only and make no art-generation or network calls.


## Hash-based replay

`resolve RUN --sha256 HASH [--source-path OLD_PATH]` is read-only. It verifies the existing run and returns a matching immutable evidence path plus all matches, its exact hash and the historical path status. Unknown hashes or corrupt evidence reject. Reused/missing original paths are diagnostic, never resolution authority. `verify_attempt_source(run, attempt, source, output)` validates normalization against the captured generation output and both attempt-scoped paths; prepare_pixels.sh exposes it through paired --run/--attempt-id options.
