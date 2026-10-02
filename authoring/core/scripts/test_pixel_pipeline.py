#!/usr/bin/env python3
"""Noncreative ImageMagick fixtures exercise the export/QA contract end to end."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

import pixel_pipeline as pipeline


def write_rgba_fixture(path, width, height, pixels):
    """Synthetic input bytes for export tests, independent of PNG quantization."""
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))
    raw = b''.join(bytes(pixel) for pixel in pixels)
    assert len(raw) == width * height * 4
    scanlines = b''.join(b'\0' + raw[y * width * 4:(y + 1) * width * 4] for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'
                     + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b''))
    return raw


class CoreCliTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, str(Path(pipeline.__file__).resolve()), *args],
                              capture_output=True, text=True)

    def test_public_cli_exposes_only_core_commands_and_options(self):
        result = self.cli('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = re.search(r'\{([^}]+)\}', result.stdout.splitlines()[0])
        self.assertIsNotNone(commands)
        self.assertEqual(commands.group(1).split(','), ['pack', 'plan', 'qa'])
        options = lambda help_text: set(re.findall(r'(?<!\w)--?[a-z][a-z-]*', help_text))
        self.assertEqual(options(result.stdout), {'-h', '--help'})
        expected_options = {
            'pack': {'-h', '--help', '--scale', '--columns', '--gif-fidelity', '--project'},
            'plan': {'-h', '--help', '--scale', '--columns', '--gif-fidelity', '--project'},
            'qa': {'-h', '--help', '--output', '--project'},
        }
        for command, expected in expected_options.items():
            with self.subTest(command=command):
                result = self.cli(command, '--help')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(options(result.stdout), expected)

    def test_pack_and_plan_dispatch_core_options(self):
        for command in ('pack', 'plan'):
            with self.subTest(command=command), redirect_stdout(io.StringIO()):
                with patch.object(pipeline, 'pack', return_value={'passed': True}) as pack:
                    status = pipeline.main([command, 'input.json', 'out', '--scale', '2',
                                            '--columns', '3', '--gif-fidelity', 'report'])
                self.assertEqual(status, 0)
                pack.assert_called_once_with('input.json', 'out', scale=2, columns=3,
                                             gif_fidelity='report', pose_plan=command == 'plan', project_path=None)


@unittest.skipUnless(shutil.which('magick') or shutil.which('convert'), 'ImageMagick is required')
class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pixel-pipeline-tests-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for i, color in enumerate(('#ff0000', '#00ff00', '#0000ff', '#ffff00')):
            pipeline.run_im(['-size', '8x8', 'xc:none', '-fill', '#00ffff',
                             '-draw', 'rectangle 2,2 5,5', '-fill', color,
                             '-draw', 'point 3,3', '-define', 'png:color-type=6',
                             str(self.root / f'frame-{i}.png')])
        self.manifest = {'width': 8, 'height': 8, 'master': 'frame-0.png', 'tag': 'idle',
                         'frames': [{'file': f'frame-{i % 4}.png', 'duration_ms': d}
                                    for i, d in enumerate((110, 120, 130, 140, 110, 120, 130, 145))],
                         'motion_regions': [{'x': 3, 'y': 3, 'width': 1, 'height': 1}],
                         'palette_max': 5}
        self.path = self.root / 'input.json'
        self.save()

    def save(self, manifest=None):
        self.path.write_text(json.dumps(manifest or self.manifest), encoding='utf-8')
        return pipeline.load_manifest(self.path)

    def test_roundtrip_eight_timeline_four_drawings(self):
        original = {p.name: p.read_bytes() for p in self.root.glob('*.png')}
        result = pipeline.pack(self.path, self.root / 'out', scale=3, columns=3,
                               gif_fidelity='report')
        self.assertFalse(result['passed'])  # The requested 145 ms hold cannot be encoded exactly in GIF.
        self.assertTrue(result['package_created'])
        self.assertEqual(result['timeline_frame_count'], 8)
        self.assertEqual(result['distinct_drawing_count'], 4)
        output = self.root / 'out'
        self.assertEqual(set(result['deliverables']), set(pipeline.DELIVERABLES))
        self.assertEqual({p.name for p in output.iterdir()}, set(pipeline.DELIVERABLES))
        portable = pipeline.load_manifest(output / 'manifest.json')
        provenance = portable['manifest']['provenance']
        self.assertEqual(set(provenance), {'source_manifest_sha256', 'artwork_handling', 'alignment'})
        self.assertEqual(provenance['source_manifest_sha256'], pipeline.digest(self.path.read_bytes()))
        qa, _ = pipeline.audit(portable)
        self.assertTrue(qa['passed'])
        self.assertEqual(qa['distinct_drawing_count'], 4)
        self.assertEqual(qa['palette_count_visible_union'], 5)
        self.assertEqual(qa['frames'][0]['nontransparent_bbox'],
                         {'x': 2, 'y': 2, 'width': 4, 'height': 4})
        self.assertEqual(qa['frames'][1]['delta_from_master']['changed_pixels'], 1)
        self.assertEqual(qa['frames'][1]['delta_from_master']['outside_motion_regions'], 0)
        self.assertTrue(all(d['changed_pixels'] == 1 for d in qa['adjacent_deltas']))
        gif = pipeline.gif_info(output / 'playback.gif')
        self.assertEqual(gif['frame_count'], 8)
        self.assertEqual(gif['duration_ms'], [110, 120, 130, 140, 110, 120, 130, 150])
        self.assertEqual((gif['width'], gif['height']), (24, 24))
        native_gif = pipeline.gif_info(output / 'playback-native.gif')
        self.assertEqual((native_gif['width'], native_gif['height']), (8, 8))
        self.assertEqual(native_gif['duration_ms'], gif['duration_ms'])
        index = json.loads((output / 'contact-sheet-index.json').read_text())
        self.assertEqual(index['frames'][7]['display_frame_number'], 8)
        self.assertEqual(index['frames'][7]['duration_ms'], 145)
        self.assertEqual(index['frames'][7]['image_bounds'],
                         {'x': 24, 'y': 48, 'width': 24, 'height': 24})
        self.assertTrue(any('centiseconds' in text for text in qa['warnings']))
        saved_qa = json.loads((output / 'qa.json').read_text())
        self.assertTrue(saved_qa['exports']['spritesheet_decoded_inputs_match'])
        self.assertEqual(saved_qa['exports']['contact_sheet']['width'], 72)
        self.assertEqual(saved_qa['exports']['contact_sheet']['height'], 72)
        self.assertTrue(saved_qa['exports']['gif']['decoded_visual_pixels_match'])
        self.assertFalse(saved_qa['exports']['gif']['encoded_timing_matches_requested'])
        self.assertTrue(saved_qa['exports']['gif']['encoded_timing_matches_quantized'])
        timing = json.loads((output / 'timing.json').read_text())
        self.assertEqual(timing['frames'][-1]['duration_ms'], 145)
        self.assertEqual(timing['total_duration_ms'], sum(f['duration_ms'] for f in self.manifest['frames']))
        self.assertIn('requestAnimationFrame', (output / 'playback.html').read_text())
        self.assertEqual((output / 'master.png').read_bytes(), original['frame-0.png'])
        self.assertEqual((output / 'master.png').stat().st_mode & 0o222, 0)
        for name, content in original.items():
            self.assertEqual((self.root / name).read_bytes(), content)
        # The package remains self-contained after original PNGs are unavailable.
        for name in original:
            (self.root / name).unlink()
        self.assertTrue(pipeline.audit(portable)[0]['passed'])

    def test_one_frame_master_supported(self):
        self.manifest['frames'] = self.manifest['frames'][:1]
        self.manifest['motion_regions'] = []
        self.save()
        result = pipeline.pack(self.path, self.root / 'single', scale=1)
        self.assertEqual(result['distinct_drawing_count'], 1)
        report = json.loads((self.root / 'single' / 'qa.json').read_text())
        self.assertEqual(report['adjacent_deltas'], [])
        self.assertEqual(report['loop_delta']['changed_pixels'], 0)
        self.assertEqual(report['visual_status'], 'unreviewed')

    def test_localization_fails_outside_regions(self):
        self.manifest['motion_regions'] = [{'x': 0, 'y': 0, 'width': 1, 'height': 1}]
        qa, _ = pipeline.audit(self.save())
        self.assertFalse(qa['passed'])
        self.assertEqual(qa['frames'][1]['delta_from_master']['outside_motion_regions'], 1)
        with self.assertRaisesRegex(pipeline.PipelineError, 'outside motion_regions'):
            pipeline.pack(self.path, self.root / 'bad')
        self.assertFalse((self.root / 'bad').exists())

    def test_strict_palette(self):
        self.manifest['palette_max'] = 4
        qa, _ = pipeline.audit(self.save())
        self.assertFalse(qa['passed'])
        self.assertTrue(any('palette_max' in error for error in qa['errors']))

    def test_margin_and_clipping_review_report(self):
        self.manifest['min_margin'] = 2
        qa, _ = pipeline.audit(self.save())
        self.assertTrue(qa['passed'])
        self.assertEqual(qa['frames'][0]['clear_margins'],
                         {'left': 2, 'right': 2, 'top': 2, 'bottom': 2})
        self.assertEqual(qa['frames'][0]['canvas_edge_contacts'], [])
        self.manifest['min_margin'] = 3
        qa, _ = pipeline.audit(self.save())
        self.assertFalse(qa['passed'])
        self.assertTrue(any('min_margin' in error for error in qa['errors']))
        pipeline.run_im(['-size', '8x8', 'xc:none', '-fill', '#00ffff',
                         '-draw', 'point 0,0', '-define', 'png:color-type=6',
                         str(self.root / 'edge.png')])
        self.manifest['master'] = 'edge.png'
        self.manifest['frames'] = [{'file': 'edge.png', 'duration_ms': 100}]
        self.manifest.pop('min_margin')
        qa, _ = pipeline.audit(self.save())
        self.assertTrue(qa['passed'])
        self.assertEqual(qa['frames'][0]['canvas_edge_contacts'], ['left', 'top'])
        self.assertTrue(any('inspect visually for clipping' in warning for warning in qa['warnings']))

    def test_absent_and_empty_motion_regions_differ(self):
        self.manifest.pop('motion_regions')
        qa, _ = pipeline.audit(self.save())
        self.assertTrue(qa['passed'])
        self.assertIsNone(qa['frames'][1]['delta_from_master']['outside_motion_regions'])
        self.manifest['motion_regions'] = []
        qa, _ = pipeline.audit(self.save())
        self.assertFalse(qa['passed'])
        self.assertEqual(qa['frames'][1]['delta_from_master']['outside_motion_regions'], 1)

    def test_fractional_alpha_fails(self):
        pipeline.run_im(['-size', '8x8', 'xc:rgba(255,0,0,0.5)', '-define', 'png:color-type=6',
                         str(self.root / 'partial.png')])
        self.manifest['frames'][0]['file'] = 'partial.png'
        qa, _ = pipeline.audit(self.save())
        self.assertFalse(qa['passed'])
        self.assertFalse(qa['frames'][0]['binary_alpha'])
        with self.assertRaisesRegex(pipeline.PipelineError, 'Non-binary alpha'):
            pipeline.pack(self.path, self.root / 'bad')

    def test_wrong_dimensions_fail(self):
        self.manifest['width'] = 9
        with self.assertRaisesRegex(pipeline.PipelineError, 'Native size mismatch'):
            pipeline.audit(self.save())

    def test_bad_schema_and_references(self):
        for field, value in [('width', True), ('height', 0), ('tag', ''), ('master', None),
                             ('frames', []), ('palette_max', -1), ('motion_regions', 'all')]:
            with self.subTest(field=field):
                broken = copy.deepcopy(self.manifest)
                broken[field] = value
                with self.assertRaises((pipeline.PipelineError, OSError)):
                    self.save(broken)
        for duration in (0, -1, 65536, 1.5, True):
            broken = copy.deepcopy(self.manifest)
            broken['frames'][0]['duration_ms'] = duration
            with self.assertRaises(pipeline.PipelineError):
                self.save(broken)
        broken = copy.deepcopy(self.manifest)
        broken['frames'][0]['file'] = 'missing.png'
        with self.assertRaises(FileNotFoundError):
            self.save(broken)
        broken['frames'][0]['file'] = '.'
        with self.assertRaises(pipeline.PipelineError):
            self.save(broken)

    def test_bad_regions_fail(self):
        for region in ({'x': 7, 'y': 0, 'width': 2, 'height': 1},
                       {'x': -1, 'y': 0, 'width': 1, 'height': 1},
                       {'x': 1, 'y': 1, 'width': 0, 'height': 1}):
            self.manifest['motion_regions'] = [region]
            with self.assertRaises(pipeline.PipelineError):
                self.save()

    def test_non_png_and_crc_rejected(self):
        path = self.root / 'fake.png'
        path.write_bytes(b'not a png')
        with self.assertRaisesRegex(pipeline.PipelineError, 'Not a PNG'):
            pipeline.decode_png(path)
        raw = bytearray((self.root / 'frame-0.png').read_bytes())
        raw[20] ^= 1
        path.write_bytes(raw)
        with self.assertRaisesRegex(pipeline.PipelineError, 'CRC'):
            pipeline.decode_png(path)

    def test_output_no_overwrite_and_report_protection(self):
        existing = self.root / 'existing'
        existing.mkdir()
        (existing / 'keep.txt').write_bytes(b'KEEP')
        with self.assertRaisesRegex(pipeline.PipelineError, 'fresh'):
            pipeline.pack(self.path, existing)
        self.assertEqual((existing / 'keep.txt').read_bytes(), b'KEEP')
        with self.assertRaisesRegex(pipeline.PipelineError, 'fresh'):
            pipeline.pack(self.path, self.root / 'frame-0.png')
        with self.assertRaisesRegex(pipeline.PipelineError, 'overwrite an input'):
            pipeline.exclusive_json(self.path, {}, [self.path])
        with self.assertRaisesRegex(pipeline.PipelineError, 'existing report'):
            pipeline.exclusive_json(self.path, {})

    def test_cli_reports_success_and_failure(self):
        command = [sys.executable, str(Path(pipeline.__file__).resolve()), 'qa', str(self.path)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])
        self.manifest['frames'][0]['duration_ms'] = 0
        self.save_json_only()
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stderr)['passed'])

    def test_strict_timing_rejects_and_report_is_explicit_failure(self):
        with self.assertRaisesRegex(pipeline.PipelineError, 'GIF fidelity failed'):
            pipeline.pack(self.path, self.root / 'strict')
        self.assertFalse((self.root / 'strict').exists())
        result = pipeline.pack(self.path, self.root / 'report', gif_fidelity='report', scale=1)
        self.assertFalse(result['passed'])
        self.assertTrue(result['package_created'])
        self.assertFalse(result['gif_fidelity_passed'])
        report = json.loads((self.root / 'report' / 'qa.json').read_text())
        self.assertFalse(report['passed'])
        self.assertEqual(report['visual_status'], 'unreviewed')

    def test_gif_coalesced_identical_holds(self):
        self.manifest['frames'] = [{'file': 'frame-0.png', 'duration_ms': 110},
                                   {'file': 'frame-0.png', 'duration_ms': 120},
                                   {'file': 'frame-1.png', 'duration_ms': 130}]
        loaded = self.save()
        _, cache = pipeline.audit(loaded)
        gif = self.root / 'coalesced.gif'
        pipeline.run_im(['(', '-delay', '23', '-dispose', 'background', str(self.root / 'frame-0.png'), ')',
                         '(', '-delay', '13', '-dispose', 'background', str(self.root / 'frame-1.png'), ')',
                         '-loop', '0', str(gif)])
        result = pipeline.verify_gif(gif, loaded, cache)
        self.assertTrue(result['passed'])
        self.assertEqual(result['frame_count'], 2)
        self.assertEqual(len(loaded['frames']), 3)
        self.assertEqual([r['duration_ms'] for r in result['decoded_runs']], [230, 130])

    def test_gif_visual_corruption_detected(self):
        self.manifest['frames'] = [{'file': 'frame-0.png', 'duration_ms': 110}]
        loaded = self.save()
        _, cache = pipeline.audit(loaded)
        path = self.root / 'wrong.gif'
        pipeline.run_im(['-delay', '11', str(self.root / 'frame-1.png'), str(path)])
        result = pipeline.verify_gif(path, loaded, cache)
        self.assertFalse(result['passed'])
        self.assertFalse(result['decoded_visual_pixels_match'])
        self.assertTrue(result['encoded_timing_matches_requested'])

    def test_unsupported_palette_rejected_even_in_report_mode(self):
        # Synthetic 512-color fixture only; this is not artwork generation.
        pixels = [bytes((x * 8, y * 16, (x + y) % 2 * 255, 255)) for y in range(16) for x in range(32)]
        source = self.root / 'many-colors.png'
        write_rgba_fixture(source, 32, 16, pixels)
        self.manifest = {'width': 32, 'height': 16, 'master': source.name, 'tag': 'palette-test',
                         'frames': [{'file': source.name, 'duration_ms': 100}]}
        loaded = self.save()
        qa, cache = pipeline.audit(loaded)
        self.assertTrue(qa['passed'])  # Valid PNGs can exceed the GIF palette capacity.
        self.assertTrue(any('lossless GIF export will be rejected' in w for w in qa['warnings']))
        before = source.read_bytes()
        for policy in ('strict', 'report'):
            output = self.root / ('palette-' + policy)
            with self.assertRaisesRegex(pipeline.PipelineError, 'GIF palette capacity exceeded'):
                pipeline.pack(self.path, output, scale=1, gif_fidelity=policy)
            self.assertFalse(output.exists())
        self.assertEqual(source.read_bytes(), before)
        # Independent decode still catches deliberately lossy third-party GIFs.
        gif = self.root / 'lossy.gif'
        pipeline.run_im(['-delay', '10', str(source), str(gif)])
        result = pipeline.verify_gif(gif, loaded, cache)
        self.assertFalse(result['passed'])
        self.assertFalse(result['decoded_visual_pixels_match'])
        self.assertTrue(result['encoded_timing_matches_requested'])

    def test_nearby_rgb_colors_preserved_at_native_and_enlarged_size(self):
        # These cream colors were merged by implicit ImageMagick GIF conversion,
        # even with just three visible entries; hidden RGB is intentionally distinct.
        first = [(252, 236, 210, 255), (252, 238, 211, 255),
                 (252, 236, 210, 0), (10, 58, 69, 255)]
        second = [first[1], first[2], first[0], first[3]]
        write_rgba_fixture(self.root / 'cream-a.png', 4, 1, first)
        write_rgba_fixture(self.root / 'cream-b.png', 4, 1, second)
        self.manifest = {'width': 4, 'height': 1, 'master': 'cream-a.png', 'tag': 'near-colors',
                         'frames': [{'file': name, 'duration_ms': duration} for name, duration in
                                    [('cream-a.png', 800), ('cream-b.png', 100),
                                     ('cream-a.png', 450), ('cream-a.png', 900)]]}
        self.save()
        before = {p.name: p.read_bytes() for p in self.root.glob('cream-*.png')}
        output = self.root / 'cream-package'
        result = pipeline.pack(self.path, output, scale=6)
        self.assertTrue(result['passed'])
        qa = json.loads((output / 'qa.json').read_text())
        for key in ('gif', 'native_gif'):
            self.assertTrue(qa['exports'][key]['decoded_visual_pixels_match'])
            self.assertTrue(qa['exports'][key]['encoded_timing_matches_requested'])
            self.assertEqual(qa['exports'][key]['duration_ms'], [800, 100, 450, 900])
            self.assertEqual(qa['exports'][key]['frame_count'], 4)
        self.assertFalse(list(output.glob('.gif-palettes-*')))
        for name, raw in before.items():
            self.assertEqual((self.root / name).read_bytes(), raw)

    def test_gif_palette_capacity_is_per_frame_and_includes_transparency(self):
        # A local palette permits >256 colors across a timeline, but never within
        # one frame. Exercise exact 256 opaque and 255 visible + transparent limits.
        frames = [
            [(n, (n * 37) % 256, 17, 255) for n in range(256)],
            [(n, (n * 41) % 256, 29, 255) for n in range(255)] + [(1, 2, 3, 0)],
            [(3, 2, 1, 0)] * 256,
            [(0, 0, 0, 255), (0, 0, 0, 0)] * 128,
        ]
        for i, pixels in enumerate(frames):
            write_rgba_fixture(self.root / f'capacity-{i}.png', 16, 16, pixels)
        self.manifest = {'width': 16, 'height': 16, 'master': 'capacity-0.png', 'tag': 'capacity',
                         'frames': [{'file': f'capacity-{i}.png', 'duration_ms': 110 + i * 10}
                                    for i in (0, 1, 2, 3, 0, 2, 1)]}
        loaded = self.save()
        qa, _ = pipeline.audit(loaded)
        self.assertGreater(qa['palette_count_visible_union'], 256)
        self.assertFalse(any('lossless GIF export will be rejected' in w for w in qa['warnings']))
        result = pipeline.pack(self.path, self.root / 'capacity', scale=2)
        self.assertTrue(result['passed'])
        saved = json.loads((self.root / 'capacity' / 'qa.json').read_text())
        self.assertTrue(saved['exports']['gif']['passed'])
        self.assertTrue(saved['exports']['native_gif']['passed'])

    def test_indexed_png_rejects_unrepresentable_pixels(self):
        target = self.root / 'indexed.png'
        for pixels in (
            [(n, 0, 0, 255) for n in range(256)] + [(1, 2, 3, 0)],
            [(n, 0, 0, 255) for n in range(256)] + [(0, 1, 0, 255)],
        ):
            with self.assertRaisesRegex(pipeline.PipelineError, 'GIF palette capacity exceeded'):
                pipeline.write_gif_indexed_png(target, b''.join(bytes(p) for p in pixels), 257, 1)
            self.assertFalse(target.exists())
        with self.assertRaisesRegex(pipeline.PipelineError, 'binary alpha'):
            pipeline.write_gif_indexed_png(target, bytes((1, 2, 3, 127)), 1, 1)
        with self.assertRaisesRegex(pipeline.PipelineError, 'dimensions do not match'):
            pipeline.write_gif_indexed_png(target, b'\0\0\0\0', 2, 1)

    def test_indexed_png_preserves_exact_visible_rgba(self):
        for pixels in (
            [(0, 0, 0, 255), (1, 2, 3, 0), (252, 236, 210, 255), (252, 238, 211, 255)],
            [(252, 236, 210, 255)] * 4,
            [(1, 2, 3, 0)] * 4,
        ):
            raw = b''.join(bytes(p) for p in pixels)
            target = self.root / 'indexed.png'
            pipeline.write_gif_indexed_png(target, raw, 2, 2)
            info, decoded = pipeline.decode_png(target)
            self.assertEqual(info['color_type'], 3)
            self.assertEqual(info['bit_depth'], 8)
            self.assertEqual(pipeline.visual_hash(decoded), pipeline.visual_hash(raw))

    def test_semantic_pose_plan_and_missing_pose_failures(self):
        plan = {'schema_version': 1, 'width': 8, 'height': 8, 'tag': 'read', 'master_pose': 'read',
                'poses': {'read': {'file': 'frame-0.png', 'status': 'approved'},
                          'blink': {'file': 'frame-1.png', 'status': 'generated'}},
                'timeline': [{'pose_id': 'read', 'duration_ms': 800},
                             {'pose_id': 'blink', 'duration_ms': 100},
                             {'pose_id': 'read', 'duration_ms': 800}],
                'constraints': {'timeline_frame_count': 3, 'distinct_drawing_count': 2,
                                'min_distinct_drawing_count': 2, 'total_duration_ms': 1700}}
        path = self.root / 'plan.json'
        path.write_text(json.dumps(plan))
        result = pipeline.pack(path, self.root / 'planned', scale=1, pose_plan=True)
        self.assertTrue(result['passed'])
        portable = json.loads((self.root / 'planned' / 'manifest.json').read_text())
        self.assertEqual([f['pose_id'] for f in portable['frames']], ['read', 'blink', 'read'])
        plan['timeline'][1]['pose_id'] = 'page-turn'
        path.write_text(json.dumps(plan))
        with self.assertRaisesRegex(pipeline.PipelineError, "missing pose ID 'page-turn'"):
            pipeline.load_pose_plan(path)
        plan['timeline'][1]['pose_id'] = 'blink'
        plan['poses']['blink']['file'] = 'not-created.png'
        path.write_text(json.dumps(plan))
        with self.assertRaisesRegex(pipeline.PipelineError, "'blink' native file is missing"):
            pipeline.load_pose_plan(path)

    def test_duplicate_json_keys_and_constraints_reject(self):
        self.path.write_text('{"poses":{"idle":1,"idle":2}}')
        with self.assertRaisesRegex(pipeline.PipelineError, 'Duplicate JSON key'):
            pipeline.load_pose_plan(self.path)
        for constraint, value in [('timeline_frame_count', 7), ('distinct_drawing_count', 5),
                                  ('min_distinct_drawing_count', 5), ('total_duration_ms', 2)]:
            self.manifest['constraints'] = {constraint: value}
            qa, _ = pipeline.audit(self.save())
            self.assertFalse(qa['passed'])
            self.assertIn('Constraint ' + constraint, ' '.join(qa['errors']))
        self.manifest['constraints'] = {'typo_constraint': 10}
        with self.assertRaisesRegex(pipeline.PipelineError, 'Unknown constraints'):
            self.save()

    def project(self, mode='full_body'):
        value = {'schema_version': '3.0', 'asset_id': 'fixture', 'brief': 'Synthetic helper test',
                 'profile': 'profile.json', 'native_canvas_px': [8, 8],
                 'limits': {'palette_max': 5, 'binary_alpha': True, 'min_margin': 1},
                 'budget': {'max_calls': 1},
                 'animation': {'mode': mode, 'duration_ms': sum(f['duration_ms'] for f in self.manifest['frames']),
                               'max_unique_drawings': 4, 'max_timeline_entries': 8, 'min_unique_drawings': 2}}
        (self.root / 'profile.json').write_text('{}')
        project = self.root / 'project.json'
        project.write_text(json.dumps(value))
        return project, value

    def test_project_shared_settings_counts_and_pack_provenance(self):
        project, _ = self.project()
        self.manifest['project'] = 'project.json'
        self.manifest.pop('width'); self.manifest.pop('height'); self.manifest.pop('palette_max')
        loaded = self.save()
        self.assertEqual((loaded['width'], loaded['height']), (8, 8))
        qa, _ = pipeline.audit(loaded)
        self.assertTrue(qa['passed'])
        self.assertEqual(qa['animation_mode'], 'full_body')
        self.assertEqual(qa['full_body_qa']['status'], 'unverified')
        result = pipeline.pack(self.path, self.root / 'project-out', scale=1, gif_fidelity='report')
        portable = pipeline.load_manifest(self.root / 'project-out/manifest.json')
        self.assertTrue(pipeline.audit(portable)[0]['passed'])
        self.assertEqual(portable['manifest']['project_provenance']['project_sha256'], pipeline.digest(project.read_bytes()))
        self.assertFalse(result['passed'])  # Exact PNG timeline remains valid; GIF 145 ms cannot be exact.

    def test_project_conflicts_and_decoded_drawing_limits_reject(self):
        project, value = self.project()
        for field, setting in [('width', 7), ('palette_max', 4), ('animation_mode', 'local')]:
            changed = dict(self.manifest, **{field: setting})
            with self.subTest(field=field), self.assertRaisesRegex(pipeline.PipelineError, 'conflicts with project'):
                pipeline.load_manifest(self.path, changed, project)
        value['animation']['max_unique_drawings'] = 3
        project.write_text(json.dumps(value))
        loaded = pipeline.load_manifest(self.path, project_path=project)
        qa, _ = pipeline.audit(loaded)
        self.assertFalse(qa['passed'])
        self.assertIn('max_distinct_drawing_count', ' '.join(qa['errors']))
        self.manifest['frames'][0]['duration_ms'] += 10
        self.save_json_only()
        with self.assertRaisesRegex(pipeline.PipelineError, 'duration conflicts'):
            pipeline.load_manifest(self.path, project_path=project)

    def test_explicit_project_disagreement_and_static_scope(self):
        project, value = self.project()
        other = self.root / 'other.json'; other.write_text(json.dumps(value))
        self.manifest['project'] = 'project.json'
        self.save_json_only()
        with self.assertRaisesRegex(pipeline.PipelineError, 'contradicts'):
            pipeline.load_manifest(self.path, project_path=other)
        static = {'scope': 'static', 'master': 'frame-0.png', 'tag': 'master',
                  'frames': [{'file': 'frame-0.png', 'duration_ms': 10}]}
        qa, _ = pipeline.audit(pipeline.load_manifest(self.path, static, project))
        self.assertTrue(qa['passed'])
        self.assertNotIn('max_distinct_drawing_count', qa['constraints'])

    def test_shaped_mask_selects_exact_rgba_and_is_portable(self):
        pixels = [(0,0,0,255)] * 64
        pixels[3*8+3] = (255,255,255,255)
        write_rgba_fixture(self.root / 'mask.png', 8, 8, pixels)
        self.manifest.pop('motion_regions')
        self.manifest.update(animation_mode='local', motion_mask='mask.png')
        qa, _ = pipeline.audit(self.save())
        self.assertTrue(qa['passed'])
        self.assertEqual(qa['motion_mask']['white_selected_pixels'], 1)
        self.assertEqual(qa['frames'][1]['delta_from_master']['outside_motion_regions'], 0)
        self.manifest['frames'][-1]['duration_ms'] = 140
        self.save()
        result = pipeline.pack(self.path, self.root / 'mask-out', scale=1)
        self.assertTrue(result['passed'])
        self.assertEqual((self.root / 'mask-out/motion-mask.png').read_bytes(), (self.root / 'mask.png').read_bytes())
        self.assertTrue(pipeline.audit(pipeline.load_manifest(self.root / 'mask-out/manifest.json'))[0]['passed'])

    def test_bad_masks_fail_binary_size_empty_full_and_ambiguous_combine(self):
        self.manifest['motion_mask'] = 'mask.png'
        for pixels, dims, phrase in [([(255,255,255,255)]*64, (8,8), 'full canvas'),
                                    ([(0,0,0,255)]*64, (8,8), 'nonempty'),
                                    ([(128,128,128,255)]*64, (8,8), 'binary'),
                                    ([(255,255,255,0)]*64, (8,8), 'binary'),
                                    ([(255,255,255,255)]*4, (2,2), 'dimensions')]:
            write_rgba_fixture(self.root / 'mask.png', *dims, pixels)
            with self.subTest(phrase=phrase), self.assertRaisesRegex(pipeline.PipelineError, phrase):
                self.save()
        pixels = [(0,0,0,255)] * 64; pixels[27] = (255,255,255,255)
        write_rgba_fixture(self.root / 'mask.png',8,8,pixels)
        with self.assertRaisesRegex(pipeline.PipelineError, 'intersection'):
            self.save()
        self.manifest['mask_semantics'] = 'intersection'
        self.manifest['motion_mask_sha256'] = '0'*64
        with self.assertRaisesRegex(pipeline.PipelineError, 'hash differs'):
            self.save()
        self.manifest['motion_mask_sha256'] = pipeline.digest((self.root / 'mask.png').read_bytes())
        self.assertTrue(pipeline.audit(self.save())[0]['passed'])
        self.manifest['motion_regions'] = [{'x': 0, 'y': 0, 'width': 1, 'height': 1}]
        with self.assertRaisesRegex(pipeline.PipelineError, 'nonempty'):
            self.save()

    def test_full_body_legitimate_wholebody_changes_and_geometry_bounds(self):
        pixels = [(0,0,0,0)] * 64
        for y in range(1,6):
            for x in range(1,4): pixels[y*8+x] = (0,255,255,255)
        write_rgba_fixture(self.root / 'whole.png',8,8,pixels)
        self.manifest['frames'] = [{'file':'whole.png','duration_ms':100}]
        self.manifest['animation_mode'] = 'full_body'
        self.manifest['geometry_constraints'] = {'max_centroid_shift_px': 2, 'bbox_width_ratio':[0.5,1.5], 'bbox_height_ratio':[0.5,1.5]}
        qa, _ = pipeline.audit(self.save())
        self.assertTrue(qa['passed'])
        self.assertIsNone(qa['frames'][0]['delta_from_master']['outside_motion_regions'])
        self.assertEqual(qa['full_body_qa']['frames'][0]['review_status']['identity'], 'unverified')
        original = (self.root / 'whole.png').read_bytes()
        self.assertTrue(pipeline.pack(self.path,self.root/'whole-out',scale=1)['passed'])
        self.assertEqual((self.root/'whole-out/sequence/frame-0000.png').read_bytes(),original)
        self.manifest['geometry_constraints']['max_centroid_shift_px'] = 0
        qa, _ = pipeline.audit(self.save())
        self.assertFalse(qa['passed'])
        self.assertIn('max_centroid_shift_px', ' '.join(qa['errors']))
        self.manifest['geometry_constraints'] = {'root_anchor_px':[8,3], 'max_root_drift_px':1}
        with self.assertRaisesRegex(pipeline.PipelineError,'outside native canvas'):
            pipeline.audit(self.save())

    def test_full_body_review_hashes_root_contact_and_identity_are_separate(self):
        self.manifest.update(animation_mode='full_body', frames=self.manifest['frames'][:1],
                             geometry_constraints={'root_anchor_px':[3,5], 'max_root_drift_px':0,
                                                   'contact_y_px':5,'max_contact_drift_px':0})
        qa,_ = pipeline.audit(self.save())
        self.assertFalse(qa['passed'])  # Declared root/contact checks need explicit evidence.
        sha = pipeline.digest((self.root/'frame-0.png').read_bytes())
        review = {'frame':0,'master_sha256':sha,'frame_sha256':sha,
                  'identity':{'status':'passed','notes':'Synthetic identity assertion'},
                  'landmarks':{'status':'passed','root_px':[3,5],'notes':'Synthetic root assertion'},
                  'contact':{'status':'passed','contact_px':[[2,5],[3,5]],'notes':'Synthetic contact assertion'}}
        self.manifest['full_body_reviews'] = [review]
        qa,_=pipeline.audit(self.save())
        self.assertTrue(qa['passed'])
        self.assertEqual(qa['full_body_qa']['status'],'review_records_complete')
        review['frame_sha256']='0'*64
        with self.assertRaisesRegex(pipeline.PipelineError,'hashes do not match'):
            pipeline.audit(self.save())
        review['frame_sha256']=sha; review['contact']['contact_px']=[[3,4]]
        qa,_=pipeline.audit(self.save())
        self.assertFalse(qa['passed'])
        review['contact']['contact_px']=[[3,5]]; review['identity']['status']='failed'
        qa,_=pipeline.audit(self.save())
        self.assertFalse(qa['passed'])
        self.assertIn('identity review failed',' '.join(qa['errors']))

    def test_pose_acceptance_and_required_semantic_phases(self):
        sha=pipeline.digest((self.root/'frame-0.png').read_bytes())
        plan={'schema_version':1,'width':8,'height':8,'tag':'action','master_pose':'ready',
              'poses':{'ready':{'file':'frame-0.png','status':'accepted',
                                'quality_review':{'status':'accepted','artifact_sha256':sha,'notes':'Synthetic acceptance'}}},
              'required_phases':['ready','recover'],
              'timeline':[{'pose_id':'ready','duration_ms':100,'phase':'ready'}]}
        path=self.root/'accepted-plan.json';path.write_text(json.dumps(plan))
        with self.assertRaisesRegex(pipeline.PipelineError,'missing required semantic phases'):
            pipeline.load_pose_plan(path)
        plan['timeline'].append({'pose_id':'ready','duration_ms':100,'phase':'recover'})
        path.write_text(json.dumps(plan)); self.assertEqual(len(pipeline.load_pose_plan(path)['frames']),2)
        for status in ('study','needs_revision'):
            plan['poses']['ready']['status']=status;path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(pipeline.PipelineError,'cannot execute'):
                pipeline.load_pose_plan(path)
        plan['poses']['ready']['status']='accepted';plan['poses']['ready']['quality_review']['artifact_sha256']='0'*64
        path.write_text(json.dumps(plan))
        with self.assertRaisesRegex(pipeline.PipelineError,'hash-bound'):
            pipeline.load_pose_plan(path)

    def test_native_reference_exact_enlargement_acceptance_and_geometry(self):
        import native_reference
        raw=write_rgba_fixture(self.root/'hidden.png',2,2,[(42,12,9,0),(1,2,3,255),(5,6,7,255),(9,8,7,0)])
        source=self.root/'hidden.png';before=source.read_bytes()
        acceptance=self.root/'accepted.json'
        acceptance.write_text(json.dumps({'status':'accepted','artifact_sha256':pipeline.digest(before),'notes':'Synthetic fixture acceptance'}))
        record=native_reference.enlarge(source,self.root/'ref.png',3,acceptance)
        info,actual=pipeline.decode_png(self.root/'ref.png')
        self.assertEqual((info['width'],info['height']),(6,6))
        for y in range(6):
            for x in range(6):
                offset=((y//3)*2+x//3)*4
                self.assertEqual(actual[(y*6+x)*4:(y*6+x+1)*4],raw[offset:offset+4])
        self.assertTrue(record['native_cells_verified'])
        self.assertEqual(source.read_bytes(),before)
        for scale in (0,-1,1.5,True):
            with self.assertRaisesRegex(pipeline.PipelineError,'integer'):
                native_reference.enlarge(source,self.root/'bad-ref.png',scale,acceptance)
        acceptance.write_text(json.dumps({'status':'accepted','artifact_sha256':'0'*64,'notes':'stale'}))
        with self.assertRaisesRegex(pipeline.PipelineError,'hash-bound'):
            native_reference.enlarge(source,self.root/'stale.png',2,acceptance)
        self.assertFalse((self.root/'stale.png').exists())

    def save_json_only(self):
        self.path.write_text(json.dumps(self.manifest), encoding='utf-8')


if __name__ == '__main__':
    unittest.main(verbosity=2)
