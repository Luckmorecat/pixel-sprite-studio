"""Synthetic immutable-source and historical-hash regressions, never art generation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import run_ledger as ledger
from motion_support import exact_rgba_png


class ArtifactHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.skill=self.root/'skill';self.skill.mkdir();(self.skill/'SKILL.md').write_text('Synthetic skill fixture')
        self.request=self.root/'request.txt';self.request.write_text('Synthetic testing only')
        self.prompt=self.root/'prompt.txt';self.prompt.write_text('Synthetic pose')
        self.params=self.root/'params.json';self.params.write_text('{}')
        self.run=self.root/'run'
        self.budgets={'max_attempts':4,'max_new_poses':4,'max_stage_repairs':2,'max_pose_repairs':2}
        self.pixels=exact_rgba_png(bytes([0,0,0,0])*4+bytes([255,255,255,255])*8+bytes([0,0,0,0])*4,4,4)
    def tearDown(self):
        for base,dirs,files in os.walk(self.root):
            Path(base).chmod(0o755)
            for name in files:(Path(base)/name).chmod(0o644)
        self.tmp.cleanup()
    def init(self):ledger.init_run(self.run,[('fixture',self.skill)],self.request,self.budgets,immutable_attempt_paths=True)
    def start(self,pose='one'):return ledger.generation_start(self.run,'animation',pose,'synthetic',self.prompt,self.params)['attempt_id']
    def source(self,attempt):
        p=self.root/'sources'/attempt/'original.png';p.parent.mkdir(parents=True);p.write_bytes(self.pixels);return p
    def finish(self,attempt,path):return ledger.generation_end(self.run,attempt,'success',[('original',path)])
    def test_cli_init_enables_immutable_attempt_policy(self):
        argv=[sys.executable,str(Path(ledger.__file__)),'init',str(self.run),'--skill','fixture='+str(self.skill),'--request-file',str(self.request)]
        for key,value in self.budgets.items():argv.extend(['--'+key.replace('_','-'),str(value)])
        result=subprocess.run(argv,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(ledger.inspect(self.run)[0]['artifact_policy']['attempt_unique_paths'])
    def test_generic_source_name_rejected_before_completion(self):
        self.init();attempt=self.start();p=self.root/'candidate.png';p.write_bytes(self.pixels)
        with self.assertRaisesRegex(ledger.LedgerError,'exact attempt ID'):self.finish(attempt,p)
        self.assertEqual(ledger.inspect(self.run)[2]['missing_generation_completions'],[attempt])
    def test_unique_sources_preserve_earlier_bytes_and_reject_reused_path(self):
        self.init();first=self.start();source=self.source(first);self.finish(first,source)
        second=self.start('two')
        with self.assertRaisesRegex(ledger.LedgerError,'exact attempt ID|already used'):self.finish(second,source)
        new=self.source(second);new.write_bytes(self.pixels+b'new synthetic bytes');self.finish(second,new)
        resolved=ledger.resolve_artifact(self.run,hashlib.sha256(self.pixels).hexdigest())
        self.assertEqual(Path(resolved['resolved_file']).read_bytes(),self.pixels)
    def test_hash_resolution_ignores_reused_historical_filename(self):
        self.init();attempt=self.start();source=self.source(attempt);self.finish(attempt,source)
        historical_hash=hashlib.sha256(source.read_bytes()).hexdigest()
        source.rename(source.with_name('rejected-original.png'));source.write_bytes(b'new unrelated candidate')
        result=ledger.resolve_artifact(self.run,historical_hash,source)
        self.assertEqual(result['historical_source_status'],'hash_mismatch_reused_or_changed_path')
        self.assertEqual(Path(result['resolved_file']).read_bytes(),self.pixels)
        with self.assertRaisesRegex(ledger.LedgerError,'source hash'):ledger.verify_attempt_source(self.run,attempt,source)
    def test_hash_resolution_works_after_relocation_and_original_removal(self):
        self.init();attempt=self.start();source=self.source(attempt);self.finish(attempt,source)
        expected=hashlib.sha256(source.read_bytes()).hexdigest();source.unlink()
        relocated=self.root/'relocated';shutil.copytree(self.run,relocated)
        result=ledger.resolve_artifact(relocated,expected,source)
        self.assertEqual(result['historical_source_status'],'missing_or_unsafe_path')
        self.assertTrue(Path(result['resolved_file']).is_relative_to(relocated))
        self.assertEqual(Path(result['resolved_file']).read_bytes(),self.pixels)
    def test_verified_evidence_source_can_replay_without_original_path(self):
        self.init();attempt=self.start();source=self.source(attempt);self.finish(attempt,source)
        expected=hashlib.sha256(source.read_bytes()).hexdigest();source.unlink()
        resolved=ledger.resolve_artifact(self.run,expected)['resolved_file']
        output=self.root/'replay'/attempt/'native.png'
        result=ledger.verify_attempt_source(self.run,attempt,resolved,output)
        self.assertEqual(result['source_sha256'],expected)
        cmd=['bash',str(Path(ledger.__file__).with_name('prepare_pixels.sh')),'--input',resolved,'--output',str(output),'--width','4','--height','4','--colors','2','--run',str(self.run),'--attempt-id',attempt]
        completed=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertTrue(output.is_file())
    def test_unknown_hash_and_corrupt_evidence_do_not_resolve(self):
        self.init();attempt=self.start();source=self.source(attempt);end=self.finish(attempt,source)
        with self.assertRaisesRegex(ledger.LedgerError,'No captured'):ledger.resolve_artifact(self.run,'0'*64)
        captured=self.run/end['data']['outputs'][0]['path'];captured.chmod(0o644);captured.write_bytes(b'tampered')
        with self.assertRaisesRegex(ledger.LedgerError,'corrupt'):ledger.resolve_artifact(self.run,hashlib.sha256(self.pixels).hexdigest())
    def test_candidate_namespace_and_source_hash_are_checked(self):
        self.init();attempt=self.start();source=self.source(attempt);self.finish(attempt,source)
        with self.assertRaisesRegex(ledger.LedgerError,'exact attempt ID'):ledger.verify_attempt_source(self.run,attempt,source,self.root/'candidate.png')
        result=ledger.verify_attempt_source(self.run,attempt,source,self.root/'candidates'/attempt/'native.png')
        self.assertEqual(result['attempt_id'],attempt)
    def test_normalization_binds_attempt_and_preserves_source(self):
        self.init();attempt=self.start();source=self.source(attempt);self.finish(attempt,source)
        output=self.root/'candidates'/attempt/'native.png'
        cmd=['bash',str(Path(ledger.__file__).with_name('prepare_pixels.sh')),'--input',str(source),'--output',str(output),'--width','4','--height','4','--colors','2','--run',str(self.run),'--attempt-id',attempt]
        result=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        record=json.loads(output.with_suffix('.provenance.json').read_text())
        self.assertEqual(record['generation_attempt_id'],attempt)
        self.assertEqual(record['source']['sha256'],hashlib.sha256(self.pixels).hexdigest())
        self.assertEqual(source.read_bytes(),self.pixels)
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)

if __name__=='__main__':unittest.main()
