#!/usr/bin/env python3
"""Validate self-contained skill packaging and run synthetic tests only."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NAMES = {'character-identity', 'multi-view-reference', 'action-pose-design',
         'refine-pixel-art', 'animate-pixel-sprite', 'export-to-aseprite'}

def check(condition, message):
    if not condition:
        raise ValueError(message)

def main():
    subprocess.run([sys.executable, str(ROOT / 'scripts/build_packages.py'), '--check'], check=True)
    subprocess.run([sys.executable, str(ROOT / 'scripts/test_generated_parity.py')], check=True)
    skills = ROOT / 'skills'
    check({p.name for p in skills.iterdir() if p.is_dir()} == NAMES,
          'Expected exactly six skill directories')
    for name in sorted(NAMES):
        directory = skills / name
        text = (directory / 'SKILL.md').read_text(encoding='utf-8')
        check(text.startswith('---\n'), f'{name}: missing frontmatter')
        frontmatter = text.split('---', 2)[1]
        check(re.search(r'^name: ' + re.escape(name) + r'$', frontmatter, re.M),
              f'{name}: frontmatter name mismatch')
        check(re.search(r'^description: .+', frontmatter, re.M), f'{name}: no description')
        check((directory / 'references/runtime.md').is_file(), f'{name}: no runtime guide')
        check('references/runtime.md' in text, f'{name}: runtime guide not linked')
        for reference in set(re.findall(r'(?:references|assets|scripts)/[a-zA-Z0-9_.-]+\.(?:md|json|py|sh)', text)):
            check((directory / reference).is_file(), f'{name}: missing entrypoint reference {reference}')
        check('claude' not in frontmatter.lower(), f'{name}: nonportable Claude-specific frontmatter')
        for file in directory.rglob('*'):
            check(not file.is_symlink(), f'Unexpected symlink: {file}')
            if file.suffix == '.json':
                json.loads(file.read_text(encoding='utf-8'))
            if file.suffix == '.py':
                compile(file.read_text(encoding='utf-8'), str(file), 'exec')
            if file.suffix in ('.md', '.yaml', '.json', '.py', '.sh'):
                content = file.read_text(encoding='utf-8')
                check(not re.search(r'/workspace/|/home/agent/|/mnt/data/|skill://|skill-[0-9a-f]{20}', content),
                      f'Private/environment-specific locator: {file}')
    core = sorted(NAMES - {'export-to-aseprite'})
    for folder in ('scripts', 'references', 'assets'):
        baseline = ROOT / 'authoring/core' / folder
        expected = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in baseline.iterdir() if p.is_file() and p.name != 'icon.svg'}
        for name in core[1:]:
            actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in (skills / name / folder).iterdir()
                      if p.is_file() and p.name in expected}
            check(actual == expected, f'Shared core {folder} drift: {name}')
    print('Packaging checks passed for six independent skill directories', flush=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    failed = []
    for name in sorted(NAMES):
        print(f'\nTesting {name}', flush=True)
        result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-p', 'test_*.py'],
                                cwd=skills / name / 'scripts', env=env)
        if result.returncode:
            failed.append(name)
    check(not failed, 'Test failures: ' + ', '.join(failed))
    print('\nAll six test suites completed; inspect unittest summaries for skips.')

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as exc:
        print(f'Validation failed: {exc}', file=sys.stderr)
        sys.exit(1)
