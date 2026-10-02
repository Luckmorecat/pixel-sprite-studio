#!/usr/bin/env python3
"""Synthetic local coverage contracts and review aids; fixtures are not real artwork."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import pixel_pipeline as pipeline
import local_motion_review as review_tool
import motion_support as motion
from test_pixel_pipeline import write_rgba_fixture


def rect(x, y, width=1, height=1):
    return {'x': x, 'y': y, 'width': width, 'height': height}


@unittest.skipUnless(shutil.which('magick') or shutil.which('convert'), 'ImageMagick required')
class LocalMotionReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='local-coverage-tests-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.master = self.root / 'master.png'
        self.candidate = self.root / 'candidate.png'
        self.plan = self.root / 'plan.json'
        self.raw = [(17, 23, 31, 0)] * 64
        for x in range(1, 7):
            self.raw[3 * 8 + x] = (225, 180, 60, 255)
        write_rgba_fixture(self.master, 8, 8, self.raw)
        self.spec = {'schema_version': 2, 'animation_mode': 'local',
                     'motion_regions': [rect(3, 2, 4, 3)],
                     'original_moving_regions': [rect(3, 3, 4, 1)],
                     'motion_envelope_regions': [rect(3, 2, 4, 3)],
                     'vacated_regions': [rect(4, 3, 2, 1)]}
        self.mi, _ = pipeline.decode_png(self.master)

    def save(self):
        self.plan.write_text(json.dumps(self.spec))

    def coverage(self, require_review=False):
        return motion.local_coverage(self.spec, self.mi, 8, 8, self.root, pipeline.decode_png,
                                     require_v2=True, require_review=require_review)

    def accept(self):
        result, errors, _ = self.coverage()
        self.assertEqual(errors, [])
        self.spec['coverage_review'] = {'status': 'passed', 'master_sha256': self.mi['file_sha256'],
                                        'contract_sha256': result['contract_sha256'],
                                        'notes': 'Synthetic fixture assertion only; no semantic identity claim'}
        self.save()

    def mask(self, name, cells):
        path = self.root / name
        write_rgba_fixture(path, 8, 8, [(255, 255, 255, 255) if i in cells else (0, 0, 0, 255) for i in range(64)])
        return path

    def test_each_declared_footprint_undercoverage_reports_measured_counts(self):
        for kind in motion.COVERAGE_PARTS:
            with self.subTest(kind=kind):
                saved = copy.deepcopy(self.spec)
                self.spec[kind + '_regions'] = [rect(1, 1, 2, 1)]
                result, errors, _ = self.coverage()
                self.assertEqual(result['measurements'][kind]['uncovered_pixels'], 2)
                self.assertEqual(result['measurements'][kind]['uncovered_coordinates_sample'], [[1, 1], [2, 1]])
                self.assertTrue(any(kind + ': 2 of 2' in error for error in errors))
                self.assertIn('before lock', '\n'.join(errors))
                self.assertEqual(result['status'], 'failed')
                self.spec = saved

    def test_declaration_masks_and_explicit_shaped_intersections(self):
        active = {19, 20, 27, 28, 35}
        self.mask('selection.png', active | {0})
        self.spec['motion_regions'] = [rect(2, 2, 3, 3)]
        self.spec['motion_mask'] = 'selection.png'
        self.spec['mask_semantics'] = 'intersection'
        for kind, cells in [('original_moving', {27, 28}), ('motion_envelope', active), ('vacated', {28})]:
            del self.spec[kind + '_regions']
            self.mask(kind + '.png', cells)
            self.spec[kind + '_mask'] = kind + '.png'
        result, errors, _ = self.coverage()
        self.assertEqual(errors, [])
        self.assertEqual(result['selected_pixels'], 5)
        self.assertEqual(result['selection_mask']['semantics'], 'intersection')
        self.assertEqual(len(result['declaration_masks']), 3)
        self.spec['original_moving_regions'] = [rect(3, 3, 2, 1)]
        with self.assertRaisesRegex(ValueError, 'original_moving_mask_semantics: intersection'):
            self.coverage()
        self.spec['original_moving_mask_semantics'] = 'intersection'
        self.assertEqual(self.coverage()[1], [])

    def test_effective_intersection_not_rectangle_union_controls_containment(self):
        self.mask('tiny.png', {27})
        self.spec.update(motion_mask='tiny.png', mask_semantics='intersection')
        result, errors, _ = self.coverage()
        self.assertEqual(result['selected_pixels'], 1)
        self.assertEqual(result['measurements']['original_moving']['uncovered_pixels'], 3)
        self.assertEqual(result['measurements']['motion_envelope']['uncovered_pixels'], 11)
        self.assertEqual(result['measurements']['vacated']['uncovered_pixels'], 2)
        self.assertEqual(len(errors), 3)

    def test_mask_undercoverage_is_measured_even_for_full_canvas_declaration(self):
        self.mask('whole.png', set(range(64)))
        del self.spec['original_moving_regions']
        self.spec['original_moving_mask'] = 'whole.png'
        result, errors, _ = self.coverage()
        self.assertEqual(result['measurements']['original_moving']['uncovered_pixels'], 52)
        self.assertTrue(errors)

    def test_v2_requires_all_three_declarations_and_explicit_empty_vacated_is_valid(self):
        self.spec.pop('vacated_regions')
        with self.assertRaisesRegex(ValueError, 'requires vacated_regions or vacated_mask'):
            self.coverage()
        self.spec['vacated_regions'] = []
        self.assertEqual(self.coverage()[1], [])
        self.spec['original_moving_regions'] = []
        with self.assertRaisesRegex(ValueError, 'original_moving declaration must be nonempty'):
            self.coverage()

    def test_coverage_contract_review_not_auto_passed_and_not_self_referential(self):
        first, errors, _ = self.coverage()
        self.assertEqual(errors, [])
        self.assertEqual(first['visual_status'], 'unreviewed')
        self.assertTrue(self.coverage(require_review=True)[1])
        self.accept()
        second, errors, _ = self.coverage(require_review=True)
        self.assertEqual(errors, [])
        self.assertEqual(first['contract_sha256'], second['contract_sha256'])
        self.spec['coverage_review']['notes'] += '; additional reviewer detail'
        self.assertEqual(first['contract_sha256'], self.coverage()[0]['contract_sha256'])

    def test_hash_binding_rejects_master_region_anchor_and_mask_drift(self):
        self.accept()
        accepted = copy.deepcopy(self.spec)
        for field in ['motion_regions', 'original_moving_regions', 'motion_envelope_regions', 'vacated_regions', 'anchor_regions']:
            with self.subTest(field=field):
                self.spec = copy.deepcopy(accepted)
                self.spec[field] = [rect(3, 3)]
                with self.assertRaisesRegex(ValueError, 'hashes do not match'):
                    self.coverage(require_review=True)
        self.spec = copy.deepcopy(accepted)
        self.mi['file_sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'hashes do not match'):
            self.coverage(require_review=True)
        self.mi, _ = pipeline.decode_png(self.master)
        self.spec.pop('coverage_review')
        self.mask('selection.png', {y * 8 + x for y in range(2, 5) for x in range(3, 7)})
        self.spec['motion_mask'] = 'selection.png'
        self.spec['mask_semantics'] = 'intersection'
        self.accept()
        self.mask('selection.png', {y * 8 + x for y in range(2, 5) for x in range(3, 7)} | {0})
        # Effective cells are unchanged, but the declared mask file changed.
        with self.assertRaisesRegex(ValueError, 'hashes do not match'):
            self.coverage(require_review=True)

    def test_declared_mask_hash_drift_and_nonbinary_masks_fail(self):
        mask = self.mask('source.png', {27, 28, 29, 30})
        self.spec.pop('original_moving_regions')
        self.spec.update(original_moving_mask='source.png', original_moving_mask_sha256=motion.sha(mask))
        self.mask('source.png', {27})
        with self.assertRaisesRegex(ValueError, 'hash differs from predeclared'):
            self.coverage()
        self.spec.pop('original_moving_mask_sha256')
        pixels = [(0, 0, 0, 255)] * 64
        pixels[27] = (128, 128, 128, 255)
        write_rgba_fixture(mask, 8, 8, pixels)
        with self.assertRaisesRegex(ValueError, 'only opaque binary'):
            self.coverage()

    def test_assembly_requires_review_and_rejects_undercoverage_without_outputs(self):
        write_rgba_fixture(self.candidate, 8, 8, self.raw)
        self.save()
        output = self.root / 'frame.png'
        with self.assertRaisesRegex(ValueError, 'requires passed coverage_review'):
            motion.assemble(self.master, self.candidate, output, self.plan)
        self.assertFalse(output.exists())
        self.spec['original_moving_regions'] = [rect(1, 3, 6, 1)]
        self.save()
        with self.assertRaisesRegex(ValueError, 'original_moving: 2 of 6'):
            motion.assemble(self.master, self.candidate, output, self.plan)
        self.assertFalse(output.exists())

    def test_exact_composition_overwrites_rgba_and_erases_alpha_without_touching_source(self):
        self.accept()
        other = list(self.raw)
        other[27] = (72, 11, 99, 0)
        other[19] = (18, 237, 31, 255)
        other[0] = (1, 2, 3, 255)
        write_rgba_fixture(self.candidate, 8, 8, other)
        before = self.master.read_bytes()
        candidate_before = self.candidate.read_bytes()
        output = self.root / 'frame.png'
        report = motion.assemble(self.master, self.candidate, output, self.plan)
        _, composed = pipeline.decode_png(output)
        active, _ = motion.selection(self.spec, 8, 8, self.root, pipeline.decode_png)
        for i in range(64):
            self.assertEqual(composed[i * 4:i * 4 + 4], bytes(other[i] if i in active else self.raw[i]))
        self.assertEqual(composed[27 * 4:27 * 4 + 4], bytes((72, 11, 99, 0)))
        self.assertEqual(report['visual_status'], 'unreviewed')
        self.assertEqual(self.master.read_bytes(), before)
        self.assertEqual(self.candidate.read_bytes(), candidate_before)

    def test_legacy_assembly_still_works_but_coverage_is_unverified(self):
        self.plan.write_text(json.dumps([rect(3, 3)]))
        write_rgba_fixture(self.candidate, 8, 8, self.raw)
        result = motion.assemble(self.master, self.candidate, self.root / 'legacy.png', self.plan)
        self.assertEqual(result['coverage_contract']['status'], 'legacy_unverified')
        with self.assertRaisesRegex(ValueError, 'schema_version 2 object'):
            review_tool.review(self.master, self.plan, self.root / 'legacy-review')

    def test_full_body_rejected_by_local_helper_without_adding_static_locks(self):
        self.spec['animation_mode'] = 'full_body'
        self.save()
        with self.assertRaisesRegex(ValueError, 'full_body has no static lock'):
            review_tool.review(self.master, self.plan, self.root / 'full-body')
        self.assertFalse((self.root / 'full-body').exists())

    def test_preflight_previews_exact_cells_backgrounds_nn_and_source_immutability(self):
        self.save()
        before = {p: p.read_bytes() for p in [self.master, self.plan]}
        out = self.root / 'preflight'
        result = review_tool.review(self.master, self.plan, out, scale=3)
        self.assertTrue(result['technical_pass'])
        self.assertFalse(result['automatic_visual_acceptance'])
        self.assertEqual(result['visual_status'], 'unreviewed')
        _, native = pipeline.decode_png(out / 'master-native.png')
        self.assertEqual(native, b''.join(bytes(p) for p in self.raw))
        _, enlarged = pipeline.decode_png(out / 'master-nn.png')
        for y in range(24):
            for x in range(24):
                self.assertEqual(enlarged[(y * 24 + x) * 4:(y * 24 + x + 1) * 4], bytes(self.raw[y // 3 * 8 + x // 3]))
        for background in review_tool.BACKGROUNDS:
            _, rendered = pipeline.decode_png(out / f'adjacent-{background}-native.png')
            for i, pixel in enumerate(self.raw):
                if pixel[3]:
                    self.assertEqual(rendered[i * 4:i * 4 + 4], bytes(pixel))
            self.assertTrue((out / f'coverage-{background}-nn.png').exists())
        self.assertEqual(pipeline.decode_png(out / 'adjacent-white-native.png')[1][:4], b'\xff\xff\xff\xff')
        self.assertEqual(pipeline.decode_png(out / 'adjacent-dark-native.png')[1][:4], bytes((24, 24, 24, 255)))
        self.assertEqual(pipeline.decode_png(out / 'adjacent-high-contrast-native.png')[1][:4], bytes((255, 0, 255, 255)))
        for p, data in before.items():
            self.assertEqual(p.read_bytes(), data)
        with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
            review_tool.review(self.master, self.plan, out, scale=3)
        self.assertEqual(json.loads((out / 'review.json').read_text()), result)

    def test_undercoverage_cli_returns_failure_and_immutable_review_evidence(self):
        self.spec['original_moving_regions'] = [rect(1, 3, 6, 1)]
        self.save()
        out = self.root / 'failed-preflight'
        result = subprocess.run([sys.executable, str(Path(review_tool.__file__)), 'preflight',
                                 '--master', str(self.master), '--regions', str(self.plan),
                                 '--output', str(out), '--scale', '2'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report['technical_pass'])
        self.assertEqual(report['coverage_contract']['measurements']['original_moving']['uncovered_pixels'], 2)
        self.assertTrue((out / 'coverage-white-native.png').exists())
        before = (out / 'review.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
            review_tool.review(self.master, self.plan, out)
        self.assertEqual((out / 'review.json').read_bytes(), before)

    def test_detached_fragment_alert_is_not_semantic_guarantee_or_automatic_repair(self):
        # Incomplete declared anatomy is intentionally not discoverable from schema.
        self.spec.update(motion_regions=[rect(3, 3, 2, 1)], original_moving_regions=[rect(3, 3, 2, 1)],
                         motion_envelope_regions=[rect(3, 3, 2, 1)], vacated_regions=[rect(3, 3, 2, 1)])
        self.accept()
        other = list(self.raw)
        other[27] = other[28] = (17, 23, 31, 0)
        write_rgba_fixture(self.candidate, 8, 8, other)
        before = self.candidate.read_bytes()
        result = review_tool.review(self.master, self.plan, self.root / 'comparison', self.candidate, scale=2)
        self.assertTrue(result['technical_pass'])
        self.assertEqual(result['visual_status'], 'unreviewed')
        self.assertFalse(result['automatic_visual_acceptance'])
        self.assertEqual(result['diagnostics']['alpha_erased_pixels'], 2)
        self.assertEqual(result['diagnostics']['components']['master_count'], 1)
        self.assertEqual(result['diagnostics']['components']['candidate_count'], 2)
        self.assertTrue(result['diagnostics']['components']['possible_retained_source_fragments'])
        self.assertTrue(any('alert, not a semantic diagnosis' in warning for warning in result['warnings']))
        self.assertEqual(self.candidate.read_bytes(), before)
        _, adjacent = pipeline.decode_png(self.root / 'comparison' / 'adjacent-white-native.png')
        master_render = review_tool.on_background(b''.join(bytes(p) for p in self.raw), 8, 8, 'white')
        candidate_render = review_tool.on_background(b''.join(bytes(p) for p in other), 8, 8, 'white')
        self.assertEqual(adjacent, review_tool.adjacent([master_render, candidate_render], 8, 8))

    def test_compare_rejects_outside_selection_drift_with_count(self):
        self.accept()
        other = list(self.raw)
        other[0] = (10, 20, 30, 255)
        write_rgba_fixture(self.candidate, 8, 8, other)
        result = review_tool.review(self.master, self.plan, self.root / 'outside', self.candidate, scale=1)
        self.assertFalse(result['technical_pass'])
        self.assertEqual(result['diagnostics']['changed_pixels_outside_selection'], 1)
        self.assertTrue(any('do not expand the mask after drift' in error for error in result['errors']))

    def test_no_component_alert_still_does_not_establish_visual_acceptance(self):
        raw = b''.join(bytes(p) for p in self.raw)
        result, warnings = review_tool.delta_diagnostics(raw, raw, 8, 8, {27})
        self.assertEqual(warnings, [])
        self.assertIn('no alert does not establish identity or coverage', result['limitation'])

    def test_neighbor_comparison_keeps_original_master_binding_and_exact_order(self):
        self.accept()
        neighbor = self.root / 'neighbor.png'
        neighbor_pixels, candidate_pixels = list(self.raw), list(self.raw)
        neighbor_pixels[27] = (4, 5, 6, 0)
        candidate_pixels[28] = (3, 2, 1, 0)
        write_rgba_fixture(neighbor, 8, 8, neighbor_pixels)
        write_rgba_fixture(self.candidate, 8, 8, candidate_pixels)
        before = {p: p.read_bytes() for p in (self.master, neighbor, self.candidate, self.plan)}
        out = self.root / 'adjacent-frames'
        result = review_tool.review(self.master, self.plan, out, self.candidate, scale=2, neighbor=neighbor)
        self.assertTrue(result['technical_pass'])
        self.assertEqual(result['coverage_contract']['master_sha256'], self.mi['file_sha256'])
        self.assertEqual(result['neighbor_against_original_master']['changed_rgba_pixels'], 1)
        self.assertEqual(result['neighbor_to_candidate']['changed_rgba_pixels'], 2)
        self.assertEqual(result['neighbor_to_candidate']['alpha_added_pixels'], 1)
        self.assertEqual(result['neighbor_to_candidate']['alpha_erased_pixels'], 1)
        record = next(p for p in result['previews'] if p['file'] == 'adjacent-white-native.png')
        self.assertEqual(record['columns_left_to_right'], ['master', 'neighbor', 'candidate'])
        _, actual = pipeline.decode_png(out / 'adjacent-white-native.png')
        columns = [review_tool.on_background(b''.join(bytes(p) for p in pixels), 8, 8, 'white')
                   for pixels in (self.raw, neighbor_pixels, candidate_pixels)]
        self.assertEqual(actual, review_tool.adjacent(columns, 8, 8))
        for p, data in before.items():
            self.assertEqual(p.read_bytes(), data)

    def test_neighbor_and_candidate_both_checked_against_original_locked_selection(self):
        self.accept()
        pixels = list(self.raw)
        pixels[0] = (15, 25, 35, 255)
        neighbor = self.root / 'neighbor.png'
        write_rgba_fixture(neighbor, 8, 8, pixels)
        write_rgba_fixture(self.candidate, 8, 8, pixels)
        result = review_tool.review(self.master, self.plan, self.root / 'both-drifted', self.candidate, scale=1, neighbor=neighbor)
        self.assertFalse(result['technical_pass'])
        self.assertEqual(result['neighbor_to_candidate']['changed_rgba_pixels'], 0)
        self.assertEqual(result['neighbor_against_original_master']['changed_pixels_outside_selection'], 1)
        self.assertEqual(result['diagnostics']['changed_pixels_outside_selection'], 1)
        self.assertTrue(any('neighbor RGBA cells' in error for error in result['errors']))
        self.assertTrue(any('candidate RGBA cells' in error for error in result['errors']))

    def test_neighbor_rejected_for_preflight_and_exposed_on_compare_cli(self):
        with self.assertRaisesRegex(ValueError, 'only valid for compare'):
            review_tool.review(self.master, self.plan, self.root / 'wrong-mode', neighbor=self.master)
        result = subprocess.run([sys.executable, str(Path(review_tool.__file__)), 'compare', '--help'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--neighbor', result.stdout)

    def test_preflight_validates_anchor_dimensions_even_before_candidate_exists(self):
        self.spec['anchor_regions'] = [rect(7, 7, 2, 2)]
        self.save()
        with self.assertRaisesRegex(ValueError, 'anchor_regions: rectangle exceeds native canvas'):
            review_tool.review(self.master, self.plan, self.root / 'bad-anchor')
        self.assertFalse((self.root / 'bad-anchor').exists())

    def test_compare_enforces_anchors_overlapping_selection_for_both_frames(self):
        self.spec['anchor_regions'] = [rect(3, 3)]
        self.accept()
        changed = list(self.raw)
        changed[27] = (10, 20, 30, 255)
        neighbor = self.root / 'neighbor.png'
        write_rgba_fixture(neighbor, 8, 8, changed)
        write_rgba_fixture(self.candidate, 8, 8, changed)
        result = review_tool.review(self.master, self.plan, self.root / 'anchors', self.candidate, scale=1, neighbor=neighbor)
        self.assertFalse(result['technical_pass'])
        self.assertEqual(result['neighbor_against_original_master']['changed_pixels_outside_selection'], 0)
        self.assertEqual(result['diagnostics']['changed_pixels_outside_selection'], 0)
        self.assertEqual(result['neighbor_against_original_master']['changed_pixels_inside_anchors'], 1)
        self.assertEqual(result['diagnostics']['changed_pixels_inside_anchors'], 1)
        self.assertEqual(result['diagnostics']['anchor_changed_coordinates_sample'], [[3, 3]])
        self.assertEqual(sum('anchor_regions' in error for error in result['errors']), 2)

    def test_output_symlink_is_never_followed(self):
        self.save()
        target, link = self.root / 'target', self.root / 'out'
        link.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
            review_tool.review(self.master, self.plan, link)
        self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
