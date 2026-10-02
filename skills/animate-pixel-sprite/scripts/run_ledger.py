#!/usr/bin/env python3
"""Append-only, bounded pixel-workflow run evidence. Python standard library only.

This tool NEVER calls a generator. Record generation-start before the call and
use its attempt_id at generation-end. Caller must supply accurate, secret-free
inputs; common credential forms are rejected, but no scanner finds every secret.
See ../references/run-records.md. Local hash chains are tamper-evident, not signed.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
import uuid

SCHEMA = "pixel-run-ledger/v1"
ZERO_HASH = "0" * 64
LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
SECRET_KEYS = {"password", "passwd", "api_key", "apikey", "access_token", "refresh_token",
               "client_secret", "authorization", "private_key", "secret_access_key"}
SECRET_TEXT = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})\b|"
    r"(?im:^\s*(?:api[_-]?key|password|passwd|access[_-]?token|client[_-]?secret)"
    r"\s*[:=]\s*[\"']?[^\s\"']{8,})"
)
SECRET_NAMES = {"credentials", "credentials.json", "id_rsa", "id_ed25519", ".netrc", ".npmrc"}


class LedgerError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe(value):
    """Reject common credential fields/values, without logging the offending value."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower().replace("-", "_") in SECRET_KEYS and item not in (None, "", False):
                raise LedgerError("Credential-like field rejected; redact before recording")
            safe(item)
    elif isinstance(value, list):
        for item in value:
            safe(item)
    elif isinstance(value, str) and SECRET_TEXT.search(value):
        raise LedgerError("Credential-like content rejected; redact before recording")
    canonical(value)  # rejects NaN and non-JSON values
    return value


def label(value):
    if not LABEL.fullmatch(value):
        raise LedgerError("Labels must be 1-96 ASCII letters/digits/underscore/dot/hyphen")
    return value


def read_bytes(path):
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_file():
        raise LedgerError("Evidence must be an existing regular, non-symlink file")
    if any(p.is_symlink() for p in path.parents):
        raise LedgerError("Evidence paths must not contain symlinks")
    if path.name in SECRET_NAMES or path.name == ".env" or path.name.startswith(".env."):
        raise LedgerError("Potential credential file rejected")
    data = path.read_bytes()
    try:
        decoded = data.decode("utf-8")
        safe(decoded)
        try:
            parsed = json.loads(decoded)
        except (ValueError, TypeError):
            pass
        else:
            safe(parsed)
    except UnicodeDecodeError:
        pass
    return data


def read_json(path):
    return safe(json.loads(read_bytes(path)))


def new_file(path, data, readonly=True):
    path = Path(path)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if readonly:
        path.chmod(0o444)


