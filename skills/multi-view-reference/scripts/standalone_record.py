#!/usr/bin/env python3
"""Compact, portable evidence for one bounded task; never invokes a generator.

No skill snapshots or run ledger are created. Local records are editable evidence,
not authenticated history. Counters are computed from attempts, not supplied totals.
See ../references/standalone-records.md for authority and continuation boundaries.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import uuid

from project_config import load_project, read_json, relative_file
from artifact_bundle import budget_from_attempts, check_status, check_native, image_info, NATIVE_ROLES
# Reuse file safety/secret checks only; no ledger initialization or snapshots.
from run_ledger import canonical, digest, dimensions, label, new_file, now, read_bytes, safe, require_attempt_path

SCHEMA = 'pixel-standalone/1.0'
HASH = re.compile(r'^[0-9a-f]{64}$')


class RecordError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise RecordError(message)


def nonempty(value, name):
    require(isinstance(value, str) and bool(value.strip()), name + ' must be nonempty text')
    return value


def root_path(path):
    path = Path(os.path.abspath(path))
    require(not any(p.is_symlink() for p in [path, *path.parents]), 'Task path must not contain symlinks')
    return path


def capture(root, source, role):
    label(role)
    source = Path(os.path.abspath(source))
    data = read_bytes(source)
    dest = root / 'evidence' / (role + '-' + uuid.uuid4().hex + source.suffix)
    new_file(dest, data)
    entry = {'role': role, 'path': dest.relative_to(root).as_posix(),
             'sha256': digest(data), 'bytes': len(data), 'source_path': str(source)}
    if dimensions(data):
        entry['dimensions_px'] = dimensions(data)
        entry['dimensions_method'] = 'header_only'
    return entry


def config_entry(root, path, role):
    data = read_bytes(path)
    return {'role': role, 'path': path.relative_to(root).as_posix(),
            'sha256': digest(data), 'bytes': len(data)}


def evidence(root, entry, nonempty_file=False):
    require(isinstance(entry, dict), 'Evidence must be an object')
    label(entry.get('role'))
    require(isinstance(entry.get('sha256'), str) and HASH.fullmatch(entry['sha256']), 'Invalid evidence hash')
    require(type(entry.get('bytes')) is int and entry['bytes'] >= 0, 'Invalid evidence byte count')
    path = relative_file(root, entry.get('path'), 'evidence.path')
    # relative_file checks containment; read_bytes also rejects internal symlinks.
    raw = read_bytes(root / entry['path'])
    require(digest(raw) == entry['sha256'] and len(raw) == entry['bytes'], 'Changed evidence: ' + entry['path'])
    if nonempty_file:
        require(bool(raw.strip()), 'Empty evidence: ' + entry['path'])
    measured = dimensions(raw)
    require(entry.get('dimensions_px') == measured, 'Dimensions differ from preserved header')
    if measured:
        require(entry.get('dimensions_method') == 'header_only', 'Unsupported dimension claim')
    return path


def save(root, record):
    safe(record)
    dest = root / ('.task-' + uuid.uuid4().hex + '.tmp')
    new_file(dest, canonical(record) + b'\n', readonly=False)
    os.replace(dest, root / 'task.json')


def source_entries(record):
    yield from record['sources']
    for attempt in record['attempts']:
        yield from attempt['outputs']
    for delivery in record['deliveries']:
        yield delivery['file']


def validate(root, record):
    require(record.get('schema') == SCHEMA, 'Unsupported standalone record schema')
    require(record.get('history_scope') == 'recorded_task_only', 'Unexpected history scope')
    require(record.get('prior_generation_usage') in ('unknown', 'not_claimed'), 'Invalid prior usage state')
    for key in ('request', 'project', 'profile'):
        evidence(root, record.get(key), nonempty_file=True)
    project = load_project(root / record['project']['path'])
    require(project['schema_version'] == '3.0', 'Standalone tasks require project schema 3.0')
    require({'max_calls', 'max_total_repairs', 'repairs_per_pose'} <= set(project['budget']),
            'Standalone tasks need explicit call, total-repair and per-pose repair caps')
    require('run_directory' not in project, 'An existing ledger project must continue its full run')
    require(Path(project['_meta']['profile_path']) == (root / record['profile']['path']).resolve(), 'Profile mismatch')
    require((root / record['request']['path']).read_text(encoding='utf-8') == record.get('request_text'), 'Request text mismatch')
    for field in ('sources', 'attempts', 'deliveries'):
        require(isinstance(record.get(field), list), field + ' must be an array')
    if record['sources']:
        require(record['prior_generation_usage'] == 'unknown', 'Imported sources have unknown prior usage; never invent zero')
    for source in record['sources']:
        evidence(root, source)
        require(source.get('prior_generation_usage') == 'unknown', 'Imported source history must remain unknown')
    seen, originals, stage_poses = {}, set(), set()
    for number, attempt in enumerate(record['attempts'], 1):
        require(isinstance(attempt, dict), 'Attempt must be an object')
        aid = 'attempt-' + str(number).zfill(4)
        require(attempt.get('attempt_id') == aid, 'Attempt IDs must be contiguous, unique and ordered')
        stage, pose = attempt.get('stage'), attempt.get('pose_id')
        label(stage); label(pose)
        nonempty(attempt.get('tool'), 'tool')
        require(attempt.get('outcome') in ('pending', 'success', 'failed', 'cancelled'), 'Invalid attempt outcome')
        started = datetime.fromisoformat(attempt['started_at'])
        require(started.tzinfo is not None, 'Attempt timestamps need a timezone')
        repair = attempt.get('repair_of')
        if repair is not None:
            require(repair in seen, 'Repair must link an earlier attempt')
            original = seen[repair]
            require((stage, pose) == (original['stage'], original['pose_id']), 'Repair changed stage or semantic pose')
            require(original['outcome'] != 'pending', 'Cannot repair a pending attempt')
            require(datetime.fromisoformat(original['finished_at']) <= started, 'Repair started before linked attempt finished')
        else:
            require((stage, pose) not in stage_poses, 'Repeat stage/pose requires repair_of; do not evade a repair cap')
        stage_poses.add((stage, pose))
        for key in ('prompt', 'parameters'):
            evidence(root, attempt.get(key), nonempty_file=True)
        args = read_json(root / attempt['parameters']['path'])
        if 'prompt' in args:
            require(args['prompt'] == (root / attempt['prompt']['path']).read_text(encoding='utf-8'), 'Prompt differs from tool parameters.prompt')
        for field in ('references', 'outputs'):
            require(isinstance(attempt.get(field), list), field + ' must be an array')
            roles = [entry.get('role') for entry in attempt[field]]
            require(len(roles) == len(set(roles)), 'Duplicate ' + field + ' role')
            for entry in attempt[field]:
                evidence(root, entry)
        for entry in attempt['outputs']:
            origin = entry.get('source_path')
            require(isinstance(origin, str) and os.path.isabs(origin), 'Output needs its original absolute path')
            require_attempt_path(origin, aid)
            require(origin not in originals, 'Original output path reused')
            originals.add(origin)
        if attempt['outcome'] == 'pending':
            require(not attempt['outputs'] and 'finished_at' not in attempt, 'Pending attempt has completion data')
        else:
            finished = datetime.fromisoformat(attempt['finished_at'])
            require(finished.tzinfo is not None and finished >= started, 'Invalid completion time')
            if attempt['outcome'] == 'success':
                require(attempt['outputs'], 'Successful generation needs preserved original output')
            else:
                nonempty(attempt.get('error'), 'Failed/cancelled attempt error')
        seen[aid] = attempt
    counters = budget_from_attempts(record['attempts'], project['budget'])
    ids, native_sets, deliveries, superseded = set(), {}, {}, set()
    sources = {entry['sha256']: entry for entry in record['sources']}
    sources.update((entry['sha256'], entry) for attempt in record['attempts'] for entry in attempt['outputs'])
    for delivery in record['deliveries']:
        label(delivery.get('id'))
        require(delivery['id'] not in ids, 'Duplicate delivery ID')
        ids.add(delivery['id'])
        label(delivery.get('role'))
        check_status(delivery, delivery['id'])
        for field in ('file', 'review', 'provenance'):
            evidence(root, delivery.get(field), nonempty_file=True)
        require(delivery.get('source_sha256') in sources, 'Delivery source must be a preserved input, output, or earlier delivery')
        if delivery['role'] in NATIVE_ROLES:
            label(delivery.get('set_id'))
            source = sources[delivery['source_sha256']]
            # Decode the actual PNG, then reuse the full handoff's native checks.
            info = image_info(root / delivery['file']['path'])
            fingerprint = check_native({**delivery, 'source': source}, info, project)
            sid = delivery['set_id']
            require(sid not in native_sets or native_sets[sid] == fingerprint, 'Native set geometry/palette/anchor mismatch')
            native_sets[sid] = fingerprint
            if delivery['role'] == 'pose':
                label(delivery.get('pose_id'))
                master = deliveries.get(delivery.get('master_id'))
                require(master is not None and master['role'] == 'native_master', 'Pose needs an earlier native_master delivery')
                require(master['set_id'] == sid, 'Pose/master native set mismatch')
                if delivery['status'] == 'accepted':
                    require(master['status'] == 'accepted', 'Accepted pose requires an accepted native master')
        else:
            require(delivery.get('native') is None and delivery.get('set_id') is None, 'Only native_master/pose may claim native metadata')
        nonempty(delivery.get('limitations'), 'limitations')
        approval = delivery.get('approval')
        if delivery['status'] == 'accepted':
            require(isinstance(approval, dict), 'Accepted delivery requires authority evidence')
            require(approval.get('actor') in ('user', 'assistant'), 'Approval actor must be user or assistant')
            require(approval.get('role') == delivery['role'], 'Approval role mismatch')
            require(approval.get('asset_sha256') == delivery['file']['sha256'], 'Approval asset hash is stale')
            require(approval.get('source_sha256') == delivery['source_sha256'], 'Approval source hash is stale')
            nonempty(approval.get('scope'), 'approval.scope')
            nonempty(approval.get('reason'), 'approval.reason')
            evidence(root, approval.get('evidence'), nonempty_file=True)
            if approval['actor'] == 'assistant':
                evidence(root, approval.get('delegation'), nonempty_file=True)
            elif approval.get('delegation') is not None:
                evidence(root, approval['delegation'], nonempty_file=True)
        else:
            require(approval is None, 'Unaccepted delivery must not claim approval')
        if 'supersedes' in delivery:
            target = delivery['supersedes']
            require(isinstance(target, str) and target in deliveries, 'Supersedes must name an earlier delivery')
            prior = deliveries[target]
            require(target not in superseded, 'Delivery was already superseded')
            require(delivery['status'] == 'accepted' and prior['status'] != 'accepted',
                    'Only an accepted replacement may supersede an unaccepted delivery')
            require(all(delivery.get(key) == prior.get(key) for key in ('role', 'set_id', 'pose_id')),
                    'Supersession must preserve role, native set and semantic pose')
            superseded.add(target)
        sources[delivery['file']['sha256']] = delivery['file']
        deliveries[delivery['id']] = delivery
    active = [d for d in record['deliveries'] if d['id'] not in superseded]
    return {'record_consistency': 'passed', 'history_authenticated': False,
            'visual_judgment_performed': False, 'budget_state': counters,
            'prior_generation_usage': record['prior_generation_usage'],
            'project_path': str(root / record['project']['path']),
            'delivery_count': len(record['deliveries']),
            'all_deliveries_accepted': bool(record['deliveries']) and all(d['status'] == 'accepted' for d in record['deliveries']),
            'active_delivery_ids': [d['id'] for d in active],
            'all_active_deliveries_accepted': bool(active) and all(d['status'] == 'accepted' for d in active),
            'task_ready': bool(active) and all(d['status'] == 'accepted' for d in active) and not counters['pending_attempts']}


def inspect(task):
    root = root_path(task)
    require(root.is_dir(), 'Task directory is missing')
    require(not (root / 'task.json').is_symlink(), 'Task record must not be a symlink')
    record = read_json(root / 'task.json')
    return record, validate(root, record)


@contextmanager
def writable(task):
    root = root_path(task)
    require(root.is_dir(), 'Task directory is missing')
    require(not (root / '.lock').is_symlink(), 'Lock must not be a symlink')
    with (root / '.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record, _ = inspect(root)
        yield root, record
        validate(root, record)
        save(root, record)


def init_task(task, project_file, request_file, sources=()):
    root = root_path(task)
    project = load_project(project_file)
    require(project['schema_version'] == '3.0', 'Standalone tasks require project schema 3.0')
    require({'max_calls', 'max_total_repairs', 'repairs_per_pose'} <= set(project['budget']),
            'Standalone tasks need explicit call, total-repair and per-pose repair caps')
    require('run_directory' not in project, 'An existing ledger project must continue its full run')
    profile_relative = Path(project['profile'])
    require(profile_relative != Path('project.json'), 'Profile must not overwrite copied project.json')
    request = read_bytes(request_file).decode('utf-8')
    nonempty(request, 'request')
    root.mkdir(exist_ok=False)
    (root / 'evidence').mkdir()
    (root / 'config').mkdir()
    new_file(root / 'config/project.json', read_bytes(project_file))
    target_profile = root / 'config' / profile_relative
    target_profile.parent.mkdir(parents=True, exist_ok=True)
    new_file(target_profile, read_bytes(project['_meta']['profile_path']))
    imported = []
    for role, path in sources:
        imported.append({**capture(root, path, role), 'prior_generation_usage': 'unknown'})
    record = {'schema': SCHEMA, 'task_id': uuid.uuid4().hex, 'created_at': now(),
              'history_scope': 'recorded_task_only', 'prior_generation_usage': 'unknown' if imported else 'not_claimed',
              'request_text': request, 'request': capture(root, request_file, 'request'),
              'project': config_entry(root, root / 'config/project.json', 'project'),
              'profile': config_entry(root, target_profile, 'profile'), 'sources': imported,
              'attempts': [], 'deliveries': []}
    report = validate(root, record)
    save(root, record)
    return {'task': str(root), 'task_id': record['task_id'], **report}


def start(task, stage, pose, tool, prompt_file, parameters_file, references=(), repair_of=None):
    label(stage); label(pose); nonempty(tool, 'tool')
    with writable(task) as (root, record):
        aid = 'attempt-' + str(len(record['attempts']) + 1).zfill(4)
        # Validate budgets and repair semantics before capturing inputs or permitting a call.
        attempt = {'attempt_id': aid, 'stage': stage, 'pose_id': pose, 'repair_of': repair_of,
                   'tool': tool, 'outcome': 'pending', 'started_at': now(), 'outputs': []}
        project = load_project(root / record['project']['path'])
        budget_from_attempts(record['attempts'] + [attempt], project['budget'])
        attempt.update(prompt=capture(root, prompt_file, 'prompt'),
                       parameters=capture(root, parameters_file, 'parameters'),
                       references=[capture(root, path, role) for role, path in references])
        record['attempts'].append(attempt)
        report = validate(root, record)
    return {'attempt_id': aid, 'artifact_namespace': aid,
            'source_directory': str(root / 'sources' / aid), 'budget_state': report['budget_state']}


def end(task, attempt_id, outcome, outputs=(), error=None):
    require(outcome in ('success', 'failed', 'cancelled'), 'Invalid completion outcome')
    with writable(task) as (root, record):
        attempt = next((a for a in record['attempts'] if a['attempt_id'] == attempt_id), None)
        require(attempt is not None, 'Unknown attempt')
        require(attempt['outcome'] == 'pending', 'Attempt is already completed')
        for _, source in outputs:
            require_attempt_path(source, attempt_id)
        attempt.update(outcome=outcome, finished_at=now(), error=error,
                       outputs=[capture(root, path, role) for role, path in outputs])
        report = validate(root, record)
    return {'attempt_id': attempt_id, 'outcome': outcome, 'preserved_outputs': attempt['outputs'],
            'budget_state': report['budget_state']}


def deliver(task, spec_file):
    """Append a new immutable delivery decision; paths are relative to the spec."""
    spec_file = Path(spec_file).absolute()
    spec = read_json(spec_file)
    def supplied(field, name):
        return relative_file(spec_file.parent, field, name)
    with writable(task) as (root, record):
        file = supplied(spec.get('file'), 'file')
        source = supplied(spec.get('source_file'), 'source_file')
        source_hash = digest(read_bytes(source))
        require(source_hash in {e['sha256'] for e in source_entries(record)}, 'Source was not preserved by this task')
        entry = {key: spec.get(key) for key in ('id', 'role', 'status', 'technical_status', 'visual_status', 'limitations')}
        for key in ('native', 'set_id', 'pose_id', 'master_id', 'supersedes'):
            if key in spec:
                entry[key] = spec[key]
        entry.update(recorded_at=now(), file=capture(root, file, 'delivery'), source_sha256=source_hash,
                     review=capture(root, supplied(spec.get('review_file'), 'review_file'), 'review'),
                     provenance=capture(root, supplied(spec.get('provenance_file'), 'provenance_file'), 'provenance'), approval=None)
        if spec.get('approval') is not None:
            approval = spec['approval']
            require(isinstance(approval, dict), 'Approval must be an object')
            # Supplied hashes must match; do not silently rewrite stale authority evidence.
            entry['approval'] = {key: approval.get(key) for key in ('actor', 'role', 'asset_sha256', 'source_sha256', 'scope', 'reason')}
            entry['approval']['evidence'] = capture(root, supplied(approval.get('evidence_file'), 'approval.evidence_file'), 'approval')
            if approval.get('delegation_file') is not None:
                entry['approval']['delegation'] = capture(root, supplied(approval['delegation_file'], 'approval.delegation_file'), 'delegation')
        record['deliveries'].append(entry)
        report = validate(root, record)
    return {'delivery_id': entry['id'], 'sha256': entry['file']['sha256'], **report}


def export_budget(task, output):
    root = root_path(task)
    record, report = inspect(root)
    result = {'attempts': [{key: attempt[key] for key in
                           ('attempt_id', 'stage', 'pose_id', 'repair_of', 'outcome')}
                          for attempt in record['attempts']],
              'standalone_record_sha256': digest(read_bytes(root / 'task.json')),
              'history_scope': record['history_scope'],
              'prior_generation_usage': record['prior_generation_usage'],
              'budget_state': report['budget_state']}
    # Exclusive create: each export is a checkpoint, never a rewritten past total.
    new_file(Path(output), canonical(result) + b'\n')
    return {'budget_evidence_file': str(Path(output).absolute()), **report}


def role_path(value):
    if '=' not in value:
        raise argparse.ArgumentTypeError('Use ROLE=FILE')
    return tuple(value.split('=', 1))


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='Create a new compact task; never use to reset continuation budget')
    init.add_argument('task'); init.add_argument('--project', required=True); init.add_argument('--request-file', required=True)
    init.add_argument('--source', action='append', type=role_path, default=[])
    begin = sub.add_parser('start', help='Count/reserve an attempt BEFORE invoking generation')
    begin.add_argument('task')
    for flag in ('stage', 'pose', 'tool', 'prompt-file', 'parameters-file'):
        begin.add_argument('--' + flag, required=True)
    begin.add_argument('--repair-of'); begin.add_argument('--reference', action='append', type=role_path, default=[])
    finish = sub.add_parser('end', help='Complete an attempt without refunding calls or repairs')
    finish.add_argument('task'); finish.add_argument('--attempt', required=True)
    finish.add_argument('--outcome', choices=('success', 'failed', 'cancelled'), required=True)
    finish.add_argument('--output', action='append', type=role_path, default=[]); finish.add_argument('--error')
    delivery = sub.add_parser('deliver', help='Record a hash-bound study/rejection/acceptance; never invent authority')
    delivery.add_argument('task'); delivery.add_argument('--spec-file', required=True)
    check = sub.add_parser('check', help='Validate current evidence/claims and derive all counters')
    check.add_argument('task')
    budget = sub.add_parser('budget-evidence', help='Export derived attempts for an evidence_only portable bundle')
    budget.add_argument('task'); budget.add_argument('output')
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            result = init_task(args.task, args.project, args.request_file, args.source)
        elif args.command == 'start':
            result = start(args.task, args.stage, args.pose, args.tool, args.prompt_file, args.parameters_file, args.reference, args.repair_of)
        elif args.command == 'end':
            result = end(args.task, args.attempt, args.outcome, args.output, args.error)
        elif args.command == 'deliver':
            result = deliver(args.task, args.spec_file)
        elif args.command == 'budget-evidence':
            result = export_budget(args.task, args.output)
        else:
            result = inspect(args.task)[1]
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        print('Standalone record error: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(cli())
