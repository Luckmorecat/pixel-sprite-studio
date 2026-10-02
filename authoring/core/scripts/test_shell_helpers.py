#!/usr/bin/env python3
"""Synthetic fixtures only: deterministic normalization and localized RGBA assembly."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import pixel_pipeline as pipeline


@unittest.skipUnless(shutil.which('magick'), 'ImageMagick 7 is required by shell helpers')
class ShellHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pixel-shell-tests-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scripts = Path(__file__).resolve().parent
        for name, changed in [('master', False), ('candidate', True)]:
            args = ['-size', '8x8', 'xc:none', '-fill', '#ff0000', '-draw', 'rectangle 2,2 5,5']
            if changed:
                args += ['-fill', '#00ff00', '-draw', 'point 3,3', '-draw', 'point 5,5']
            pipeline.run_im(args + ['-define', 'png:color-type=6', str(self.root / (name + '.png'))])
        self.region = {'x': 3, 'y': 3, 'width': 1, 'height': 1}
        self.regions = self.root / 'regions.json'
        self.output = self.root / 'frame.png'
        self.write_regions([self.region])

    def write_regions(self, value):
        self.regions.write_text(json.dumps(value))

    def assemble(self):
        return subprocess.run(['bash', str(self.scripts / 'assemble_generated_patches.sh'),
                               '--master', str(self.root / 'master.png'), '--candidate', str(self.root / 'candidate.png'),
                               '--regions', str(self.regions), '--output', str(self.output)], capture_output=True, text=True)

    def normalize(self, name='native.png', extra=()):
        return subprocess.run(['bash', str(self.scripts / 'prepare_pixels.sh'),
                               '--input', str(self.root / 'master.png'), '--output', str(self.root / name),
                               '--width', '8', '--height', '8', '--colors', '8', *extra], capture_output=True, text=True)

    def test_assembly_preserves_static_pixels_and_reports_raw_drift(self):
        original = (self.root / 'master.png').read_bytes()
        result = self.assemble()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(self.output.with_suffix('.assembly.json').read_text())
        self.assertEqual(report['changed_pixels'], 1)
        self.assertEqual(report['changed_pixels_outside_regions'], 0)
        self.assertEqual(report['raw_candidate_changed_pixels_outside_regions'], 1)
        self.assertEqual(report['alignment_review']['status'], 'unreviewed')
        self.assertEqual(report['visual_status'], 'unreviewed')
        self.assertEqual((self.root / 'master.png').read_bytes(), original)
        _, master = pipeline.decode_png(self.root / 'master.png')
        _, candidate = pipeline.decode_png(self.root / 'candidate.png')
        _, actual = pipeline.decode_png(self.output)
        for i in range(64):
            self.assertEqual(actual[i * 4:i * 4 + 4],
                             (candidate if i == 3 * 8 + 3 else master)[i * 4:i * 4 + 4])
        second = self.assemble()
        self.assertNotEqual(second.returncode, 0)
        self.assertIn('Refusing to overwrite', second.stderr)

    def test_full_canvas_union_rejected(self):
        self.write_regions([{'x': 0, 'y': 0, 'width': 4, 'height': 8},
                            {'x': 4, 'y': 0, 'width': 4, 'height': 8}])
        result = self.assemble()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Full-canvas motion-region union', result.stderr)
        self.assertFalse(self.output.exists())

    def test_anchor_drift_rejects_before_output(self):
        self.write_regions({'motion_regions': [self.region],
                            'anchor_regions': [{'x': 5, 'y': 5, 'width': 1, 'height': 1}]})
        result = self.assemble()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Pre-composite anchor drift', result.stderr)
        self.assertFalse(self.output.exists())

    def test_review_hashes_are_bound_to_actual_inputs(self):
        sha = lambda name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        review = {'status': 'passed', 'master_sha256': sha('master.png'),
                  'candidate_sha256': sha('candidate.png'), 'notes': 'Synthetic test review only'}
        self.write_regions({'motion_regions': [self.region], 'alignment_review': review})
        result = self.assemble()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.output.with_suffix('.assembly.json').read_text())['alignment_review'], review)
        self.output = self.root / 'mismatch.png'
        review['candidate_sha256'] = '0' * 64
        self.write_regions({'motion_regions': [self.region], 'alignment_review': review})
        result = self.assemble()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('input hashes do not match', result.stderr)
        self.assertFalse(self.output.exists())

    def test_normalization_grid_lock_and_no_overwrite(self):
        before = (self.root / 'master.png').read_bytes()
        result = self.normalize()
        self.assertEqual(result.returncode, 0, result.stderr)
        provenance = self.root / 'native.provenance.json'
        info = json.loads(provenance.read_text())
        self.assertEqual(info['visual_status'], 'unreviewed')
        self.assertIsNone(info['grid_lock'])
        result = self.normalize('matched.png', ('--grid-lock', str(provenance)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads((self.root / 'matched.provenance.json').read_text())['grid_lock']['matched'])
        result = self.normalize('mismatch.png', ('--crop', '4x4+2+2', '--grid-lock', str(provenance)))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Grid lock mismatch', result.stderr)
        self.assertFalse((self.root / 'mismatch.png').exists())
        result = self.normalize()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Refusing to overwrite', result.stderr)
        self.assertEqual((self.root / 'master.png').read_bytes(), before)

    def test_shaped_mask_exact_composition_including_hidden_rgba(self):
        from test_pixel_pipeline import write_rgba_fixture
        a=[(10,20,30,0)]*64; b=[(80,90,100,0)]*64
        a[27]=(255,0,0,255); b[27]=(0,255,0,255)
        write_rgba_fixture(self.root/'master.png',8,8,a)
        write_rgba_fixture(self.root/'candidate.png',8,8,b)
        pixels=[(0,0,0,255)]*64; pixels[27]=(255,255,255,255);pixels[28]=(255,255,255,255)
        write_rgba_fixture(self.root/'shaped.png',8,8,pixels)
        before=(self.root/'master.png').read_bytes()
        self.write_regions({'motion_mask':'shaped.png'})
        result=self.assemble();self.assertEqual(result.returncode,0,result.stderr)
        _,raw=pipeline.decode_png(self.output)
        for i in range(64):self.assertEqual(raw[i*4:i*4+4],bytes(b[i] if i in (27,28) else a[i]))
        report=json.loads(self.output.with_suffix('.assembly.json').read_text())
        self.assertEqual(report['motion_mask']['file_sha256'],hashlib.sha256((self.root/'shaped.png').read_bytes()).hexdigest())
        self.assertEqual(report['changed_pixels_outside_regions'],0)
        self.assertEqual(report['mask_semantics'],'white_selects')
        self.assertEqual((self.root/'master.png').read_bytes(),before)

    def test_shaped_mask_anchor_checks_and_ambiguous_intersection(self):
        pipeline.run_im(['-size','8x8','xc:black','-fill','white','-draw','point 3,3',str(self.root/'mask.png')])
        self.write_regions({'motion_mask':'mask.png','motion_regions':[self.region]})
        result=self.assemble();self.assertNotEqual(result.returncode,0)
        self.assertIn('intersection',result.stderr)
        self.write_regions({'motion_mask':'mask.png','motion_regions':[self.region],'mask_semantics':'intersection',
                            'anchor_regions':[{'x':5,'y':5,'width':1,'height':1}]})
        result=self.assemble();self.assertNotEqual(result.returncode,0)
        self.assertIn('Pre-composite anchor drift',result.stderr)
        self.assertFalse(self.output.exists())

    def write_project(self, margin=1):
        project={'schema_version':'3.0','asset_id':'fixture','brief':'Fixture only','profile':'profile.json',
                 'native_canvas_px':[8,8],'limits':{'palette_max':8,'binary_alpha':True,'min_margin':margin},
                 'budget':{'max_calls':1},'animation':{'mode':'full_body','duration_ms':1000,
                                                     'max_unique_drawings':4,'max_timeline_entries':8}}
        (self.root/'profile.json').write_text('{}')
        path=self.root/'project.json';path.write_text(json.dumps(project));return path

    def test_normalization_project_inheritance_provenance_and_conflict(self):
        project=self.write_project()
        command=['bash',str(self.scripts/'prepare_pixels.sh'),'--input',str(self.root/'master.png'),
                 '--output',str(self.root/'inherited.png'),'--project',str(project)]
        result=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads((self.root/'inherited.provenance.json').read_text())
        self.assertEqual(report['output']['width'],8)
        self.assertEqual(report['requested_color_limit'],8)
        self.assertEqual(report['project_provenance']['project_sha256'],hashlib.sha256(project.read_bytes()).hexdigest())
        self.assertTrue(report['project_limits_verified']['binary_alpha'])
        result=self.normalize('contradict.png',('--project',str(project),'--colors','4'))
        self.assertNotEqual(result.returncode,0)
        self.assertIn('conflicts with project',result.stderr)
        self.assertFalse((self.root/'contradict.png').exists())
        project=self.write_project(margin=3)
        result=self.normalize('margin.png',('--project',str(project)))
        self.assertNotEqual(result.returncode,0)
        self.assertIn('violates project min_margin',result.stderr)
        self.assertFalse((self.root/'margin.png').exists())

    def test_actual_model_dimensions_require_explicit_matching_geometry(self):
        pipeline.run_im(['-size','12x8','xc:none','-fill','red','-draw','rectangle 2,2 5,5',str(self.root/'wide.png')])
        command=['bash',str(self.scripts/'prepare_pixels.sh'),'--input',str(self.root/'wide.png'),
                 '--output',str(self.root/'measured.png'),'--width','8','--height','8','--colors','8']
        result=subprocess.run(command,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Aspect ratio mismatch',result.stderr)
        self.assertFalse((self.root/'measured.png').exists())
        result=subprocess.run(command+['--crop','8x8+0+0'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        provenance=json.loads((self.root/'measured.provenance.json').read_text())
        self.assertEqual((provenance['source']['width'],provenance['source']['height']),(12,8))
        self.assertEqual(provenance['crop'],'8x8+0+0')
        self.assertFalse(provenance['creative_repair'])

    def test_dangling_output_symlink_is_not_followed(self):
        target = self.root / 'should-not-be-created.png'
        self.output.symlink_to(target)
        result = self.assemble()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(target.exists())
        (self.root / 'native.png').symlink_to(target)
        result = self.normalize()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
