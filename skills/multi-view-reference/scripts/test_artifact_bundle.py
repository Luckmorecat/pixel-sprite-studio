#!/usr/bin/env python3
"""Synthetic files only; forward-portability and negative handoff gates."""
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
from unittest.mock import patch
import zlib

import artifact_bundle as bundle
from project_config import sha256
from test_project_config import project_fixture


def png(path, width=8, height=8, alternate=False):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    rows = []
    for y in range(height):
        pixels = []
        for x in range(width):
            color = (0, 0, 0, 255) if 2 <= x < width - 2 and 2 <= y < height - 2 else (0, 0, 0, 0)
            if alternate and x == 3 and y == 3:
                color = (255, 255, 255, 255)
            pixels.extend(color)
        rows.append(b'\0' + bytes(pixels))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b''))


def write(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


@unittest.skipUnless(shutil.which('magick') or shutil.which('convert'), 'ImageMagick required')
class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.cleanup)
        self.root = Path(self.tmp.name)
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        self.project = project_fixture()
        write(self.inputs / 'project.json', self.project)
        write(self.inputs / 'profile.json', {'identity': {'proportions': 'fixture', 'outfit': 'fixture',
                                                        'palette_roles': {'outline': '#000000', 'light': '#ffffff'}}})
        for name in ('request', 'review', 'provenance', 'approval', 'delegation'):
            (self.inputs / f'{name}.txt').write_text(f'Synthetic {name} evidence; no real-user approval asserted.\n')
        write(self.inputs / 'budget.json', {'attempts': []})
        png(self.inputs / 'identity.png')
        png(self.inputs / 'master.png')
        png(self.inputs / 'pose.png', alternate=True)
        self.spec = bundle.template()
        self.spec.update({'status': 'accepted', 'technical_status': 'passed', 'visual_status': 'accepted',
                          'stage': 'refinement', 'required_assets': ['identity', 'master'],
                          'budget_evidence_file': 'budget.json', 'next_step': 'Animate from the accepted master'})
        self.spec['assets'] = [self.asset('identity', 'identity.png', 'identity'),
                               self.asset('master', 'master.png', 'native_master')]
        self.spec_path = self.inputs / 'spec.json'
        self.save()
        self.output = self.root / 'handoff'

    def cleanup(self):
        for base, dirs, files in os.walk(self.root):
            os.chmod(base, 0o755)
        self.tmp.cleanup()

    def asset(self, aid, file, role):
        result = {'id': aid, 'file': file, 'role': role, 'status': 'accepted',
                  'technical_status': 'passed', 'visual_status': 'accepted',
                  'source': {'file': file, 'kind': 'supplied'},
                  'review_file': 'review.txt', 'provenance_file': 'provenance.txt',
                  'approval': {'actor': 'assistant', 'role': role, 'asset_sha256': sha256(self.inputs / file),
                               'source_sha256': sha256(self.inputs / file), 'reason': 'Synthetic fixture gate',
                               'evidence_file': 'approval.txt', 'delegation_file': 'delegation.txt'}}
        if role in bundle.NATIVE_ROLES:
            result.update({'set_id': 'native', 'native': {'grid_px': 1, 'anchor_px': [4, 6],
                           'palette': ['#000000', '#ffffff'], 'grid': {'source_canvas_px': [8, 8], 'crop': None}}})
        if role == 'pose':
            result.update({'pose_id': aid, 'master_id': 'master'})
        return result

    def save(self):
        write(self.spec_path, self.spec)

    def create(self):
        self.save()
        return bundle.create_bundle(self.spec_path, self.output)

    def manifest(self):
        return json.loads((self.output / 'bundle.json').read_text())

    def mutate_manifest(self, change):
        data = self.manifest()
        change(data)
        write(self.output / 'bundle.json', data)

    def test_valid_bundle_survives_unrelated_directory_no_source_session(self):
        report = self.create()
        self.assertTrue(report['handoff_ready'])
        self.assertFalse(report['visual_judgment_performed'])
        unrelated = self.root / 'unrelated/session-two/portable'
        shutil.copytree(self.output, unrelated)
        shutil.rmtree(self.inputs)
        result = subprocess.run([sys.executable, str(Path(bundle.__file__).resolve()), 'check', str(unrelated)],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        checked = json.loads(result.stdout)
        self.assertTrue(checked['handoff_ready'])
        self.assertEqual(checked['budget_state']['remaining_calls'], 24)
        portable = json.loads((unrelated / 'project.json').read_text())
        self.assertTrue((unrelated / portable['approved_master']['file']).is_file())


    def playback_tree(self):
        tree = self.inputs / 'exports/loop-v1'
        for directory in ('sequence', 'styles/nested', 'empty'):
            (tree / directory).mkdir(parents=True)
        shutil.copyfile(self.inputs / 'master.png', tree / 'sequence/frame-0000.png')
        shutil.copyfile(self.inputs / 'pose.png', tree / 'sequence/frame-0001.png')
        (tree / 'styles/main.css').write_text('@import "nested/theme.css"; .a{background:url(../sequence/frame-0001.png?v=1#pixel)}')
        (tree / 'styles/nested/theme.css').write_text('.b{background:url("../../sequence/frame-0000.png")}')
        (tree / 'timing.json').write_bytes(b'{"unit":"milliseconds","durations":[17,283]}\n')
        (tree / 'playback.html').write_text('''<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="styles/main.css">
<img src="sequence/frame-0000.png"><a href="timing.json">Exact timing</a>
<a href="https://example.invalid/playback-help">Help</a>
<style>.inline{background:url(sequence/frame-0001.png)}</style>
<script type="application/json" id="timeline">{"frames":[{"file":"sequence/frame-0001.png","duration_ms":283}]}</script>
<script>fetch('timing.json'); throw new Error('Must never execute bundle support scripts');</script>
''', encoding='utf-8')
        self.spec['supports'].append({'directory': 'exports/loop-v1', 'role': 'playback',
                                      'entrypoint': 'playback.html', 'dependencies': ['timing.json']})
        return tree

    def test_playback_tree_relocates_exact_bytes_and_relative_links(self):
        tree = self.playback_tree()
        expected = {path.relative_to(tree).as_posix(): path.read_bytes() for path in tree.rglob('*') if path.is_file()}
        expected_directories = sorted(path.relative_to(tree).as_posix() for path in tree.rglob('*') if path.is_dir())
        report = self.create()
        support = self.manifest()['supports'][-1]
        self.assertEqual(support['directory'], 'support-trees/loop-v1')
        self.assertEqual(support['entrypoint'], 'playback.html')
        self.assertEqual(support['directories'], expected_directories)
        self.assertFalse(report['support_checks']['playback_execution_performed'])
        self.assertFalse(report['support_checks']['dynamic_dependencies_evaluated'])
        self.assertEqual(report['support_checks']['external_references_not_fetched'], 1)
        self.assertGreaterEqual(report['support_checks']['local_references_checked'], 8)
        unrelated = self.root / 'other-session/standalone'
        shutil.copytree(self.output, unrelated)
        shutil.rmtree(self.inputs)
        shutil.rmtree(self.output)
        result = subprocess.run([sys.executable, str(Path(bundle.__file__).resolve()), 'check', str(unrelated)],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        copied = unrelated / support['directory']
        self.assertEqual({path.relative_to(copied).as_posix(): path.read_bytes() for path in copied.rglob('*') if path.is_file()}, expected)
        self.assertTrue((copied / 'empty').is_dir())
        for path in copied.rglob('*'):
            if path.is_file():
                for reference in bundle.support_references(path):
                    bundle.validate_support_reference(copied, path, reference)
        inventory = json.loads((unrelated / 'bundle.json').read_text())['inventory']
        indexed = {entry['file']: entry for entry in inventory}
        for name, data in expected.items():
            entry = indexed[support['directory'] + '/' + name]
            self.assertEqual(entry['bytes'], len(data))
            self.assertEqual(entry['sha256'], sha256(copied / name))

    def test_generated_native_viewer_inline_json_dependencies_checked(self):
        from pixel_pipeline import render_html
        tree = self.playback_tree()
        render_html(tree, {'width': 8, 'height': 8, 'frames': [
            {'file': 'sequence/frame-0000.png', 'duration_ms': 17},
            {'file': 'sequence/frame-0001.png', 'duration_ms': 283}]}, 4)
        self.assertTrue(self.create()['handoff_ready'])
        shutil.rmtree(self.output)
        (tree / 'sequence/frame-0001.png').unlink()
        with self.assertRaisesRegex(bundle.BundleError, 'Missing support dependency'):
            self.create()

    def test_linking_support_file_requires_explicit_tree(self):
        for suffix in ('.html', '.HTML', '.htm', '.xhtml', '.css', '.js', '.mjs'):
            path = self.inputs / ('standalone' + suffix)
            path.write_text('<img src="master.png">')
            self.spec['supports'] = [{'file': 'request.txt', 'role': 'request'},
                                     {'file': path.name, 'role': 'playback'}]
            with self.subTest(suffix=suffix), self.assertRaisesRegex(bundle.BundleError, 'require support.directory'):
                self.create()
            self.assertFalse(self.output.exists())

    def test_unrelated_support_files_and_asset_paths_keep_hash_contract(self):
        self.create()
        original = self.manifest()
        shutil.rmtree(self.output)
        self.playback_tree()
        self.create()
        updated = self.manifest()
        self.assertEqual(original['assets'], updated['assets'])
        self.assertEqual(original['supports'], updated['supports'][:-1])
        request = updated['supports'][0]['file']
        self.assertEqual(request, 'evidence/' + sha256(self.inputs / 'request.txt')[:16] + '-request.txt')

    def test_support_tree_missing_dependencies_rejected(self):
        tree = self.playback_tree()
        original = (tree / 'playback.html').read_text()
        for content in ('<img src="missing.png">', '<a href="missing.json">timing</a>',
                        '<style>.a{background:url(missing.png)}</style>',
                        '<script>fetch("missing.json")</script>',
                        '<script type="application/json">{"frames":[{"file":"missing.png"}]}</script>'):
            (tree / 'playback.html').write_text(content)
            with self.subTest(content=content), self.assertRaisesRegex(bundle.BundleError, 'Missing support dependency'):
                self.create()
            self.assertFalse(self.output.exists())
        (tree / 'playback.html').write_text(original)
        self.spec['supports'][-1]['dependencies'].append('computed-at-runtime.json')
        with self.assertRaisesRegex(bundle.BundleError, 'Missing declared support dependency'):
            self.create()
        self.spec['supports'][-1]['dependencies'] = ['timing.json']
        self.spec['supports'][-1]['entrypoint'] = 'missing.html'
        with self.assertRaisesRegex(bundle.BundleError, 'Missing support entrypoint'):
            self.create()

    def test_support_tree_css_import_missing_rejected(self):
        tree = self.playback_tree()
        (tree / 'styles/nested/theme.css').unlink()
        with self.assertRaisesRegex(bundle.BundleError, 'Missing support dependency'):
            self.create()

    def test_support_tree_url_traversal_absolute_and_schemes_rejected(self):
        tree = self.playback_tree()
        bad = ('../request.txt', '../../request.txt', '%2e%2e/request.txt',
               '%252e%252e%252frequest.txt', '%2Fetc/passwd', '/etc/passwd',
               '..%5crequest.txt', 'file:///etc/passwd', 'javascript:alert(1)', '%00.png')
        for reference in bad:
            (tree / 'playback.html').write_text('<img src="' + reference + '">')
            with self.subTest(reference=reference), self.assertRaises(bundle.BundleError):
                self.create()
            self.assertFalse(self.output.exists())

    def test_nested_css_escaped_traversal_rejected(self):
        tree = self.playback_tree()
        (tree / 'styles/nested/theme.css').write_text(r'.a{background:url(\2e\2e/\2e\2e/\2e\2e/request.txt)}')
        with self.assertRaisesRegex(bundle.BundleError, 'escapes its declared tree'):
            self.create()

    def test_encoded_contained_relative_reference_preserves_bytes(self):
        tree = self.playback_tree()
        (tree / 'sequence/frame with space.png').write_bytes((tree / 'sequence/frame-0000.png').read_bytes())
        content = '<img src="sequence/frame%20with%20space.png?download=1#pixel">'
        (tree / 'playback.html').write_text(content)
        self.create()
        self.assertEqual((self.output / 'support-trees/loop-v1/playback.html').read_text(), content)

    def test_support_tree_source_path_and_metadata_traversal_rejected(self):
        self.playback_tree()
        for name in ('../inputs/exports/loop-v1', '/exports/loop-v1', 'exports/../exports/loop-v1',
                     'exports/%2e%2e/loop-v1', 'exports\\loop-v1', 'https://example.com/tree', '.', 'exports//loop-v1'):
            self.spec['supports'][-1]['directory'] = name
            with self.subTest(name=name), self.assertRaises(bundle.BundleError):
                self.create()
        self.spec['supports'][-1]['directory'] = 'exports/loop-v1'
        for key, value in (('entrypoint', '../request.txt'), ('dependencies', ['../request.txt']),
                           ('dependencies', [['invalid']])):
            original = copy.deepcopy(self.spec['supports'][-1])
            self.spec['supports'][-1][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(bundle.BundleError):
                self.create()
            self.spec['supports'][-1] = original

    def test_support_tree_symlink_members_and_source_ancestors_rejected(self):
        tree = self.playback_tree()
        for target in (tree / 'timing.json', self.inputs / 'request.txt', tree / 'sequence'):
            link = tree / 'linked'
            link.symlink_to(target)
            with self.subTest(target=target), self.assertRaisesRegex(bundle.BundleError, 'Symlinks'):
                self.create()
            link.unlink()
        (self.inputs / 'alias').symlink_to(tree.parent, target_is_directory=True)
        self.spec['supports'][-1]['directory'] = 'alias/loop-v1'
        with self.assertRaisesRegex(bundle.BundleError, 'Symlinks'):
            self.create()

    def test_support_tree_special_file_and_nonportable_member_rejected(self):
        tree = self.playback_tree()
        fifo = tree / 'stream'
        os.mkfifo(fifo)
        with self.assertRaisesRegex(bundle.BundleError, 'Only regular support'):
            self.create()
        fifo.unlink()
        (tree / '%2e%2e').write_text('literal encoded path')
        with self.assertRaisesRegex(bundle.BundleError, 'encoded path'):
            self.create()

    def test_support_tree_duplicate_and_casefold_destinations_rejected(self):
        tree = self.playback_tree()
        self.spec['supports'].append(copy.deepcopy(self.spec['supports'][-1]))
        with self.assertRaisesRegex(bundle.BundleError, 'Conflicting support tree destinations'):
            self.create()
        self.spec['supports'].pop()
        other = self.inputs / 'other/LOOP-v1'
        shutil.copytree(tree, other)
        self.spec['supports'].append({'directory': 'other/LOOP-v1', 'role': 'other'})
        with self.assertRaisesRegex(bundle.BundleError, 'Conflicting support tree destinations'):
            self.create()
        self.spec['supports'].pop()
        (tree / 'TIMING.json').write_text('{}')
        with self.assertRaisesRegex(bundle.BundleError, 'Conflicting support tree destinations'):
            self.create()

    def test_support_tree_output_inside_source_rejected_without_recursion(self):
        tree = self.playback_tree()
        self.output = tree / 'new-parent/bundle'
        with self.assertRaisesRegex(bundle.BundleError, 'Output cannot be inside'):
            self.create()
        self.assertFalse((tree / 'new-parent').exists())
        alias = self.root / 'source-alias'
        alias.symlink_to(tree, target_is_directory=True)
        self.output = alias / 'bundle'
        with self.assertRaisesRegex(bundle.BundleError, 'Output cannot be inside'):
            self.create()

    def test_support_tree_bounds_reject_without_retaining_output(self):
        self.playback_tree()
        for constant, maximum in (('MAX_SUPPORT_ENTRIES', 2), ('MAX_SUPPORT_FILE_BYTES', 32),
                                  ('MAX_SUPPORT_BYTES', 100), ('MAX_SUPPORT_TEXT_BYTES', 10)):
            with self.subTest(constant=constant), patch.object(bundle, constant, maximum):
                with self.assertRaisesRegex(bundle.BundleError, 'safety limit'):
                    self.create()
                self.assertFalse(self.output.exists())

    def test_support_tree_empty_directory_inventory_and_manifest_collisions(self):
        self.playback_tree()
        self.create()
        (self.output / 'support-trees/loop-v1/empty').rmdir()
        with self.assertRaisesRegex(bundle.BundleError, 'directory inventory'):
            bundle.check_bundle(self.output)
        (self.output / 'support-trees/loop-v1/empty').mkdir()
        self.mutate_manifest(lambda m: m['supports'].append(copy.deepcopy(m['supports'][-1])))
        with self.assertRaisesRegex(bundle.BundleError, 'Conflicting support tree destinations'):
            bundle.check_bundle(self.output)

    def test_support_tree_does_not_copy_external_siblings(self):
        self.playback_tree()
        (self.inputs / 'exports/private-sibling.txt').write_text('Not in the declared tree')
        self.create()
        self.assertFalse(any(path.name == 'private-sibling.txt' for path in self.output.rglob('*')))

    def test_support_record_ambiguous_or_overridden_destination_rejected(self):
        self.playback_tree()
        for change in ({'file': 'request.txt'}, {'destination': 'assets'}, {'target': 'assets'}, {'directories': []}):
            original = copy.deepcopy(self.spec['supports'][-1])
            self.spec['supports'][-1].update(change)
            with self.subTest(change=change), self.assertRaises(bundle.BundleError):
                self.create()
            self.spec['supports'][-1] = original

    def test_support_html_base_and_duplicate_attributes_rejected(self):
        tree = self.playback_tree()
        for content in ('<base href="../"><img src="request.txt">', '<img src="missing.png" src="timing.json">'):
            (tree / 'playback.html').write_text(content)
            with self.subTest(content=content), self.assertRaises(bundle.BundleError):
                self.create()

    def test_study_never_becomes_visual_acceptance_from_valid_png(self):
        self.spec.update({'status': 'study', 'technical_status': 'unverified', 'visual_status': 'unverified'})
        for asset in self.spec['assets']:
            asset.update({'status': 'study', 'technical_status': 'unverified', 'visual_status': 'unverified', 'approval': None})
        report = self.create()
        self.assertFalse(report['handoff_ready'])
        self.assertEqual(report['recorded_visual_status'], 'unverified')
        self.assertFalse(report['visual_judgment_performed'])

    def test_wrong_dimensions_in_spec_rejected(self):
        self.spec['assets'][1]['dimensions_px'] = [64, 64]
        with self.assertRaisesRegex(bundle.BundleError, 'wrong dimensions'):
            self.create()
        self.assertFalse(self.output.exists())

    def test_invalid_actual_native_dimensions_rejected(self):
        png(self.inputs / 'master.png', 16, 16)
        self.spec['assets'][1]['approval']['asset_sha256'] = sha256(self.inputs / 'master.png')
        self.spec['assets'][1]['approval']['source_sha256'] = sha256(self.inputs / 'master.png')
        with self.assertRaisesRegex(bundle.BundleError, 'artifact canvas'):
            self.create()

    def test_hash_stale_on_disk_rejected(self):
        self.create()
        asset = self.manifest()['assets'][0]
        (self.output / asset['file']).write_bytes(b'wrong bytes')
        with self.assertRaisesRegex(bundle.BundleError, 'Stale hash'):
            bundle.check_bundle(self.output)

    def test_wrong_asset_hash_even_with_inventory_intact_rejected(self):
        self.create()
        self.mutate_manifest(lambda m: m['assets'][0].update({'sha256': '0' * 64}))
        with self.assertRaisesRegex(bundle.BundleError, 'sha256'):
            bundle.check_bundle(self.output)

    def test_missing_file_and_extra_file_rejected(self):
        self.create()
        (self.output / 'unlisted.txt').write_text('unexpected')
        with self.assertRaisesRegex(bundle.BundleError, 'inventory'):
            bundle.check_bundle(self.output)
        (self.output / 'unlisted.txt').unlink()
        (self.output / self.manifest()['assets'][0]['file']).unlink()
        with self.assertRaises(ValueError):
            bundle.check_bundle(self.output)

    def test_path_escape_and_symlink_rejected(self):
        self.spec['assets'][0]['file'] = '../elsewhere.png'
        with self.assertRaises(ValueError):
            self.create()
        self.spec['assets'][0]['file'] = 'identity.png'
        self.create()
        (self.output / 'outside-link').symlink_to(self.inputs / 'identity.png')
        with self.assertRaisesRegex(bundle.BundleError, 'Symlink'):
            bundle.check_bundle(self.output)

    def test_accepted_requires_actual_approval_hash_and_delegation(self):
        original = copy.deepcopy(self.spec)
        for patch in (None, {'actor': 'assistant'}, {'actor': 'user', 'role': 'view'},
                      {**self.spec['assets'][1]['approval'], 'asset_sha256': 'f' * 64},
                      {k: v for k, v in self.spec['assets'][1]['approval'].items() if k != 'delegation_file'}):
            self.spec = copy.deepcopy(original)
            self.spec['assets'][1]['approval'] = patch
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.create()

    def test_accepted_requires_separate_visual_gate(self):
        self.spec['assets'][1]['visual_status'] = 'unverified'
        with self.assertRaisesRegex(bundle.BundleError, 'separate technical pass'):
            self.create()

    def animation(self):
        self.spec['stage'] = 'animation'
        self.spec['assets'].extend([self.asset('rest', 'master.png', 'pose'), self.asset('contact', 'pose.png', 'pose')])
        self.spec['required_assets'] += ['rest', 'contact']
        self.spec['timeline'] = [{'pose_id': 'rest', 'duration_ms': 100}, {'pose_id': 'contact', 'duration_ms': 200}]

    def test_valid_animation_timeline_and_missing_pose(self):
        self.animation()
        self.spec['timeline'][1]['pose_id'] = 'absent'
        with self.assertRaisesRegex(bundle.BundleError, 'missing pose'):
            self.create()
        self.spec['timeline'][1]['pose_id'] = 'contact'
        self.assertTrue(self.create()['handoff_ready'])

    def test_role_consistency(self):
        self.spec['assets'][1]['role'] = 'identity'
        with self.assertRaisesRegex(bundle.BundleError, 'role'):
            self.create()

    def test_set_palette_grid_and_anchor_consistency(self):
        self.animation()
        original = copy.deepcopy(self.spec)
        changes = [({'palette': ['#000000', '#ffffff', '#ff0000']}, 'set'),
                   ({'anchor_px': [3, 6]}, 'anchor'),
                   ({'grid': {'source_canvas_px': [8, 8], 'crop': [1, 1, 6, 6]}}, 'set'),
                   ({'grid_px': 2}, 'grid')]
        for changes, message in changes:
            self.spec = copy.deepcopy(original)
            self.spec['assets'][-1]['native'].update(changes)
            with self.subTest(changes=changes), self.assertRaisesRegex(bundle.BundleError, message):
                self.create()

    def test_equivalent_source_sizes_share_native_grid_unless_strict_lock(self):
        self.animation()
        png(self.inputs / 'larger-source.png', 16, 16, alternate=True)
        pose = self.spec['assets'][-1]
        pose['source']['file'] = 'larger-source.png'
        pose['approval']['source_sha256'] = sha256(self.inputs / 'larger-source.png')
        pose['native']['grid']['source_canvas_px'] = [16, 16]
        self.assertTrue(self.create()['handoff_ready'])
        shutil.rmtree(self.output)
        for asset in self.spec['assets']:
            if 'native' in asset:
                asset['native']['grid']['lock_source_geometry'] = True
        with self.assertRaisesRegex(bundle.BundleError, 'set'):
            self.create()

    def test_identity_study_requires_actual_native_preview(self):
        png(self.inputs / 'identity.png', 16, 16)
        asset = self.spec['assets'][0]
        asset['approval']['asset_sha256'] = asset['approval']['source_sha256'] = sha256(self.inputs / 'identity.png')
        with self.assertRaisesRegex(bundle.BundleError, 'artifact canvas'):
            self.create()

    def test_required_master_role_cannot_be_faked_by_identity(self):
        self.spec['required_assets'] = ['identity']
        with self.assertRaisesRegex(bundle.BundleError, 'roles'):
            self.create()

    def test_view_is_optional_unless_view_stage_requested(self):
        self.spec['stage'] = 'views'
        with self.assertRaisesRegex(bundle.BundleError, 'roles'):
            self.create()

    def test_source_dimensions_cannot_be_claimed_native(self):
        self.spec['assets'][0]['source']['dimensions_px'] = [64, 64]
        with self.assertRaisesRegex(bundle.BundleError, 'source dimensions'):
            self.create()

    def test_budget_counts_failed_calls_total_and_per_pose_across_stages(self):
        attempts = [{'attempt_id': 'a1', 'stage': 'identity', 'pose_id': 'one', 'repair_of': None, 'outcome': 'failed'},
                    {'attempt_id': 'a2', 'stage': 'refinement', 'pose_id': 'one', 'repair_of': 'a1', 'outcome': 'failed'},
                    {'attempt_id': 'a3', 'stage': 'animation', 'pose_id': 'one', 'repair_of': 'a2', 'outcome': 'cancelled'}]
        write(self.inputs / 'budget.json', {'attempts': attempts})
        report = self.create()
        self.assertEqual(report['budget_state']['attempted_calls'], 3)
        self.assertEqual(report['budget_state']['remaining_repairs_total'], 4)
        self.assertEqual(report['budget_state']['remaining_repairs_by_pose']['one'], 0)

    def test_budget_exhaustion_and_pending_handoff_rejected(self):
        attempts = [{'attempt_id': 'a1', 'stage': 'identity', 'pose_id': 'one', 'repair_of': None, 'outcome': 'pending'}]
        write(self.inputs / 'budget.json', {'attempts': attempts})
        with self.assertRaisesRegex(bundle.BundleError, 'unfinished generation'):
            self.create()
        attempts[0]['outcome'] = 'success'
        for i in range(2, 5):
            attempts.append({'attempt_id': f'a{i}', 'stage': 'different', 'pose_id': 'one', 'repair_of': f'a{i-1}', 'outcome': 'failed'})
        write(self.inputs / 'budget.json', {'attempts': attempts})
        with self.assertRaisesRegex(bundle.BundleError, 'pose repair'):
            self.create()

    def test_stale_budget_counter_rejected(self):
        self.create()
        self.mutate_manifest(lambda m: m['budget_state'].update({'remaining_calls': 999}))
        with self.assertRaisesRegex(bundle.BundleError, 'Budget counters'):
            bundle.check_bundle(self.output)

    def test_complete_open_run_can_continue_after_unrelated_copy(self):
        import run_ledger as ledger
        skill = self.inputs / 'synthetic-skill'
        skill.mkdir()
        (skill / 'SKILL.md').write_text('# Synthetic skill')
        (skill / 'empty-directory').mkdir()
        run = self.inputs / 'run-original'
        ledger.init_run(run, [('synthetic', skill)], self.inputs / 'request.txt',
                        {'max_attempts': 24, 'max_new_poses': 8, 'max_stage_repairs': 6, 'max_pose_repairs': 2,
                         'max_total_repairs': 6})
        self.spec['run_directory'] = 'run-original'
        report = self.create()
        self.assertEqual(report['continuation_mode'], 'same_run')
        unrelated = self.root / 'unrelated'
        shutil.copytree(self.output, unrelated)
        self.assertTrue(bundle.check_bundle(unrelated)['handoff_ready'])
        parameters = unrelated / 'next-parameters.json'
        parameters.write_text('{}')
        next_prompt = unrelated / 'next-prompt.txt'
        next_prompt.write_text('Synthetic authorized next-step test only')
        result = ledger.generation_start(unrelated / 'run', 'animation', 'next', 'synthetic', next_prompt, parameters)
        self.assertEqual(result['remaining_attempts'], 23)
        # Old immutable bundle inventory is now stale; create a NEW bundle at next gate.
        with self.assertRaisesRegex(bundle.BundleError, 'Stale hash|inventory'):
            bundle.check_bundle(unrelated)

    def test_run_budget_mismatch_cannot_reset(self):
        import run_ledger as ledger
        skill = self.inputs / 'skill'
        skill.mkdir()
        (skill / 'SKILL.md').write_text('fixture')
        ledger.init_run(self.inputs / 'run', [('test', skill)], self.inputs / 'request.txt',
                        {'max_attempts': 999, 'max_new_poses': 8, 'max_stage_repairs': 6, 'max_pose_repairs': 2, 'max_total_repairs': 6})
        self.spec['run_directory'] = 'run'
        with self.assertRaisesRegex(bundle.BundleError, 'conflicts with project'):
            self.create()


if __name__ == '__main__':
    unittest.main()