def dimensions(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24 and data[12:16] == b"IHDR":
        return list(struct.unpack(">II", data[16:24]))
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return list(struct.unpack("<HH", data[6:10]))
    return None


def capture(run, source, role, supplied_dimensions=None, data=None):
    label(role)
    source = Path(source).absolute()
    if data is None:
        data = read_bytes(source)
    measured = dimensions(data)
    if supplied_dimensions is not None:
        if len(supplied_dimensions) != 2 or any(type(x) is not int or x <= 0 for x in supplied_dimensions):
            raise LedgerError("Dimensions must be two positive integers")
        if measured and measured != supplied_dimensions:
            raise LedgerError("Supplied dimensions disagree with PNG/GIF header")
    folder = run / "evidence" / uuid.uuid4().hex
    folder.mkdir()
    dest = folder / source.name
    new_file(dest, data)
    folder.chmod(0o555)
    entry = {"role": role, "source_path": str(source), "path": dest.relative_to(run).as_posix(),
             "sha256": digest(data), "bytes": len(data)}
    if supplied_dimensions is not None:
        entry["dimensions"] = supplied_dimensions
        entry["dimensions_source"] = "supplied_and_header" if measured else "supplied"
    elif measured:
        entry["dimensions"] = measured
        entry["dimensions_source"] = "header"
    return entry


def event_hash(event):
    return digest(canonical({k: v for k, v in event.items() if k != "hash"}))


def load_events(run):
    events, previous = [], ZERO_HASH
    data = (run / "events.jsonl").read_bytes()
    if data and not data.endswith(b"\n"):
        raise LedgerError("Incomplete event tail; preserve run and start a new run")
    for seq, line in enumerate(data.splitlines(), 1):
        event = json.loads(line)
        if event.get("seq") != seq or event.get("previous_hash") != previous or event.get("hash") != event_hash(event):
            raise LedgerError("Event hash chain mismatch at sequence " + str(seq))
        previous = event["hash"]
        events.append(event)
    return events


def append(run, events, event_type, data):
    safe(data)
    event = {"seq": len(events) + 1, "time": now(), "type": event_type,
             "previous_hash": events[-1]["hash"] if events else ZERO_HASH, "data": data}
    event["hash"] = event_hash(event)
    with (run / "events.jsonl").open("ab") as stream:
        stream.write(canonical(event) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    events.append(event)
    return event


def resolve_inside(run, relative):
    path = run / relative
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise LedgerError("Unsafe stored evidence path")
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise LedgerError("Stored evidence must not contain symlinks")
    return path


def evidence_records(manifest, events):
    """Only schema-owned artifact fields are paths; arbitrary tool/check JSON is not."""
    yield manifest["request_file"]
    for skill in manifest["skills"]:
        yield from skill["files"]
    for event in events:
        data = event["data"]
        if event["type"] == "generation-start":
            yield data["prompt_file"]
            yield data["parameters_file"]
            yield from data["references"]
        elif event["type"] == "generation-end":
            yield from data["outputs"]
            if data.get("response_file"):
                yield data["response_file"]
        elif event["type"] in ("decision", "check", "failure", "review"):
            yield from data["artifacts"]


def inspect(run):
    """Check chain, manifest, exact snapshot inventory, and recorded evidence."""
    run = Path(run).absolute()
    if run.is_symlink() or not run.is_dir():
        raise LedgerError("Run must be an existing non-symlink directory")
    manifest_bytes = (run / "run.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    events = load_events(run)
    if not events or events[0]["type"] != "run-initialized" or events[0]["data"].get("manifest_sha256") != digest(manifest_bytes):
        raise LedgerError("Missing initialization or changed run manifest")
    if manifest.get("schema") != SCHEMA:
        raise LedgerError("Unsupported run manifest schema")
    errors = []
    seen = set()
    for entry in evidence_records(manifest, events):
        path = resolve_inside(run, entry["path"])
        if entry["path"] in seen:
            continue
        seen.add(entry["path"])
        if not path.is_file():
            errors.append("Missing evidence: " + entry["path"])
            continue
        data = path.read_bytes()
        if len(data) != entry["bytes"] or digest(data) != entry["sha256"]:
            errors.append("Changed evidence: " + entry["path"])
    for skill in manifest["skills"]:
        root = resolve_inside(run, skill["snapshot_path"])
        expected = {entry["relative_path"] for entry in skill["files"]}
        actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() or p.is_symlink()}
        if actual != expected:
            errors.append("Changed snapshot inventory: " + skill["label"])
        actual_dirs = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir()}
        if actual_dirs != set(skill["directories"]):
            errors.append("Changed snapshot directory inventory: " + skill["label"])
        identity = digest(canonical([{k: v for k, v in e.items() if k in ("relative_path", "sha256", "bytes")}
                                     for e in skill["files"]]))
        if identity != skill["version_sha256"]:
            errors.append("Invalid snapshot identity: " + skill["label"])
    starts = {e["data"]["attempt_id"]: e for e in events if e["type"] == "generation-start"}
    completions = [e["data"]["attempt_id"] for e in events if e["type"] == "generation-end"]
    if len(completions) != len(set(completions)) or any(x not in starts for x in completions):
        errors.append("Duplicate or unmatched generation completion")
    if manifest.get("artifact_policy", {}).get("attempt_unique_paths"):
        original_paths = set()
        for event in events:
            if event["type"] != "generation-end":
                continue
            for record in event["data"]["outputs"]:
                try:
                    require_attempt_path(record["source_path"], event["data"]["attempt_id"])
                except (LedgerError, KeyError):
                    errors.append("Invalid attempt-scoped original path")
                canonical_source = os.path.abspath(record["source_path"])
                if canonical_source in original_paths:
                    errors.append("Reused original output path")
                original_paths.add(canonical_source)
    missing = [key for key in starts if key not in completions]
    finalized = [e for e in events if e["type"] == "run-finalized"]
    if len(finalized) > 1 or (finalized and finalized[-1] != events[-1]):
        errors.append("Events recorded after finalization")
    status = finalized[-1]["data"]["status"] if finalized else "open"
    return manifest, events, {"schema": SCHEMA, "run_id": manifest["run_id"], "integrity_ok": not errors,
                             "errors": errors, "status": status, "attempted_generation_calls": len(starts),
                             "missing_generation_completions": missing, "last_event_hash": events[-1]["hash"]}


@contextmanager
def writable(run):
    run = Path(run).absolute()
    if not run.is_dir() or run.is_symlink():
        raise LedgerError("Run does not exist or is a symlink")
    with (run / ".lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest, events, report = inspect(run)
        if not report["integrity_ok"]:
            raise LedgerError("Run integrity failed: " + "; ".join(report["errors"]))
        if report["status"] != "open":
            raise LedgerError("Run already finalized; use a new run")
        yield run, manifest, events, report


def init_run(run, skills, request_file, budgets, project="pixel-workflow", immutable_attempt_paths=False):
    run = Path(run).absolute()
    label(project)
    required = {"max_attempts", "max_new_poses", "max_stage_repairs", "max_pose_repairs"}
    if not required <= set(budgets) or set(budgets) - required - {"max_total_repairs"} or any(type(x) is not int or x < 0 for x in budgets.values()):
        raise LedgerError("Supply all four nonnegative integer budgets; max_total_repairs is optional")
    if not skills:
        raise LedgerError("At least one exact skill directory is required")
    sources = []
    labels = set()
    for name, source in skills:
        label(name)
        source = Path(source).absolute()
        if name in labels or source.is_symlink() or not source.is_dir():
            raise LedgerError("Skill labels must be unique and sources must be real directories")
        if source == run or source in run.parents:
            raise LedgerError("Run directory cannot be inside a snapshotted skill")
        labels.add(name)
        sources.append((name, source))
    request_bytes = read_bytes(request_file)
    request = request_bytes.decode("utf-8")
    run.mkdir(parents=False, exist_ok=False)  # never reuse even an empty run
    (run / "snapshots").mkdir()
    (run / "evidence").mkdir()
    snapshots = []
    try:
        for name, source in sources:
            dest = run / "snapshots" / name
            dest.mkdir()
            files, directories = [], []
            for path in sorted(source.rglob("*")):
                relative = path.relative_to(source)
                target = dest / relative
                if path.is_symlink():
                    raise LedgerError("Skill snapshots reject symlinks")
                if path.is_dir():
                    target.mkdir()
                    directories.append(relative.as_posix())
                elif path.is_file():
                    data = read_bytes(path)
                    new_file(target, data)
                    files.append({"relative_path": relative.as_posix(), "path": target.relative_to(run).as_posix(),
                                  "sha256": digest(data), "bytes": len(data)})
                else:
                    raise LedgerError("Skill snapshots allow only regular files/directories")
            identity = digest(canonical([{k: v for k, v in e.items() if k in ("relative_path", "sha256", "bytes")}
                                         for e in files]))
            for folder in sorted((p for p in dest.rglob("*") if p.is_dir()), reverse=True):
                folder.chmod(0o555)
            dest.chmod(0o555)
            snapshots.append({"label": name, "source_path": str(source), "snapshot_path": dest.relative_to(run).as_posix(),
                              "version_sha256": identity, "files": files, "directories": directories})
        (run / "snapshots").chmod(0o555)
        request_artifact = capture(run, request_file, "user-request", data=request_bytes)
        manifest = {"schema": SCHEMA, "run_id": uuid.uuid4().hex, "project": project, "created_at": now(),
                    "user_request": request, "request_file": request_artifact, "budgets": budgets, "skills": snapshots}
        if immutable_attempt_paths:
            manifest["artifact_policy"] = {"attempt_unique_paths": True, "immutable_originals": True}
        safe(manifest)
        data = canonical(manifest) + b"\n"
        new_file(run / "run.json", data)
        new_file(run / "events.jsonl", b"", readonly=False)
        append(run, [], "run-initialized", {"manifest_sha256": digest(data), "run_id": manifest["run_id"]})
        return {"run": str(run), "run_id": manifest["run_id"], "budgets": budgets,
                "skill_versions": {s["label"]: s["version_sha256"] for s in snapshots}}
    except Exception:
        # Preserve partial initialization rather than erase failure evidence.
        marker = run / "INITIALIZATION_FAILED.txt"
        if not marker.exists():
            new_file(marker, b"Initialization failed. Preserve this directory and choose a fresh run path.\n")
        raise


def generation_start(run, stage, pose, tool, prompt_file, parameters_file, references=(), repair_of=None):
    label(stage)
    if pose is not None:
        label(pose)
    safe(tool)
    if not tool.strip():
        raise LedgerError("Tool name is required")
    prompt_bytes = read_bytes(prompt_file)
    prompt = prompt_bytes.decode("utf-8")
    parameters_bytes = read_bytes(parameters_file)
    parameters = safe(json.loads(parameters_bytes))
    if not isinstance(parameters, dict):
        raise LedgerError("Tool parameters must be a JSON object")
    with writable(run) as (run, manifest, events, report):
        starts = [e["data"] for e in events if e["type"] == "generation-start"]
        budgets = manifest["budgets"]
        reason = None
        if len(starts) >= budgets["max_attempts"]:
            reason = "global_attempt_cap"
        if repair_of:
            original = next((s for s in starts if s["attempt_id"] == repair_of), None)
            if not original or original["stage"] != stage or original["pose"] != pose:
                raise LedgerError("repair-of must name an earlier attempt with the same stage and pose")
            if not any(e["type"] == "generation-end" and e["data"]["attempt_id"] == repair_of for e in events):
                raise LedgerError("Complete the linked attempt before starting its repair")
            repairs = [s for s in starts if s["repair_of"]]
            if "max_total_repairs" in budgets and len(repairs) >= budgets["max_total_repairs"]:
                reason = reason or "total_repair_cap"
            if sum(s["stage"] == stage for s in repairs) >= budgets["max_stage_repairs"]:
                reason = reason or "stage_repair_cap"
            if pose is not None and sum(s["pose"] == pose and ("max_total_repairs" in budgets or s["stage"] == stage) for s in repairs) >= budgets["max_pose_repairs"]:
                reason = reason or "pose_repair_cap"
        elif pose is not None:
            existing = {(s["stage"], s["pose"]) for s in starts if s["pose"] is not None and not s["repair_of"]}
            if any(s["pose"] == pose and s["stage"] == stage for s in starts):
                raise LedgerError("Same stage/pose already attempted; use repair-of for a targeted repair")
            if (stage, pose) not in existing and len(existing) >= budgets["max_new_poses"]:
                reason = reason or "new_pose_cap"
        if reason:
            append(run, events, "generation-blocked", {"stage": stage, "pose": pose, "repair_of": repair_of,
                                                       "reason": reason, "attempted_generation_calls": len(starts)})
            raise LedgerError("Generation blocked: " + reason + "; do not call the generator")
        attempt = "attempt-" + str(len(starts) + 1).zfill(4)
        data = {"attempt_id": attempt, "stage": stage, "pose": pose, "repair_of": repair_of,
                "kind": "repair" if repair_of else ("new-pose" if pose else "initial"), "tool": tool,
                "prompt": prompt, "prompt_file": capture(run, prompt_file, "prompt", data=prompt_bytes),
                "parameters": parameters, "parameters_file": capture(run, parameters_file, "tool-parameters", data=parameters_bytes),
                "references": [capture(run, path, role) for role, path in references]}
        event = append(run, events, "generation-start", data)
        return {"attempt_id": attempt, "event_hash": event["hash"], "started_at": event["time"],
                "attempted_generation_calls": len(starts) + 1, "remaining_attempts": budgets["max_attempts"] - len(starts) - 1,
                "artifact_namespace": attempt,
                "artifact_policy": manifest.get("artifact_policy", {"attempt_unique_paths": False})}


def generation_end(run, attempt, outcome, outputs=(), error=None, output_dimensions=None, response_file=None):
    if outcome not in ("success", "failed", "cancelled"):
        raise LedgerError("Invalid generation outcome")
    if outcome != "success" and not error:
        raise LedgerError("Failed/cancelled calls require a non-secret error description")
    safe(error)
    with writable(run) as (run, manifest, events, report):
        start = next((e for e in events if e["type"] == "generation-start" and e["data"]["attempt_id"] == attempt), None)
        if not start:
            raise LedgerError("Unknown attempt")
        if any(e["type"] == "generation-end" and e["data"]["attempt_id"] == attempt for e in events):
            raise LedgerError("Attempt already completed")
        if manifest.get("artifact_policy", {}).get("attempt_unique_paths"):
            paths = [str(Path(path).resolve(strict=True)) for _, path in outputs]
            if len(set(paths)) != len(paths):
                raise LedgerError("Output path repeated within attempt")
            earlier = {os.path.abspath(record["source_path"]) for event in events if event["type"] == "generation-end"
                       for record in event["data"]["outputs"]}
            for path in paths:
                require_attempt_path(path, attempt)
                if path in earlier:
                    raise LedgerError("Original output path was already used; retain immutable attempt-unique source names")
        finished = now()
        elapsed = (datetime.fromisoformat(finished) - datetime.fromisoformat(start["time"])).total_seconds()
        data = {"attempt_id": attempt, "start_event_hash": start["hash"], "outcome": outcome,
                "error": error, "finished_at": finished, "elapsed_seconds": elapsed,
                "outputs": [capture(run, path, role, (output_dimensions or {}).get(role)) for role, path in outputs]}
        if response_file:
            data["response_file"] = capture(run, response_file, "tool-response")
        return append(run, events, "generation-end", data)


def require_attempt_path(path, attempt):
    if not re.fullmatch(r"attempt-[0-9]{4,}", attempt):
        raise LedgerError("Expected a ledger attempt ID")
    path = Path(os.path.abspath(path))  # lexical normalization; historical originals need not exist
    if attempt not in path.parts and not any(path.name.startswith(attempt + sep) for sep in ("-", "_", ".")):
        raise LedgerError("Artifact path must contain the exact attempt ID as a directory or filename prefix: " + attempt)


def resolve_artifact(run, sha256, source_path=None):
    """Resolve by verified content, never trust a historical path that was reused."""
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise LedgerError("sha256 must be 64 lowercase hex characters")
    run = Path(run).absolute()
    manifest, events, report = inspect(run)
    if not report["integrity_ok"]:
        raise LedgerError("Cannot resolve from corrupt run evidence")
    matches = []
    seen = set()
    for record in evidence_records(manifest, events):
        if record["sha256"] == sha256 and record["path"] not in seen:
            seen.add(record["path"])
            actual = resolve_inside(run, record["path"])
            if digest(read_bytes(actual)) != sha256:
                raise LedgerError("Historical evidence hash no longer matches")
            matches.append({"file": str(actual), "run_relative_path": record["path"],
                            "sha256": sha256, "role": record.get("role"),
                            "original_source_path": record.get("source_path")})
    if not matches:
        raise LedgerError("No captured artifact with the requested content hash")
    source_status = "not_checked"
    if source_path:
        try:
            source_status = "hash_matches" if digest(read_bytes(source_path)) == sha256 else "hash_mismatch_reused_or_changed_path"
        except (OSError, LedgerError):
            source_status = "missing_or_unsafe_path"
    return {"resolved_file": matches[0]["file"], "sha256": sha256, "matches": matches,
            "historical_source_status": source_status,
            "resolution": "verified immutable evidence by hash; historical path is advisory only"}


def verify_attempt_source(run, attempt, source, output=None):
    """Bind a new normalization to its actual generation output and unique candidate path."""
    manifest, events, report = inspect(run)
    if not report["integrity_ok"]:
        raise LedgerError("Run integrity failed before normalization")
    ended = next((e for e in events if e["type"] == "generation-end" and e["data"]["attempt_id"] == attempt), None)
    if not ended:
        raise LedgerError("Record generation-end before normalizing its source")
    source_hash = digest(read_bytes(source))
    matches = [r for r in ended["data"]["outputs"] if r["sha256"] == source_hash]
    if not matches:
        raise LedgerError("Normalization source hash does not match that attempt's captured original; resolve historical content by hash")
    captured_paths = {resolve_inside(Path(run).absolute(), record["path"]).resolve() for record in matches}
    if Path(source).resolve() not in captured_paths:
        require_attempt_path(source, attempt)
    if output is not None:
        require_attempt_path(output, attempt)
    return {"attempt_id": attempt, "source_sha256": source_hash,
            "captured_source": matches[0]["path"], "run_id": manifest["run_id"]}


def general_event(run, event_type, data, artifacts=()):
    if event_type not in ("decision", "check", "failure", "review"):
        raise LedgerError("Use decision, check, failure, or review")
    if not isinstance(data, dict) or not data:
        raise LedgerError("Event data must be a nonempty JSON object")
    safe(data)
    with writable(run) as (run, manifest, events, report):
        return append(run, events, event_type, {"details": data,
                                               "artifacts": [capture(run, path, role) for role, path in artifacts]})


def finalize(run, status, summary):
    if status not in ("succeeded", "failed", "incomplete"):
        raise LedgerError("Invalid final status")
    safe(summary)
    with writable(run) as (run, manifest, events, report):
        if status == "succeeded" and report["missing_generation_completions"]:
            raise LedgerError("Cannot mark succeeded with uncompleted generation attempts")
        return append(run, events, "run-finalized", {"status": status, "summary": summary,
                                                    "attempted_generation_calls": report["attempted_generation_calls"],
                                                    "missing_generation_completions": report["missing_generation_completions"]})


def pair(value):
    if "=" not in value:
        raise argparse.ArgumentTypeError("Expected LABEL=PATH")
    name, path = value.split("=", 1)
    if not name or not path:
        raise argparse.ArgumentTypeError("Expected nonempty LABEL=PATH")
    return name, path


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a fresh directory and immutable skill snapshots")
    init.add_argument("run")
    init.add_argument("--skill", action="append", type=pair, required=True)
    init.add_argument("--request-file", required=True)
    init.add_argument("--project", default="pixel-workflow")
    for arg in ("max-attempts", "max-new-poses", "max-stage-repairs", "max-pose-repairs"):
        init.add_argument("--" + arg, type=int, required=True)
    init.add_argument("--max-total-repairs", type=int, help="Cumulative repair cap across all stages; also scopes per-pose repairs across stages")
    start = commands.add_parser("generation-start", help="Reserve/count an attempt BEFORE calling the tool")
    start.add_argument("run")
    for arg in ("stage", "tool", "prompt-file", "parameters-file"):
        start.add_argument("--" + arg, required=True)
    start.add_argument("--pose")
    start.add_argument("--repair-of")
    start.add_argument("--reference", action="append", type=pair, default=[])
    end = commands.add_parser("generation-end", help="Record success, failure, or cancellation without refunding budget")
    end.add_argument("run")
    end.add_argument("--attempt", required=True)
    end.add_argument("--outcome", choices=("success", "failed", "cancelled"), required=True)
    end.add_argument("--output", action="append", type=pair, default=[])
    end.add_argument("--dimensions", action="append", type=pair, default=[], metavar="ROLE=WIDTHxHEIGHT")
    end.add_argument("--error")
    end.add_argument("--response-file")
    event = commands.add_parser("event", help="Append actual decisions, checks, failures, or reviews")
    event.add_argument("run")
    event.add_argument("--type", choices=("decision", "check", "failure", "review"), required=True)
    event.add_argument("--data-file", required=True)
    event.add_argument("--artifact", action="append", type=pair, default=[])
    close = commands.add_parser("finalize", help="Close permanently; failed/incomplete evidence is retained")
    close.add_argument("run")
    close.add_argument("--status", choices=("succeeded", "failed", "incomplete"), required=True)
    close.add_argument("--summary", required=True)
    verify = commands.add_parser("verify", help="Verify chain, snapshot inventory/hashes, evidence and missing completions")
    verify.add_argument("run")
    resolve = commands.add_parser("resolve", help="Resolve a historical artifact from immutable evidence by exact hash")
    resolve.add_argument("run")
    resolve.add_argument("--sha256", required=True)
    resolve.add_argument("--source-path", help="Optionally check an old provenance path without trusting it")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = init_run(args.run, args.skill, args.request_file,
                              {key: getattr(args, key) for key in ("max_attempts", "max_new_poses", "max_stage_repairs", "max_pose_repairs", "max_total_repairs") if getattr(args, key) is not None}, args.project, immutable_attempt_paths=True)
        elif args.command == "generation-start":
            result = generation_start(args.run, args.stage, args.pose, args.tool, args.prompt_file,
                                      args.parameters_file, args.reference, args.repair_of)
        elif args.command == "generation-end":
            dims = {}
            for role, size in args.dimensions:
                if not re.fullmatch(r"[1-9][0-9]*x[1-9][0-9]*", size) or role in dims:
                    raise LedgerError("Dimensions must be unique ROLE=WIDTHxHEIGHT entries")
                dims[role] = [int(x) for x in size.split("x")]
            if set(dims) - {role for role, path in args.output}:
                raise LedgerError("Dimensions supplied for a missing output role")
            result = generation_end(args.run, args.attempt, args.outcome, args.output, args.error, dims, args.response_file)
        elif args.command == "event":
            result = general_event(args.run, args.type, read_json(args.data_file), args.artifact)
        elif args.command == "resolve":
            result = resolve_artifact(args.run, args.sha256, args.source_path)
        elif args.command == "finalize":
            result = finalize(args.run, args.status, args.summary)
        else:
            result = inspect(args.run)[2]
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["integrity_ok"] and not result["missing_generation_completions"] else 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (LedgerError, OSError, ValueError, KeyError, TypeError) as exc:
        # Do not print raw exceptions that might contain file contents/secrets.
        message = str(exc) if isinstance(exc, LedgerError) else "Invalid or unreadable input (" + type(exc).__name__ + ")"
        print(json.dumps({"error": message}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
