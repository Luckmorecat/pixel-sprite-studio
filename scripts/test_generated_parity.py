#!/usr/bin/env python3
"""Check that canonical package parity catches reference/template drift as well as code."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build', ROOT/'scripts/build_packages.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)

class Packaging(unittest.TestCase):
    def test_all_resources_and_no_nested_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'skills';build.generate(out)
            self.assertEqual(build.inventory(out),build.inventory(ROOT/'skills'))
            self.assertEqual(len(list(out.rglob('SKILL.md'))),6)
            self.assertFalse(list((ROOT/'authoring').rglob('SKILL.md')))
            self.assertFalse(list(out.rglob('SKILL.md.in')))
            for folder,filename in [('references','runtime.md'),('assets','project.template.json'),('scripts','project_config.py')]:
                p=out/'character-identity'/folder/filename
                before=build.inventory(out)
                p.write_bytes(p.read_bytes()+b'\n')
                self.assertNotEqual(before,build.inventory(out))
                self.assertNotEqual(build.inventory(ROOT/'skills'),build.inventory(out))

if __name__=='__main__':unittest.main()
