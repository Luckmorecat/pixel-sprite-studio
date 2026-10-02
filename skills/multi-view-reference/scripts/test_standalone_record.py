#!/usr/bin/env python3
"""Synthetic evidence only: no generator calls, real approvals, or network."""
import copy
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

import artifact_bundle
import standalone_record as records


def write(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


def png(path):
    def chunk(kind, raw):
        return struct.pack('>I', len(raw)) + kind + raw + struct.pack('>I', zlib.crc32(kind + raw) & 0xffffffff)
    rows = b''.join(b'\0' + bytes([0, 0, 0, 255]) * 4 for _ in range(4))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 4, 4, 8, 6, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


class StandaloneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='standalone-record-tests-')
        self.root = Path(self.temp.name)
        self.addCleanup(self.cleanup)
        self.project = {'schema_version': '3.0', 'asset_id': 'fixture', 'brief': 'Synthetic fixture.',
                        'profile': 'style/profile.json', 'native_canvas_px': [4, 4],
                        'limits': {'palette_max': 4, 'binary_alpha': True, 'min_margin': 0},
                        'budget': {'max_calls': 4, 'max_total_repairs': 2, 'repairs_per_pose': 1}}
        self.project_path = self.root / 'project.json'
        write(self.project_path, self.project)
        (self.root / 'style').mkdir()
        write(self.root / 'style/profile.json', {'medium': 'pixel_art', 'identity': {'silhouette': 'Synthetic fixture'}})
        self.request = self.root / 'request.txt'
        self.request.write_text('Synthetic user-request evidence; not an actual approval.\n')
        self.prompt = self.root / 'prompt.txt'
        self.prompt.write_text('Exact synthetic prompt: 雪\n\n')
        self.args = self.root / 'parameters.json'
        write(self.args, {'prompt': self.prompt.read_text(), 'transparent_background': True})
        self.source = self.root / 'import.png'
        png(self.source)
        self.task = self.root / 'task'

    def cleanup(self):
        for base, dirs, files in os.walk(self.root):
            os.chmod(base, 0o755)
        self.temp.cleanup()

    def init(self, sources=(), **budget):
        self.project['budget'].update(budget)
        write(self.project_path, self.project)
        return records.init_task(self.task, self.project_path, self.request, sources)

    def start(self, pose='neutral', stage='identity', repair_of=None, references=()):
        return records.start(self.task, stage, pose, 'synthetic-tool', self.prompt, self.args, references, repair_of)

    def finish(self, aid, outcome='success'):
        output = self.root / 'sources' / aid / 'original.png'
        if outcome == 'success':
            output.parent.mkdir(parents=True, exist_ok=True)
            png(output)
        return records.end(self.task, aid, outcome, [('original', output)] if outcome == 'success' else [],
                           None if outcome == 'success' else 'Synthetic failure')

    def mutate(self, change):
        path = self.task / 'task.json'
        record = json.loads(path.read_text())
        change(record)
        write(path, record)

    def delivery_spec(self, accepted=False):
        for name in ('review', 'provenance', 'approval', 'delegation'):
            (self.root / (name + '.txt')).write_text('Synthetic ' + name + '; no real approval asserted.\n')
        spec = {'id': 'identity-01', 'file': 'import.png', 'source_file': 'import.png', 'role': 'identity',
                'status': 'study', 'technical_status': 'unverified', 'visual_status': 'unverified',
                'review_file': 'review.txt', 'provenance_file': 'provenance.txt', 'limitations': 'Synthetic fixture only',
                'approval': None}
        if accepted:
            spec.update(status='accepted', technical_status='passed', visual_status='accepted')
            h = records.digest(self.source.read_bytes())
            spec['approval'] = {'actor': 'assistant', 'role': 'identity', 'asset_sha256': h, 'source_sha256': h,
                                'evidence_file': 'approval.txt', 'delegation_file': 'delegation.txt',
                                'reason': 'Synthetic test reason', 'scope': 'Synthetic identity fixture'}
        return spec

    def deliver(self, spec):
        file = self.root / 'delivery.json'
        write(file, spec)
        return records.deliver(self.task, file)

    def test_minimal_init_preserves_request_and_exact_configuration_without_snapshots(self):
        report = self.init()
        record, checked = records.inspect(self.task)
        self.assertEqual((self.task / 'config/project.json').read_bytes(), self.project_path.read_bytes())
        self.assertEqual((self.task / 'config/style/profile.json').read_bytes(), (self.root / 'style/profile.json').read_bytes())
        self.assertEqual(record['request_text'], self.request.read_text())
        self.assertEqual(checked['budget_state']['attempted_calls'], 0)
        self.assertFalse(checked['history_authenticated'])
        self.assertFalse((self.task / 'snapshots').exists())
        self.assertFalse((self.task / 'events.jsonl').exists())
        self.assertEqual(Path(report['project_path']), self.task / 'config/project.json')

    def test_imported_source_unknown_history_not_zero_or_approval(self):
        self.init(sources=[('supplied', self.source)])
        record, report = records.inspect(self.task)
        self.assertEqual(report['prior_generation_usage'], 'unknown')
        self.assertEqual(record['sources'][0]['prior_generation_usage'], 'unknown')
        self.assertEqual(record['deliveries'], [])
        self.mutate(lambda r: r['sources'][0].update(prior_generation_usage=0))
        with self.assertRaisesRegex(ValueError, 'history'):
            records.inspect(self.task)

    def test_existing_directory_and_ledger_project_rejected(self):
        self.init()
        with self.assertRaises(FileExistsError):
            self.init()
        self.project['run_directory'] = 'run'
        write(self.project_path, self.project)
        with self.assertRaisesRegex(ValueError, 'full run'):
            records.init_task(self.root / 'bad-task', self.project_path, self.request)

    def test_budget_types_and_legacy_schema_rejected(self):
        with self.assertRaises(ValueError):
            self.init(max_calls=True)
        self.project['budget']['max_calls'] = 3
        self.project['schema_version'] = '2.0'
        write(self.project_path, self.project)
        with self.assertRaisesRegex(ValueError, '3.0'):
            records.init_task(self.task, self.project_path, self.request)

    def test_missing_repair_caps_do_not_create_an_unbounded_standalone_task(self):
        self.project['budget'].pop('max_total_repairs')
        write(self.project_path, self.project)
        with self.assertRaisesRegex(ValueError, 'explicit call'):
            records.init_task(self.task, self.project_path, self.request)
        self.assertFalse(self.task.exists())

    def test_exact_prompt_args_reference_and_pending_budget(self):
        self.init()
        aid = self.start(references=[('input', self.source)])['attempt_id']
        record, report = records.inspect(self.task)
        attempt = record['attempts'][0]
        self.assertEqual((self.task / attempt['prompt']['path']).read_bytes(), self.prompt.read_bytes())
        self.assertEqual((self.task / attempt['parameters']['path']).read_bytes(), self.args.read_bytes())
        self.assertEqual(attempt['references'][0]['sha256'], records.digest(self.source.read_bytes()))
        self.assertEqual(report['budget_state']['pending_attempts'], [aid])
        self.assertEqual(report['budget_state']['remaining_calls'], 3)

    def test_prompt_parameters_disagreement_blocks_before_generator(self):
        self.init()
        write(self.args, {'prompt': 'Different prompt'})
        with self.assertRaisesRegex(ValueError, 'Prompt differs'):
            self.start()
        self.assertEqual(records.inspect(self.task)[1]['budget_state']['attempted_calls'], 0)

    def test_failed_cancelled_pending_calls_exhaust_cap(self):
        self.init(max_calls=3)
        self.finish(self.start(pose='a')['attempt_id'], 'failed')
        self.finish(self.start(pose='b')['attempt_id'], 'cancelled')
        self.start(pose='c')
        with self.assertRaisesRegex(ValueError, 'max_calls'):
            self.start(pose='d')
        self.assertEqual(records.inspect(self.task)[1]['budget_state']['attempted_calls'], 3)

    def test_repair_links_per_pose_cumulative_cap_and_total_cap(self):
        self.init(max_calls=10)
        a = self.start()['attempt_id']; self.finish(a)
        b = self.start(repair_of=a)['attempt_id']; self.finish(b, 'failed')
        with self.assertRaisesRegex(ValueError, 'repairs_per_pose'):
            self.start(repair_of=b)
        c = self.start(stage='refinement')['attempt_id']; self.finish(c)
        with self.assertRaisesRegex(ValueError, 'repairs_per_pose'):
            self.start(stage='refinement', repair_of=c)
        d = self.start(pose='side')['attempt_id']; self.finish(d)
        e = self.start(pose='side', repair_of=d)['attempt_id']; self.finish(e)
        f = self.start(pose='back')['attempt_id']; self.finish(f)
        with self.assertRaisesRegex(ValueError, 'max_total_repairs'):
            self.start(pose='back', repair_of=f)

    def test_repeat_stage_pose_without_repair_rejected(self):
        self.init()
        aid = self.start()['attempt_id']; self.finish(aid)
        with self.assertRaisesRegex(ValueError, 'repair_of'):
            self.start()
        self.assertEqual(records.inspect(self.task)[1]['budget_state']['attempted_calls'], 1)

    def test_pending_repair_future_link_and_changed_stage_rejected(self):
        self.init()
        aid = self.start()['attempt_id']
        with self.assertRaisesRegex(ValueError, 'pending'):
            self.start(repair_of=aid)
        with self.assertRaisesRegex(ValueError, 'earlier'):
            self.start(repair_of='attempt-0099')
        self.finish(aid)
        with self.assertRaisesRegex(ValueError, 'changed stage'):
            self.start(stage='other', repair_of=aid)

    def test_success_requires_output_failed_requires_error_and_no_double_end(self):
        self.init()
        aid = self.start()['attempt_id']
        with self.assertRaisesRegex(ValueError, 'preserved original'):
            records.end(self.task, aid, 'success')
        with self.assertRaisesRegex(ValueError, 'error'):
            records.end(self.task, aid, 'failed')
        self.finish(aid)
        with self.assertRaisesRegex(ValueError, 'already completed'):
            self.finish(aid)

    def test_original_names_must_be_attempt_unique_and_copies_are_immutable(self):
        self.init()
        aid = self.start()['attempt_id']
        with self.assertRaisesRegex(ValueError, 'exact attempt ID'):
            records.end(self.task, aid, 'success', [('original', self.source)])
        self.finish(aid)
        record, _ = records.inspect(self.task)
        output = record['attempts'][0]['outputs'][0]
        self.assertEqual(output['dimensions_px'], [4, 4])
        self.assertFalse((self.task / output['path']).stat().st_mode & 0o222)
        Path(output['source_path']).write_bytes(b'changed external file')
        self.assertEqual(records.inspect(self.task)[1]['record_consistency'], 'passed')
        p = self.task / output['path']; p.chmod(0o644); p.write_bytes(b'changed preserved file')
        with self.assertRaisesRegex(ValueError, 'Changed evidence'):
            records.inspect(self.task)

    def test_attempt_ids_and_source_links_validated_not_manual_totals(self):
        self.init()
        self.start()
        self.mutate(lambda r: r.update(budget_state={'attempted_calls': 0}))
        self.assertEqual(records.inspect(self.task)[1]['budget_state']['attempted_calls'], 1)
        self.mutate(lambda r: r['attempts'][0].update(attempt_id='attempt-0002'))
        with self.assertRaisesRegex(ValueError, 'contiguous'):
            records.inspect(self.task)

    def test_symlink_task_evidence_and_credential_inputs_rejected(self):
        self.init()
        alias = self.root / 'alias'; alias.symlink_to(self.task, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            records.inspect(alias)
        write(self.args, {'api_key': 'do-not-store-secrets'})
        with self.assertRaisesRegex(ValueError, 'Credential'):
            self.start()
        record, _ = records.inspect(self.task)
        p = self.task / record['request']['path']; p.unlink(); p.symlink_to(self.request)
        with self.assertRaises(ValueError):
            records.inspect(self.task)

    def test_study_does_not_invent_acceptance_and_delivery_preserves_source(self):
        self.init(sources=[('supplied', self.source)])
        report = self.deliver(self.delivery_spec())
        self.assertFalse(report['task_ready'])
        record, _ = records.inspect(self.task)
        self.assertIsNone(record['deliveries'][0]['approval'])
        self.assertEqual(record['deliveries'][0]['source_sha256'], records.digest(self.source.read_bytes()))
        self.assertFalse(report['visual_judgment_performed'])

    def test_acceptance_requires_separate_gates_actor_delegation_and_exact_hashes(self):
        self.init(sources=[('supplied', self.source)])
        valid = self.delivery_spec(accepted=True)
        for change in (lambda s: s.update(technical_status='unverified'),
                       lambda s: s.update(visual_status='unverified'),
                       lambda s: s.update(approval=None),
                       lambda s: s['approval'].update(actor='generator'),
                       lambda s: s['approval'].pop('delegation_file'),
                       lambda s: s['approval'].update(asset_sha256='0' * 64),
                       lambda s: s['approval'].update(source_sha256='0' * 64),
                       lambda s: s['approval'].update(role='native_master')):
            spec = copy.deepcopy(valid); change(spec)
            with self.assertRaises(ValueError):
                self.deliver(spec)
        report = self.deliver(valid)
        self.assertTrue(report['task_ready'])
        record, _ = records.inspect(self.task)
        self.assertEqual(record['deliveries'][0]['approval']['actor'], 'assistant')
        with self.assertRaisesRegex(ValueError, 'Duplicate delivery'):
            self.deliver(valid)

    def test_user_actor_can_omit_delegation_but_needs_own_evidence(self):
        self.init(sources=[('supplied', self.source)])
        spec = self.delivery_spec(accepted=True)
        spec['approval']['actor'] = 'user'
        spec['approval'].pop('delegation_file')
        self.assertTrue(self.deliver(spec)['task_ready'])

    def test_unpreserved_source_rejected_and_pending_prevents_ready(self):
        self.init()
        spec = self.delivery_spec()
        with self.assertRaisesRegex(ValueError, 'not preserved'):
            self.deliver(spec)
        aid = self.start()['attempt_id']; self.finish(aid)
        self.start(pose='other')
        spec = self.delivery_spec(accepted=True)
        # Synthetic imported and generated bytes match; exact content is preserved.
        self.assertFalse(self.deliver(spec)['task_ready'])

    @unittest.skipUnless(shutil.which('magick') or shutil.which('convert'), 'ImageMagick required for native checks')
    def test_native_master_requires_measured_pixels_and_valid_native_contract(self):
        self.init(sources=[('supplied', self.source)])
        spec = self.delivery_spec(accepted=True)
        spec.update(role='native_master', set_id='native')
        spec['approval']['role'] = 'native_master'
        with self.assertRaisesRegex(ValueError, 'native canvas/palette/grid/anchor'):
            self.deliver(spec)
        spec['native'] = {'grid_px': 1, 'anchor_px': [2, 3], 'palette': ['#000000'],
                          'grid': {'source_canvas_px': [4, 4], 'crop': None}}
        valid = copy.deepcopy(spec)
        for mutate in (lambda s: s['native']['grid'].update(source_canvas_px=[8, 8]),
                       lambda s: s['native'].update(palette=['#ffffff']),
                       lambda s: s['native'].update(anchor_px=[5, 5]),
                       lambda s: s['native'].update(grid_px=2)):
            invalid = copy.deepcopy(valid); mutate(invalid)
            with self.assertRaises(ValueError):
                self.deliver(invalid)
        self.assertTrue(self.deliver(valid)['task_ready'])

    def test_budget_export_compatible_with_existing_bundle_counter_schema(self):
        self.init(sources=[('supplied', self.source)])
        aid = self.start()['attempt_id']; self.finish(aid, 'failed')
        self.start(repair_of=aid)
        target = self.root / 'budget-evidence.json'
        records.export_budget(self.task, target)
        exported = json.loads(target.read_text())
        calculated = artifact_bundle.budget_from_attempts(exported['attempts'], self.project['budget'])
        self.assertEqual(calculated, records.inspect(self.task)[1]['budget_state'])
        self.assertEqual(exported['prior_generation_usage'], 'unknown')
        self.assertEqual(exported['standalone_record_sha256'], records.digest((self.task / 'task.json').read_bytes()))
        with self.assertRaises(FileExistsError):
            records.export_budget(self.task, target)

    def test_relocated_task_continues_same_attempt_ids_and_remaining_budget(self):
        self.init()
        aid = self.start()['attempt_id']; self.finish(aid, 'failed')
        moved = self.root / 'elsewhere/copied-task'
        shutil.copytree(self.task, moved)
        shutil.rmtree(self.task)
        checked = records.inspect(moved)[1]
        self.assertEqual(checked['budget_state']['attempted_calls'], 1)
        next_call = records.start(moved, 'identity', 'neutral', 'synthetic-tool', self.prompt, self.args, repair_of=aid)
        self.assertEqual(next_call['attempt_id'], 'attempt-0002')
        self.assertEqual(next_call['budget_state']['remaining_calls'], 2)

    def test_cli_init_start_end_check_and_budget_export(self):
        script = str(Path(records.__file__).resolve())
        def cli(*args):
            result = subprocess.run([sys.executable, script, *map(str, args)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        cli('init', self.task, '--project', self.project_path, '--request-file', self.request)
        started = cli('start', self.task, '--stage', 'identity', '--pose', 'neutral', '--tool', 'synthetic',
                      '--prompt-file', self.prompt, '--parameters-file', self.args)
        cli('end', self.task, '--attempt', started['attempt_id'], '--outcome', 'failed', '--error', 'Synthetic')
        self.assertEqual(cli('check', self.task)['budget_state']['attempted_calls'], 1)
        cli('budget-evidence', self.task, self.root / 'export.json')

    @unittest.skipUnless(shutil.which('magick') or shutil.which('convert'), 'ImageMagick required for existing bundle checker')
    def test_actual_evidence_only_bundle_carries_record_and_resumes_after_relocation(self):
        self.init(sources=[('supplied', self.source)])
        aid = self.start()['attempt_id']; self.finish(aid, 'failed')
        self.deliver(self.delivery_spec())
        records.export_budget(self.task, self.root / 'budget-evidence.json')
        spec = artifact_bundle.template()
        spec.update(project='task/config/project.json', budget_evidence_file='budget-evidence.json',
                    assets=[{'id': 'identity-01', 'file': 'import.png', 'role': 'identity', 'status': 'study',
                             'technical_status': 'unverified', 'visual_status': 'unverified',
                             'source': {'file': 'import.png', 'kind': 'supplied'}, 'review_file': 'review.txt',
                             'provenance_file': 'provenance.txt', 'approval': None}],
                    supports=[{'file': 'request.txt', 'role': 'request'}, {'directory': 'task', 'role': 'provenance'}])
        write(self.root / 'bundle-spec.json', spec)
        result = artifact_bundle.create_bundle(self.root / 'bundle-spec.json', self.root / 'handoff')
        self.assertEqual(result['continuation_mode'], 'evidence_only')
        self.assertEqual(result['budget_state']['attempted_calls'], 1)
        copied = self.root / 'handoff/support-trees/task'
        self.assertEqual(records.inspect(copied)[1]['budget_state']['remaining_calls'], 3)
        moved = self.root / 'resumed-task'; shutil.copytree(copied, moved)
        self.assertEqual(records.start(moved, 'identity', 'neutral', 'synthetic', self.prompt, self.args, repair_of=aid)['attempt_id'], 'attempt-0002')
        # Original immutable bundle checkpoint stays valid after work continues in a copy.
        self.assertEqual(artifact_bundle.check_bundle(self.root / 'handoff')['continuation_mode'], 'evidence_only')


    def test_explicit_accepted_replacement_preserves_study_history(self):
        self.init(sources=[('supplied', self.source)])
        self.deliver(self.delivery_spec())
        before = copy.deepcopy(records.inspect(self.task)[0]['deliveries'][0])
        spec = self.delivery_spec(accepted=True)
        spec.update(id='identity-02', supersedes='identity-01')
        report = self.deliver(spec)
        self.assertTrue(report['task_ready'])
        self.assertFalse(report['all_deliveries_accepted'])
        self.assertEqual(report['active_delivery_ids'], ['identity-02'])
        self.assertEqual(records.inspect(self.task)[0]['deliveries'][0], before)
        spec.update(id='identity-03')
        with self.assertRaisesRegex(ValueError, 'already superseded'):
            self.deliver(spec)

    def test_replacement_does_not_hide_unrelated_study_or_pending_calls(self):
        self.init(sources=[('supplied', self.source)])
        self.deliver(self.delivery_spec())
        other = self.delivery_spec(); other['id'] = 'other-study'; self.deliver(other)
        spec = self.delivery_spec(accepted=True)
        spec.update(id='identity-02', supersedes='identity-01')
        self.assertFalse(self.deliver(spec)['task_ready'])
        self.start()
        spec.update(id='other-accepted', supersedes='other-study')
        self.assertFalse(self.deliver(spec)['task_ready'])

    def test_replacement_requires_existing_unaccepted_same_role_and_authority(self):
        self.init(sources=[('supplied', self.source)])
        self.deliver(self.delivery_spec())
        valid = self.delivery_spec(accepted=True)
        valid.update(id='identity-02', supersedes='identity-01')
        for change in (lambda x: x.update(supersedes='missing'),
                       lambda x: x.update(supersedes='identity-02'),
                       lambda x: x.update(role='action'),
                       lambda x: x.update(approval=None),
                       lambda x: x['approval'].update(asset_sha256='0' * 64),
                       lambda x: x['approval'].pop('delegation_file')):
            bad = copy.deepcopy(valid); change(bad)
            with self.assertRaises(ValueError): self.deliver(bad)
        study = self.delivery_spec(); study.update(id='identity-02', supersedes='identity-01')
        with self.assertRaisesRegex(ValueError, 'accepted replacement'): self.deliver(study)
        self.deliver(valid)
        valid.update(id='identity-03', supersedes='identity-02')
        with self.assertRaisesRegex(ValueError, 'unaccepted delivery'): self.deliver(valid)

    def test_native_replacement_cannot_change_set_or_semantic_pose(self):
        self.init(sources=[('supplied', self.source)])
        native = {'grid_px': 1, 'anchor_px': [2, 3], 'palette': ['#000000'],
                  'grid': {'source_canvas_px': [4, 4], 'crop': None}}
        master = self.delivery_spec(accepted=True)
        master.update(id='master', role='native_master', set_id='set-a', native=native)
        master['approval']['role'] = 'native_master'; self.deliver(master)
        master.update(id='master-b', set_id='set-b'); self.deliver(master)
        study = self.delivery_spec()
        study.update(id='pose-study', role='pose', set_id='set-a', native=native, pose_id='blink', master_id='master')
        self.deliver(study)
        accepted = self.delivery_spec(accepted=True)
        accepted.update(id='pose-accepted', role='pose', set_id='set-a', native=native,
                        pose_id='blink', master_id='master', supersedes='pose-study')
        accepted['approval']['role'] = 'pose'
        for change in (dict(set_id='set-b', master_id='master-b'), dict(pose_id='open')):
            wrong = copy.deepcopy(accepted); wrong.update(change)
            with self.assertRaisesRegex(ValueError, 'preserve role, native set and semantic pose'):
                self.deliver(wrong)
        self.assertTrue(self.deliver(accepted)['task_ready'])

    def compact_bundle_fixture(self):
        self.init(sources=[('supplied', self.source)])
        self.finish(self.start()['attempt_id'], 'failed')
        self.deliver(self.delivery_spec())
        records.export_budget(self.task, self.root / 'budget.json')
        spec = artifact_bundle.template()
        spec.update(project='task/config/project.json', budget_evidence_file='budget.json',
                    assets=[{'id': 'identity-01', 'file': 'import.png', 'role': 'identity', 'status': 'study',
                             'technical_status': 'unverified', 'visual_status': 'unverified',
                             'source': {'file': 'import.png', 'kind': 'supplied'}, 'review_file': 'review.txt',
                             'provenance_file': 'provenance.txt', 'approval': None}],
                    supports=[{'file': 'request.txt', 'role': 'request'}, {'directory': 'task', 'role': 'provenance'}])
        write(self.root / 'bundle.json', spec)
        return spec

    def test_stale_compact_export_rejected_at_bundle_creation(self):
        self.compact_bundle_fixture()
        self.finish(self.start(pose='side')['attempt_id'], 'cancelled')
        with self.assertRaisesRegex(ValueError, 'source record hash'):
            artifact_bundle.create_bundle(self.root / 'bundle.json', self.root / 'handoff')
        self.assertFalse((self.root / 'handoff').exists())

    def test_compact_export_checks_actual_record_not_only_hash(self):
        self.compact_bundle_fixture()
        original = json.loads((self.root / 'budget.json').read_text())
        (self.root / 'budget.json').chmod(0o644)
        for key, value in [('attempts', []), ('budget_state', {}), ('history_scope', 'invented'),
                           ('prior_generation_usage', 'not_claimed')]:
            modified = copy.deepcopy(original); modified[key] = value
            write(self.root / 'budget.json', modified)
            with self.assertRaisesRegex(ValueError, 'Standalone exported'):
                artifact_bundle.create_bundle(self.root / 'bundle.json', self.root / 'handoff')
        write(self.root / 'budget.json', original)
        self.mutate(lambda r: r['attempts'][0].update(attempt_id='attempt-0009'))
        original['standalone_record_sha256'] = records.digest((self.task / 'task.json').read_bytes())
        write(self.root / 'budget.json', original)
        with self.assertRaisesRegex(ValueError, 'contiguous'):
            artifact_bundle.create_bundle(self.root / 'bundle.json', self.root / 'handoff')

    def test_compact_export_requires_included_record_and_project_binding(self):
        spec = self.compact_bundle_fixture()
        spec['supports'].pop(); write(self.root / 'bundle.json', spec)
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            artifact_bundle.create_bundle(self.root / 'bundle.json', self.root / 'handoff')
        spec['supports'].append({'directory': 'task', 'role': 'provenance'})
        spec['project'] = 'project.json'
        self.project['brief'] = 'Different source project'
        write(self.project_path, self.project); write(self.root / 'bundle.json', spec)
        with self.assertRaisesRegex(ValueError, 'checkpoint project'):
            artifact_bundle.create_bundle(self.root / 'bundle.json', self.root / 'handoff')

    def test_existing_bundle_checker_rejects_reinventoried_stale_compact_checkpoint(self):
        self.compact_bundle_fixture()
        out = self.root / 'handoff'
        artifact_bundle.create_bundle(self.root / 'bundle.json', out)
        # Simulate an older unchecked assembly: current task plus stale export,
        # with internally correct file inventory, so the cross-check must catch it.
        out.chmod(0o755)
        task = out / 'support-trees/task'
        for base, dirs, files in os.walk(task): os.chmod(base, 0o755)
        records.start(task, 'identity', 'side', 'synthetic', self.prompt, self.args)
        manifest = json.loads((out / 'bundle.json').read_text())
        manifest['inventory'] = [{'file': p.relative_to(out).as_posix(), 'sha256': records.digest(p.read_bytes()), 'bytes': p.stat().st_size}
                                 for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'bundle.json']
        (out / 'bundle.json').chmod(0o644); write(out / 'bundle.json', manifest)
        with self.assertRaisesRegex(ValueError, 'source record hash'): artifact_bundle.check_bundle(out)


if __name__ == '__main__':
    unittest.main()
