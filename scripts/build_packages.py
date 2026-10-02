#!/usr/bin/env python3
"""Generate self-contained packages from canonical authoring sources; --check detects drift."""
import argparse
import hashlib
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CORE = ('character-identity', 'multi-view-reference', 'action-pose-design', 'refine-pixel-art', 'animate-pixel-sprite')
NAMES = (*CORE, 'export-to-aseprite')

def inventory(root):
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise ValueError(f'Symlink forbidden: {p}')
        if p.is_file():
            result[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result

def generate(destination):
    for name in NAMES:
        target = destination / name
        if name in CORE:
            shutil.copytree(ROOT / 'authoring/core', target)
            # Overlay contains only unique entrypoint/agent/icon files.
            shutil.copytree(ROOT / 'authoring/skills' / name, target, dirs_exist_ok=True)
        else:
            shutil.copytree(ROOT / 'authoring/skills' / name, target)
        (target / 'SKILL.md.in').rename(target / 'SKILL.md')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / 'skills'
        generate(output)
        expected = inventory(output)
        actual = inventory(ROOT / 'skills')
        changed = sorted(k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k))
        if args.check:
            if changed:
                raise SystemExit('Generated package drift:\n' + '\n'.join(changed))
            print(f'All-resource parity passed: {len(expected)} files in six packages')
            return
        for name in NAMES:
            dest = ROOT / 'skills' / name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(output / name, dest)
        print(f'Generated six independent packages ({len(expected)} files; {len(changed)} changed)')

if __name__ == '__main__':
    main()
