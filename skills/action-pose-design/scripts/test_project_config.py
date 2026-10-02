#!/usr/bin/env python3
"""Synthetic contract tests; no generation or project mutation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import project_config as config


def project_fixture():
    return {'schema_version': '3.0', 'asset_id': 'synthetic', 'brief': 'Fixture only',
            'profile': 'profile.json', 'native_canvas_px': [8, 8], 'anchor_px': [4, 6],
            'limits': {'palette_max': 4, 'binary_alpha': True, 'min_margin': 1},
            'budget': {'max_calls': 24, 'max_total_repairs': 6, 'repairs_per_pose': 2},
            'animation': {'mode': 'full_body', 'duration_ms': 300, 'max_unique_drawings': 3,
                          'max_timeline_entries': 4, 'min_unique_drawings': 2}}


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'project.json'
        (self.root / 'profile.json').write_text('{"identity":{"palette_roles":{"outline":"#000000"}}}')
        self.project = project_fixture()
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.project))

    def test_load_keeps_original_fields_and_hashes(self):
        loaded = config.load_project(self.path)
        self.assertEqual(loaded['brief'], self.project['brief'])
        self.assertEqual(loaded['_meta']['project_sha256'], config.sha256(self.path))
        self.assertIn('identity', loaded['_meta']['profile_data'])

    def test_legacy_has_no_implicit_animation(self):
        self.project['schema_version'] = '2.0'
        del self.project['animation']
        self.save()
        merged = config.enforce_manifest({}, self.path)
        self.assertNotIn('animation_mode', merged)
        self.assertEqual(merged['constraints'], {})

    def test_merge_inherits_without_mutating(self):
        original = {'frames': [{'file': 'one.png', 'duration_ms': 100},
                               {'file': 'two.png', 'duration_ms': 200}]}
        merged = config.enforce_manifest(original, self.path)
        self.assertNotIn('width', original)
        self.assertEqual(merged['width'], 8)
        self.assertEqual(merged['animation_mode'], 'full_body')
        self.assertEqual(merged['constraints']['max_distinct_drawing_count'], 3)
        self.assertEqual(merged['project_provenance']['project_sha256'], config.sha256(self.path))

    def test_explicit_stricter_and_weaker_bounds_rejected(self):
        for field, values in [('palette_max', (2, 8)), ('width', (4, 16)), ('min_margin', (0, 2))]:
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(config.ProjectError):
                    config.enforce_manifest({field: value}, self.path)
        for value in (2, 4):
            with self.assertRaises(config.ProjectError):
                config.enforce_manifest({'constraints': {'max_distinct_drawing_count': value}}, self.path)

    def test_exact_counts_compared_to_not_equated_with_bounds(self):
        merged = config.enforce_manifest({'constraints': {'distinct_drawing_count': 2,
                                                          'timeline_frame_count': 3}}, self.path)
        self.assertEqual(merged['constraints']['distinct_drawing_count'], 2)
        for value in (1, 4):
            with self.assertRaises(config.ProjectError):
                config.enforce_manifest({'constraints': {'distinct_drawing_count': value}}, self.path)

    def test_actual_duration_and_timeline_size(self):
        for frames in ([{'duration_ms': 50}] * 5, [{'duration_ms': 100}]):
            with self.assertRaises(config.ProjectError):
                config.enforce_manifest({'frames': frames}, self.path)

    def test_normalization_all_inherit_and_conflicts(self):
        result = config.enforce_normalization(self.path)
        self.assertEqual((result['width'], result['height'], result['colors']), (8, 8, 4))
        self.assertEqual(result['anchor_px'], [4, 6])
        for args in ({'width': 4}, {'height': 16}, {'colors': 2}, {'colors': '4'}):
            with self.assertRaises(config.ProjectError):
                config.enforce_normalization(self.path, **args)

    def test_invalid_project_never_relaxes(self):
        patches = [('native_canvas_px', [8, True]), ('limits', {'palette_max': 4, 'binary_alpha': False, 'min_margin': 1}),
                   ('budget', {'max_calls': -1}), ('profile', '../profile.json'), ('anchor_px', [8, 4]),
                   ('animation', {'mode': 'unknown'})]
        original = copy.deepcopy(self.project)
        for key, value in patches:
            self.project = copy.deepcopy(original)
            self.project[key] = value
            self.save()
            with self.subTest(key=key), self.assertRaises(config.ProjectError):
                config.load_project(self.path)

    def test_stale_manifest_project_hash_rejected(self):
        first = config.enforce_manifest({}, self.path)
        self.project['brief'] = 'Changed user requirement'
        self.save()
        with self.assertRaises(config.ProjectError):
            config.enforce_manifest(first, self.path)

    def test_explicit_static_scope_skips_future_animation_only(self):
        merged = config.enforce_manifest({'scope': 'static', 'frames': [{'file': 'one.png', 'duration_ms': 10}]}, self.path)
        self.assertEqual(merged['width'], 8)
        self.assertEqual(merged['palette_max'], 4)
        self.assertNotIn('animation_mode', merged)
        self.assertEqual(merged['constraints'], {})
        for forbidden in ({'animation_mode': 'full_body'}, {'motion_regions': []}, {'constraints': {'total_duration_ms': 300}}):
            with self.assertRaises(config.ProjectError):
                config.enforce_manifest({'scope': 'static', **forbidden}, self.path)

    def test_duplicate_keys_rejected(self):
        self.path.write_text('{"schema_version":"3.0","schema_version":"2.0"}')
        with self.assertRaises(config.ProjectError):
            config.load_project(self.path)


if __name__ == '__main__':
    unittest.main()
