#!/usr/bin/env python3
"""Report explicit documentation read sets, not inferred model token use or wall time."""
import argparse
import json
from pathlib import Path
import re

NAMES = ('character-identity', 'multi-view-reference', 'action-pose-design', 'refine-pixel-art', 'animate-pixel-sprite', 'export-to-aseprite')

def measure(root, files):
    items = []
    for f in files:
        p = root / f
        content = p.read_text()
        items.append({'path': f, 'bytes': len(content.encode()), 'words': len(content.split()), 'lines': len(content.splitlines())})
    return {'files': items, 'total_bytes': sum(x['bytes'] for x in items), 'total_words': sum(x['words'] for x in items)}

def report(root, candidate):
    result = {'entrypoints': {}, 'scenarios': {}, 'reference_edges': {}, 'documentation_graph': {}}
    for name in NAMES:
        base = 'skills/' + name + '/'
        result['entrypoints'][name] = measure(root, [base+'SKILL.md'])
        text = (root/base/'SKILL.md').read_text()
        refs_available = {p.name: base+'references/'+p.name for p in (root/base/'references').glob('*.md')}
        for document in [root/base/'SKILL.md', *(root/base/'references').glob('*.md')]:
            body=document.read_text()
            result['documentation_graph'][document.relative_to(root).as_posix()] = sorted({target for filename,target in refs_available.items() if filename in body})
        result['reference_edges'][name] = sorted(set(re.findall(r'references/[a-z0-9-]+\.md', text)))
        if name == 'export-to-aseprite':
            refs = ['runtime.md','input-contract.md','verification.md']
            result['scenarios'][name + '/export'] = measure(root,[base+'SKILL.md']+[base+'references/'+x for x in refs])
            continue
        for mode in ['standalone','full']:
            refs = ['runtime.md','project-contract.md']
            refs += ['standalone-records.md'] if candidate and mode=='standalone' else ['run-records.md','portable-handoff.md']
            # Full command reference counted consistently; a reader may load only a section.
            refs += ['pixel-tooling.md']
            if name == 'animate-pixel-sprite':
                refs += ['visual-review.md']
            result['scenarios'][name+'/'+mode] = measure(root,[base+'SKILL.md']+[base+'references/'+x for x in refs])
            if name == 'character-identity' and mode == 'standalone' and not candidate:
                minimal = [x for x in refs if x != 'run-records.md']
                result['scenarios'][name+'/standalone-no-explicit-ledger-read'] = measure(root,[base+'SKILL.md']+[base+'references/'+x for x in minimal])
            if name == 'animate-pixel-sprite':
                local = refs + ['action-continuity.md'] + (['local-motion.md'] if candidate else [])
                result['scenarios'][name+'/'+mode+'-local-linked-action'] = measure(root,[base+'SKILL.md']+[base+'references/'+x for x in local])
                full_body = refs + ['full-body-motion.md']
                result['scenarios'][name+'/'+mode+'-full-body'] = measure(root,[base+'SKILL.md']+[base+'references/'+x for x in full_body])
    return result

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('baseline', type=Path); p.add_argument('candidate', type=Path)
    a=p.parse_args()
    print(json.dumps({'method':'Whitespace words and UTF-8 bytes, explicit comparable read sets. Not token counts or observed runtime overhead. Baseline standalone set models its full evidence route; character identity only explicitly calls run-records for full flow/trial, so report that reference separately. Optional local/full-body/action details excluded from common cases. Command references counted whole conservatively.', 'baseline':report(a.baseline,False),'candidate':report(a.candidate,True)},indent=2))
