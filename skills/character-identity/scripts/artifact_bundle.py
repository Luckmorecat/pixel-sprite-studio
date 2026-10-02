#!/usr/bin/env python3
"""Create/check self-contained, hash-verified pixel handoffs; never judge artwork.

Commands: template SPEC.json | create SPEC.json OUT_DIR | check BUNDLE_DIR.
Paths in editable specs are relative to the spec and may not escape that root.
The template is deliberately an unaccepted study; replace every example value.
Supports use exactly one of file or directory plus a SUPPORT_ROLES role. A tree
may name an entrypoint and dependencies (literal tree-root-relative file paths).
Trees land in support-trees/<basename> with exact bytes and relative layout;
directories is a generated empty-directory-inclusive inventory, never spec input.
Single HTML/CSS/JS supports require a directory tree. Static local references are
checked without executing JavaScript, opening a browser, or fetching URLs. List
runtime-computed file dependencies explicitly; a pass is not observed playback.
PNG inspection uses ImageMagick. Config/evidence handling uses the standard library.
A checker PASS means structural/technical integrity, not visual approval. Visual
acceptance is a recorded human/explicitly delegated decision bound to exact hashes.
"""
from __future__ import annotations
import argparse
import copy
from collections import Counter
from fractions import Fraction
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import struct
import stat
import subprocess
import sys
import tempfile
import zlib
import unicodedata
from urllib.parse import unquote, urlsplit

from project_config import ProjectError, integer, load_project, pair, read_json, relative_file, sha256

SCHEMA = 'pixel-handoff/1.0'
ROLES = {'identity', 'view', 'action', 'native_master', 'pose'}
STAGES = {'design', 'identity', 'views', 'action', 'refinement', 'animation'}
STATUSES = {'study', 'accepted', 'needs_revision'}
TECHNICAL = {'passed', 'failed', 'unverified'}
VISUAL = {'accepted', 'rejected', 'unverified'}
SUPPORT_ROLES = {'request', 'review', 'provenance', 'budget', 'delegation', 'approval', 'other', 'playback'}
# Bounded explicit trees only; do not discover/copy dependencies outside them.
MAX_SUPPORT_ENTRIES = 10000
MAX_SUPPORT_FILE_BYTES = 64 * 1024 * 1024
MAX_SUPPORT_BYTES = 256 * 1024 * 1024
MAX_SUPPORT_TEXT_BYTES = 8 * 1024 * 1024
LINKING_SUFFIXES = {'.html', '.htm', '.xhtml', '.css', '.js', '.mjs'}
NATIVE_ROLES = {'native_master', 'pose'}


class BundleError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise BundleError(message)


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f'{label} must be nonempty text')
    return value


def ident(value, label):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value),
            f'{label} must be a short portable identifier')
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as output:
        json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write('\n')


def safe_file(root, name, label='file'):
    return relative_file(root, name, label)


def no_symlinks(root):
    root = Path(root)
    require(not root.is_symlink(), 'Bundle/run root must not be a symlink')
    for path in root.rglob('*'):
        require(not path.is_symlink(), f'Symlinks are not portable: {path.relative_to(root)}')
        require(path.is_file() or path.is_dir(), f'Only regular files/directories are allowed: {path.relative_to(root)}')


def support_path(value, label):
    """Literal portable paths, never URLs; URL references have separate rules."""
    text(value, label)
    require(not any(c in value for c in '\\%?#:<>|"*') and not any(ord(c) < 32 or ord(c) == 127 for c in value),
            f'{label} must be a literal relative POSIX path, not an encoded path or URL')
    parts = value.split('/')
    require(len(parts) <= 64 and all(p not in ('', '.', '..') and not p.endswith((' ', '.')) for p in parts),
            f'{label} must be a contained relative path without traversal')
    for part in parts:
        require(not re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', part),
                f'{label} contains a nonportable reserved filename')
    return parts


def support_directory(root, value):
    parts = support_path(value, 'support.directory')
    path = Path(root)
    for part in parts:
        path = path / part
        require(not path.is_symlink(), f'Symlinks are not portable: {value}')
        require(path.is_dir(), f'Support directory is missing or not a directory: {value}')
    require(path.resolve().is_relative_to(Path(root).resolve()), 'Support directory escapes its root')
    return path


def scan_support_tree(root):
    """Inventory all regular files and directories without following symlinks."""
    root = Path(root)
    require(not root.is_symlink() and root.is_dir(), 'Support tree must be a real directory')
    files, directories, seen, total = [], [], set(), 0
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative = path.relative_to(root).as_posix()
                support_path(relative, 'support tree member')
                folded = unicodedata.normalize('NFC', relative).casefold()
                require(folded not in seen, f'Conflicting support tree destinations: {relative}')
                seen.add(folded)
                require(len(seen) <= MAX_SUPPORT_ENTRIES, 'Support tree exceeds entry safety limit')
                mode = entry.stat(follow_symlinks=False).st_mode
                require(not stat.S_ISLNK(mode), f'Symlinks are not portable: {relative}')
                if stat.S_ISDIR(mode):
                    directories.append(relative)
                    pending.append(path)
                else:
                    require(stat.S_ISREG(mode), f'Only regular support files/directories are allowed: {relative}')
                    size = entry.stat(follow_symlinks=False).st_size
                    require(size <= MAX_SUPPORT_FILE_BYTES, 'Support file exceeds byte safety limit')
                    total += size
                    require(total <= MAX_SUPPORT_BYTES, 'Support tree exceeds byte safety limit')
                    files.append(relative)
    require(files and total > 0, 'Support directory must contain nonempty evidence')
    return sorted(directories), sorted(files)


def css_references(content):
    # Decode CSS escapes before treating url()/@import strings as URL references.
    def unescape(value):
        def replace(match):
            if match.group(1):
                code = int(match.group(1), 16)
                require(0 < code <= 0x10ffff, 'Invalid CSS URL escape')
                return chr(code)
            return match.group(2) or ''
        return re.sub(r'\\(?:([0-9a-fA-F]{1,6})[ \t\r\n\f]?|([^\r\n\f])|\r\n|[\r\n\f])', replace, value)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.S)
    values = []
    for match in re.finditer(r'''(?is)url\(\s*(?:"((?:\\.|[^"\\])*)"|'((?:\\.|[^'\\])*)'|([^)]*?))\s*\)''', content):
        values.append(unescape(next(value for value in match.groups() if value is not None).strip()))
    for match in re.finditer(r'''(?is)@import\s+(?:"((?:\\.|[^"\\])*)"|'((?:\\.|[^'\\])*)')''', content):
        values.append(unescape(next(value for value in match.groups() if value is not None)))
    return values


def script_references(content):
    """A conservative static supplement, not a JavaScript parser or execution."""
    return [match.group(2) for match in re.finditer(
        r'''\b(?:fetch|import)\s*\(\s*(["'])([^"'\r\n\\]+)\1\s*[,)]''', content)]


class SupportHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.references, self.block, self.content = [], None, []
        self.json_block = False

    def handle_starttag(self, tag, attributes):
        require(len(attributes) == len({key for key, value in attributes}), 'Duplicate support HTML attributes are ambiguous')
        attrs = dict(attributes)
        require(tag != 'base', 'Support HTML must not change its relative URL base')
        for key in ('src', 'href', 'poster'):
            if attrs.get(key) is not None:
                self.references.append(attrs[key])
        if attrs.get('style'):
            self.references.extend(css_references(attrs['style']))
        if tag in ('style', 'script'):
            self.block, self.content = tag, []
            self.json_block = tag == 'script' and attrs.get('type', '').lower() == 'application/json'

    def handle_startendtag(self, tag, attributes):
        self.handle_starttag(tag, attributes)
        self.handle_endtag(tag)

    def handle_data(self, data):
        if self.block:
            self.content.append(data)

    def handle_endtag(self, tag):
        if tag != self.block:
            return
        content = ''.join(self.content)
        if tag == 'style':
            self.references.extend(css_references(content))
        elif self.json_block:
            # Native PNG playback embeds its exact frame paths in JSON, rather
            # than literal img src attributes. Validate these without running JS.
            try:
                value = json.loads(content)
            except (ValueError, RecursionError) as exc:
                raise BundleError('Support HTML contains invalid inline JSON') from exc
            pending = [value]
            while pending:
                item = pending.pop()
                if isinstance(item, dict):
                    for key, value in item.items():
                        if key in ('file', 'src', 'href') and isinstance(value, str):
                            self.references.append(value)
                        elif isinstance(value, (dict, list)):
                            pending.append(value)
                elif isinstance(item, list):
                    pending.extend(item)
        else:
            self.references.extend(script_references(content))
        self.block, self.content = None, []


def support_references(path):
    if path.suffix.lower() not in LINKING_SUFFIXES:
        return []
    require(path.stat().st_size <= MAX_SUPPORT_TEXT_BYTES, 'Support linking document exceeds text safety limit')
    try:
        content = path.read_text(encoding='utf-8-sig')
    except UnicodeError as exc:
        raise BundleError('Support HTML/CSS/JS must use UTF-8') from exc
    if path.suffix.lower() == '.css':
        return css_references(content)
    if path.suffix.lower() in ('.js', '.mjs'):
        return script_references(content)
    parser = SupportHTML()
    parser.feed(content)
    parser.close()
    require(parser.block is None, 'Support HTML has an unclosed style/script block')
    return parser.references


def validate_support_reference(root, path, reference):
    reference = reference.strip()
    if not reference or reference.startswith('#'):
        return 'fragment'
    require('\\' not in reference and not any(ord(c) < 32 or ord(c) == 127 for c in reference),
            'Support reference contains an unsafe separator/control character')
    try:
        url = urlsplit(reference)
    except ValueError as exc:
        raise BundleError('Invalid support URL reference') from exc
    if url.scheme.lower() == 'data':
        return 'embedded'
    if url.scheme.lower() in ('http', 'https', 'mailto', 'tel') or (url.netloc and not url.scheme):
        return 'external'
    require(not url.scheme and not url.netloc, 'Support reference uses an unsupported URL scheme')
    local = url.path
    for _ in range(8):
        decoded = unquote(local, errors='strict')
        if decoded == local:
            break
        local = decoded
    require('%' not in local and '\\' not in local and ':' not in local and
            not any(ord(c) < 32 or ord(c) == 127 for c in local), 'Unsafe encoded support reference')
    if not local:
        return 'fragment'
    require(not local.startswith('/'), 'Support reference must be relative to its declared tree')
    target = (path.parent / local).resolve()
    require(target.is_relative_to(root.resolve()), f'Support reference escapes its declared tree: {reference}')
    require(target.is_file() or target.is_dir(), f'Missing support dependency: {reference} from {path.relative_to(root)}')
    return 'local'


def check_support_tree(root, support):
    directories, files = scan_support_tree(root)
    require(support.get('directories') == directories, 'Support directory inventory is stale or incomplete')
    if support.get('entrypoint') is not None:
        support_path(support['entrypoint'], 'support.entrypoint')
        require((root / support['entrypoint']).is_file(), 'Missing support entrypoint')
    dependencies = support.get('dependencies', [])
    require(isinstance(dependencies, list) and all(isinstance(name, str) for name in dependencies) and
            len(dependencies) == len(set(dependencies)),
            'support.dependencies must list distinct tree-root-relative files')
    for name in dependencies:
        support_path(name, 'support.dependencies')
        require((root / name).is_file(), f'Missing declared support dependency: {name}')
    counts = Counter()
    for name in files:
        path = root / name
        for reference in support_references(path):
            counts[validate_support_reference(root, path, reference)] += 1
    return counts


def check_support_record(support):
    require(isinstance(support, dict) and support.get('role') in SUPPORT_ROLES, 'Unknown support role')
    require(('file' in support) != ('directory' in support), 'Support needs exactly one of file or directory')
    if 'file' in support:
        require(not any(key in support for key in ('entrypoint', 'dependencies', 'directories')),
                'Tree entrypoint/dependencies/directories require support.directory')
        name = text(support['file'], 'support.file')
        require(Path(name).suffix.lower() not in LINKING_SUFFIXES,
                'Linking HTML/CSS/JS support files require support.directory to preserve relative dependencies')
    else:
        support_path(support['directory'], 'support.directory')
        require(not any(key in support for key in ('target', 'destination')),
                'Support tree destination is derived; target/destination cannot be overridden')


def image_info(path):
    """Verify PNG container and decode exact visible pixels (no resizing)."""
    path = Path(path)
    data = path.read_bytes()
    require(data[:8] == b'\x89PNG\r\n\x1a\n', f'Expected a PNG: {path.name}')
    offset, dims, ended = 8, None, False
    while offset < len(data):
        require(offset + 12 <= len(data), f'Truncated PNG: {path.name}')
        size = struct.unpack_from('>I', data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + size + 12
        require(end <= len(data), f'Truncated PNG chunk: {path.name}')
        payload = data[offset + 8:end - 4]
        require(zlib.crc32(kind + payload) & 0xffffffff == struct.unpack_from('>I', data, end - 4)[0],
                f'PNG CRC mismatch: {path.name}')
        if offset == 8:
            require(kind == b'IHDR' and size == 13, f'Invalid PNG header: {path.name}')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            require(0 < width <= 65535 and 0 < height <= 65535 and width * height <= 16777216, 'PNG dimensions exceed safety limit')
            require(depth in (1, 2, 4, 8) and compression == filtering == 0 and interlace in (0, 1), 'Unsupported PNG encoding')
            dims = [width, height]
        require(kind != b'acTL', 'Animation is not a single native drawing')
        if kind == b'IEND':
            require(size == 0 and end == len(data), 'Invalid PNG end or trailing bytes')
            ended = True
            break
        offset = end
    require(dims and ended, 'Incomplete PNG')
    program = shutil.which('magick') or shutil.which('convert')
    require(program, 'ImageMagick is required for actual PNG checks')
    try:
        result = subprocess.run([program, 'PNG:' + str(path.resolve()), '-alpha', 'on', '-depth', '8', 'RGBA:-'],
                                capture_output=True, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BundleError(f'PNG decoder failed: {exc}') from exc
    require(result.returncode == 0, f'PNG decoding failed: {path.name}')
    raw = result.stdout
    require(len(raw) == dims[0] * dims[1] * 4, 'PNG decoded size mismatch')
    pixels = [tuple(raw[i:i + 4]) for i in range(0, len(raw), 4)]
    opaque = [i for i, p in enumerate(pixels) if p[3]]
    colors = sorted({'#%02x%02x%02x' % p[:3] for p in pixels if p[3]})
    margin = None
    if opaque:
        xs, ys = [i % dims[0] for i in opaque], [i // dims[0] for i in opaque]
        margin = min(min(xs), min(ys), dims[0] - 1 - max(xs), dims[1] - 1 - max(ys))
    return {'sha256': hashlib.sha256(data).hexdigest(), 'dimensions_px': dims,
            'rgba_sha256': hashlib.sha256(raw).hexdigest(), 'visible_palette': colors,
            'binary_alpha': all(p[3] in (0, 255) for p in pixels), 'min_margin': margin}


def check_status(record, label):
    require(record.get('status') in STATUSES, f'{label}.status must be study, accepted, or needs_revision')
    require(record.get('technical_status') in TECHNICAL, f'{label}.technical_status is required')
    require(record.get('visual_status') in VISUAL, f'{label}.visual_status is required')
    if record['status'] == 'accepted':
        require(record['technical_status'] == 'passed' and record['visual_status'] == 'accepted',
                f'{label} cannot be accepted without separate technical pass and recorded visual acceptance')
    if record['status'] == 'needs_revision':
        require(record['technical_status'] == 'failed' or record['visual_status'] == 'rejected',
                f'{label}.needs_revision must record the failed gate')
    if record['visual_status'] == 'accepted':
        require(record['status'] == 'accepted', f'{label} visual acceptance must use accepted status')


def budget_from_attempts(attempts, budget):
    require(isinstance(attempts, list), 'Budget evidence requires attempts array, including failed starts')
    by_id, repairs, by_pose = {}, 0, Counter()
    for attempt in attempts:
        require(isinstance(attempt, dict), 'Attempt must be an object')
        attempt_id = ident(attempt.get('attempt_id'), 'attempt_id')
        require(attempt_id not in by_id, 'Duplicate budget attempt ID')
        text(attempt.get('stage'), 'attempt.stage')
        pose = attempt.get('pose_id')
        if pose is not None:
            ident(pose, 'pose_id')
        require(attempt.get('outcome') in ('success', 'failed', 'cancelled', 'pending'), 'Attempt outcome is required')
        original = attempt.get('repair_of')
        if original is not None:
            require(original in by_id, 'Repair must reference an earlier attempt')
            require(by_id[original].get('pose_id') == pose, 'Repair changed semantic pose ID')
            repairs += 1
            if pose is not None:
                by_pose[pose] += 1
        by_id[attempt_id] = attempt
    require(len(attempts) <= budget['max_calls'], 'Generation count exceeds project budget.max_calls')
    total_cap = budget.get('max_total_repairs')
    pose_cap = budget.get('repairs_per_pose')
    if total_cap is not None:
        require(repairs <= total_cap, 'Cumulative repair count exceeds project budget.max_total_repairs')
    if pose_cap is not None:
        require(all(n <= pose_cap for n in by_pose.values()), 'Semantic pose repair count exceeds project budget.repairs_per_pose')
    return {'attempted_calls': len(attempts), 'repairs_total': repairs, 'repairs_by_pose': dict(sorted(by_pose.items())),
            'remaining_calls': budget['max_calls'] - len(attempts),
            'remaining_repairs_total': None if total_cap is None else total_cap - repairs,
            'remaining_repairs_by_pose': {} if pose_cap is None else {k: pose_cap - v for k, v in sorted(by_pose.items())},
            'pending_attempts': [a['attempt_id'] for a in attempts if a['outcome'] == 'pending']}


def run_budget(run, project):
    import run_ledger
    manifest, events, report = run_ledger.inspect(run)
    require(report['integrity_ok'], 'Run ledger integrity failed: ' + '; '.join(report.get('errors', [])))
    budget = manifest['budgets']
    expected = {'max_attempts': 'max_calls', 'max_total_repairs': 'max_total_repairs', 'max_pose_repairs': 'repairs_per_pose'}
    for ledger_key, project_key in expected.items():
        if project_key in project['budget']:
            require(budget.get(ledger_key) == project['budget'][project_key],
                    f'Run budget {ledger_key} conflicts with project {project_key}; continue the same bounded run')
    outcomes = {e['data']['attempt_id']: e['data']['outcome'] for e in events if e['type'] == 'generation-end'}
    attempts = [{'attempt_id': e['data']['attempt_id'], 'stage': e['data']['stage'], 'pose_id': e['data']['pose'],
                 'repair_of': e['data']['repair_of'], 'outcome': outcomes.get(e['data']['attempt_id'], 'pending')}
                for e in events if e['type'] == 'generation-start']
    return budget_from_attempts(attempts, project['budget']), attempts


def check_native(asset, info, project):
    native = asset.get('native')
    require(isinstance(native, dict), f'{asset["id"]} needs explicit native canvas/palette/grid/anchor contract')
    require(info['dimensions_px'] == project['native_canvas_px'], f'{asset["id"]} native canvas conflicts with project')
    require(native.get('grid_px') == 1 and type(native.get('grid_px')) is int, 'Native grid_px must be exactly 1')
    anchor = pair(native.get('anchor_px'), 'native.anchor_px', zero=True)
    require(anchor[0] < info['dimensions_px'][0] and anchor[1] < info['dimensions_px'][1], 'Native anchor outside canvas')
    if project.get('anchor_px') is not None:
        require(anchor == project['anchor_px'], 'Native anchor conflicts with project')
    palette = native.get('palette')
    require(isinstance(palette, list) and palette and all(isinstance(c, str) and re.fullmatch(r'#[0-9a-f]{6}', c) for c in palette),
            'Native palette must list lowercase #rrggbb colors')
    require(len(palette) == len(set(palette)), 'Native palette has duplicate entries')
    require(len(palette) <= project['limits']['palette_max'], 'Native palette exceeds project palette_max')
    require(set(info['visible_palette']) <= set(palette), 'Visible native colors are absent from declared shared palette')
    require(info['binary_alpha'], 'Native PNG does not have binary alpha')
    require(info['min_margin'] is not None and info['min_margin'] >= project['limits']['min_margin'], 'Native PNG is blank or violates min_margin')
    grid = native.get('grid')
    require(isinstance(grid, dict), 'Native grid must record source_canvas_px and crop')
    require(pair(grid.get('source_canvas_px'), 'native.grid.source_canvas_px') == asset['source']['dimensions_px'],
            'Native grid source dimensions conflict with actual source')
    crop = grid.get('crop')
    if crop is not None:
        require(isinstance(crop, list) and len(crop) == 4, 'Native grid crop must be [x,y,width,height] or null')
        for i, value in enumerate(crop):
            integer(value, f'crop[{i}]', 0 if i < 2 else 1, 65535)
        require(crop[0] + crop[2] <= grid['source_canvas_px'][0] and crop[1] + crop[3] <= grid['source_canvas_px'][1], 'Native grid crop exceeds source')
        source_size = crop[2:]
    else:
        source_size = grid['source_canvas_px']
    require(source_size[0] * info['dimensions_px'][1] == source_size[1] * info['dimensions_px'][0], 'Native grid would distort source aspect ratio')
    # Source resolution is provenance, not a reason to reject equivalent native grids.
    # Compare normalized crop windows; explicit strict locks additionally bind pixels.
    effective_crop = crop or [0, 0, *grid['source_canvas_px']]
    normalized_crop = [str(Fraction(v, grid['source_canvas_px'][i % 2])) for i, v in enumerate(effective_crop)]
    locked = grid.get('lock_source_geometry', False)
    require(type(locked) is bool, 'lock_source_geometry must be a boolean')
    return {'canvas': info['dimensions_px'], 'palette': sorted(palette), 'grid_px': 1,
            'normalized_crop': normalized_crop, 'anchor_px': anchor,
            'locked_source': {'dimensions_px': grid['source_canvas_px'], 'crop': effective_crop} if locked else None}


def check_approval(root, asset):
    approval = asset.get('approval')
    require(isinstance(approval, dict), f'Accepted {asset["id"]} is missing approval evidence')
    require(approval.get('actor') in ('user', 'assistant'), 'Approval actor must distinguish user from assistant')
    require(approval.get('role') == asset['role'], 'Approval role does not match artifact role')
    require(approval.get('asset_sha256') == asset['sha256'], 'Approval is for a different/stale artifact hash')
    require(approval.get('source_sha256') == asset['source']['sha256'], 'Approval is for a different/stale input source hash')
    for key in ('evidence_file',):
        require(safe_file(root, approval.get(key), 'approval.' + key).stat().st_size > 0, 'Approval evidence must not be empty')
    text(approval.get('reason'), 'approval.reason')
    if approval['actor'] == 'assistant':
        require(safe_file(root, approval.get('delegation_file'), 'approval.delegation_file').stat().st_size > 0,
                'Assistant acceptance needs explicit task delegation evidence')
    elif approval.get('delegation_file') is not None:
        safe_file(root, approval['delegation_file'], 'approval.delegation_file')


def check_bundle(directory):
    root = Path(directory).resolve(strict=True)
    no_symlinks(Path(directory))
    manifest = read_json(root / 'bundle.json')
    require(manifest.get('schema_version') == SCHEMA, 'Unsupported handoff schema')
    require(manifest.get('stage') in STAGES, 'Unknown bundle stage')
    check_status(manifest, 'bundle')
    text(manifest.get('next_step'), 'next_step')
    # Check tree limits and local links before reading/hashing inventory bytes.
    supports = manifest.get('supports')
    require(isinstance(supports, list), 'supports must be an array')
    support_roles, tree_destinations, reference_counts = set(), set(), Counter()
    for support in supports:
        check_support_record(support)
        if 'directory' in support:
            parts = support_path(support['directory'], 'support.directory')
            require(len(parts) == 2 and parts[0] == 'support-trees', 'Invalid support tree destination')
            destination = unicodedata.normalize('NFC', support['directory']).casefold()
            require(destination not in tree_destinations, 'Conflicting support tree destinations')
            tree_destinations.add(destination)
            reference_counts.update(check_support_tree(support_directory(root, support['directory']), support))
        else:
            require(safe_file(root, support['file'], 'support.file').stat().st_size > 0, 'Support evidence is empty')
        support_roles.add(support['role'])
    require('request' in support_roles, 'Bundle must contain ordinary request/context evidence')
    inventory = manifest.get('inventory')
    require(isinstance(inventory, list) and inventory, 'Bundle inventory is required')
    expected = set()
    for entry in inventory:
        require(isinstance(entry, dict), 'Inventory entries must be objects')
        path = safe_file(root, entry.get('file'), 'inventory.file')
        name = path.relative_to(root).as_posix()
        require(name != 'bundle.json' and name not in expected, 'Duplicate/invalid inventory path')
        expected.add(name)
        require(sha256(path) == entry.get('sha256') and path.stat().st_size == entry.get('bytes'), f'Stale hash or size: {name}')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()} - {'bundle.json'}
    require(expected == actual, 'Bundle inventory does not cover exactly all files')
    project_path = safe_file(root, manifest.get('project'), 'project')
    project = load_project(project_path)
    require(project['_meta']['project_sha256'] == manifest.get('project_sha256'), 'Project hash changed')
    original = safe_file(root, manifest.get('original_project'), 'original_project')
    require(sha256(original) == manifest.get('original_project_sha256'), 'Original project provenance hash changed')
    original_data = read_json(original)
    rewritten_slots = {'profile', 'selected_design', 'approved_master', 'run_directory', '_meta'}
    require({k: v for k, v in original_data.items() if k not in rewritten_slots} ==
            {k: v for k, v in project.items() if k not in rewritten_slots},
            'Portable project changed original non-path requirements')
    require(project['_meta']['profile_sha256'] == manifest.get('profile_sha256'), 'Profile hash changed')
    require(manifest.get('asset_id') == project['asset_id'], 'Bundle asset_id conflicts with project')
    if manifest.get('run_directory'):
        run_path = root / manifest['run_directory']
        require(run_path.resolve().is_relative_to(root) and run_path.is_dir(), 'Invalid bundled run directory')
        counters, attempts = run_budget(run_path, project)
        require(manifest.get('continuation_mode') == 'same_run', 'Run continuation must preserve same_run mode')
    else:
        evidence = read_json(safe_file(root, manifest.get('budget_evidence_file'), 'budget_evidence_file'))
        counters = budget_from_attempts(evidence.get('attempts'), project['budget'])
        require(manifest.get('continuation_mode') == 'evidence_only', 'No run directory: continuation must be evidence_only')
    require(manifest.get('budget_state') == counters, 'Budget counters are stale or conflict with evidence')
    assets = manifest.get('assets')
    require(isinstance(assets, list) and assets, 'Bundle assets must be a nonempty array')
    by_id, pose_ids, sets = {}, {}, {}
    accepted_roles = set()
    for asset in assets:
        require(isinstance(asset, dict), 'Asset must be an object')
        aid = ident(asset.get('id'), 'asset.id')
        require(aid not in by_id, 'Duplicate asset ID')
        require(asset.get('role') in ROLES, f'Unknown role for {aid}')
        check_status(asset, aid)
        info = image_info(safe_file(root, asset.get('file'), f'{aid}.file'))
        for key in ('sha256', 'dimensions_px', 'rgba_sha256'):
            require(asset.get(key) == info[key], f'{aid} recorded {key} is incorrect/stale')
        require(info['dimensions_px'] == project['native_canvas_px'],
                f'{aid} artifact canvas differs from project native target; include the native study in file and original in source.file')
        source = asset.get('source')
        require(isinstance(source, dict), f'{aid} missing source provenance')
        source_info = image_info(safe_file(root, source.get('file'), f'{aid}.source.file'))
        for key in ('sha256', 'dimensions_px'):
            require(source.get(key) == source_info[key], f'{aid} actual source {key} differs from record')
        require(source.get('kind') in ('generated', 'supplied', 'derived'), 'Source kind must be generated/supplied/derived')
        for key in ('review_file', 'provenance_file'):
            require(safe_file(root, asset.get(key), f'{aid}.{key}').stat().st_size > 0, f'{aid} requires nonempty {key}')
        if asset['status'] == 'accepted':
            check_approval(root, asset)
            accepted_roles.add(asset['role'])
        elif asset.get('approval') is not None:
            require(False, f'{aid} has approval but is not accepted; preserve old approval in review evidence instead')
        if asset['role'] in NATIVE_ROLES:
            fingerprint = check_native(asset, info, project)
            sid = ident(asset.get('set_id'), 'set_id')
            if sid in sets:
                require(fingerprint == sets[sid], f'Native set {sid} canvas/palette/grid/anchor inconsistency')
            else:
                sets[sid] = fingerprint
        else:
            require(asset.get('native') is None and asset.get('set_id') is None, f'{aid} role must not claim a native master/pose contract')
        if asset['role'] == 'view':
            text(asset.get('view'), f'{aid}.view')
        if asset['role'] == 'pose':
            pid = ident(asset.get('pose_id'), 'pose_id')
            require(pid not in pose_ids, 'Duplicate semantic pose ID')
            pose_ids[pid] = asset
        elif asset.get('pose_id') is not None:
            require(False, 'Only role pose may declare pose_id')
        by_id[aid] = asset
    for asset in assets:
        for aid in asset.get('references', []):
            require(aid in by_id and aid != asset['id'], 'Asset references a missing/self artifact ID')
        if asset['role'] == 'pose':
            master_id = asset.get('master_id')
            require(master_id in by_id and by_id[master_id]['role'] == 'native_master', 'Pose references a missing/wrong-role native master')
            require(by_id[master_id].get('set_id') == asset['set_id'], 'Pose/master belong to different native sets')
            if asset['status'] == 'accepted':
                require(by_id[master_id]['status'] == 'accepted', 'Accepted pose requires accepted native master')
    timeline = manifest.get('timeline', [])
    require(isinstance(timeline, list), 'timeline must be an array')
    for entry in timeline:
        require(isinstance(entry, dict), 'Timeline entry must be an object')
        require(entry.get('pose_id') in pose_ids, 'Timeline references missing pose')
        integer(entry.get('duration_ms'), 'timeline.duration_ms', 1, 65535)
    if timeline:
        animation = project.get('animation')
        require(animation is not None, 'Timeline requires project animation constraints')
        require(sum(e['duration_ms'] for e in timeline) == animation['duration_ms'], 'Timeline duration differs from project')
        require(len(timeline) <= animation['max_timeline_entries'], 'Timeline exceeds entry cap')
        drawings = {pose_ids[e['pose_id']]['rgba_sha256'] for e in timeline}
        require(len(drawings) <= animation['max_unique_drawings'], 'Timeline exceeds unique drawing cap')
        require(len(drawings) >= animation.get('min_unique_drawings', 1), 'Timeline has too few unique drawings')
    required_ids = manifest.get('required_assets')
    require(isinstance(required_ids, list) and required_ids and len(required_ids) == len(set(required_ids)), 'required_assets must list distinct IDs')
    require(all(aid in by_id for aid in required_ids), 'Required asset is missing')
    needed_roles = {'identity'}
    if manifest['stage'] == 'views':
        needed_roles.add('view')
    if manifest['stage'] == 'action':
        needed_roles.add('action')
    if manifest['stage'] in ('refinement', 'animation'):
        needed_roles.add('native_master')
    if manifest['stage'] == 'animation':
        require(timeline, 'Animation handoff needs timeline and native poses')
        needed_roles.add('pose')
        require(all(pose_ids[e['pose_id']]['id'] in required_ids for e in timeline), 'Every timeline pose must be in required_assets')
    require(needed_roles <= {by_id[aid]['role'] for aid in required_ids}, 'Required asset roles do not cover handoff stage')
    for aid in required_ids:
        asset = by_id[aid]
        if asset['role'] == 'pose':
            require(asset['master_id'] in required_ids, 'Required pose must include its master in required_assets')
    ready = (manifest['status'] == 'accepted' and all(by_id[aid]['status'] == 'accepted' for aid in required_ids)
             and not counters['pending_attempts'])
    require(manifest.get('handoff_ready') is ready, 'handoff_ready is stale/inconsistent')
    if manifest['status'] == 'accepted':
        require(ready, 'Accepted handoff has unaccepted required assets or unfinished generation')
    return {'structural_integrity': 'passed', 'technical_checks': 'passed',
            'recorded_technical_status': manifest['technical_status'],
            'recorded_visual_status': manifest['visual_status'], 'visual_judgment_performed': False,
            'handoff_ready': ready, 'stage': manifest['stage'], 'next_step': manifest['next_step'],
            'continuation_mode': manifest['continuation_mode'], 'budget_state': counters,
            'asset_count': len(assets), 'bundle': str(root),
            'support_checks': {'tree_count': len(tree_destinations),
                               'local_references_checked': reference_counts['local'],
                               'external_references_not_fetched': reference_counts['external'],
                               'validation': 'static_local_references_only',
                               'dynamic_dependencies_evaluated': False, 'playback_execution_performed': False}}


def create_bundle(spec_path, output):
    spec_path = Path(spec_path).resolve(strict=True)
    spec = read_json(spec_path)
    require(spec.get('schema_version') == 1, 'Bundle spec schema_version must be integer 1')
    root = spec_path.parent
    project_path = safe_file(root, spec.get('project'), 'project')
    project = load_project(project_path)
    out = Path(output).absolute()
    require(not out.exists() and not out.is_symlink(), 'Output bundle must be a new directory')
    supports = spec.get('supports', [])
    require(isinstance(supports, list), 'supports must be an array')
    trees, destinations = {}, set()
    for index, support in enumerate(supports):
        check_support_record(support)
        if 'directory' in support:
            require('directories' not in support, 'Support directories inventory is generated, not a spec input')
            source = support_directory(root, support['directory'])
            require(not out.resolve().is_relative_to(source.resolve()), 'Output cannot be inside a copied support tree')
            destination = 'support-trees/' + source.name
            folded = unicodedata.normalize('NFC', destination).casefold()
            require(folded not in destinations, 'Conflicting support tree destinations')
            destinations.add(folded)
            trees[index] = (source, destination, scan_support_tree(source))
    out.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.bundle-', dir=out.parent))
    try:
        copies, tree_hashes = {}, {}
        def capture(name, category='evidence'):
            source = safe_file(root, name, category)
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            key = (str(source), digest)
            if key not in copies:
                basename = re.sub(r'[^A-Za-z0-9_.-]', '_', source.name)
                relative = f'{category}/{digest[:16]}-{basename}'
                dest = stage / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    dest.write_bytes(data)
                else:
                    require(dest.read_bytes() == data, 'Artifact filename hash collision')
                copies[key] = relative
            return copies[key]
        manifest = {key: copy.deepcopy(spec[key]) for key in ('stage', 'status', 'technical_status', 'visual_status', 'next_step', 'required_assets') if key in spec}
        manifest.update({'schema_version': SCHEMA, 'asset_id': project['asset_id'],
                         'assets': [], 'supports': [], 'timeline': copy.deepcopy(spec.get('timeline', []))})
        # Preserve original config bytes separately; only known path slots are rewritten.
        manifest['original_project'] = capture(spec['project'], 'provenance')
        manifest['original_project_sha256'] = project['_meta']['project_sha256']
        profile_data = Path(project['_meta']['profile_path']).read_bytes()
        (stage / 'profile.json').write_bytes(profile_data)
        manifest['profile_sha256'] = project['_meta']['profile_sha256']
        portable = copy.deepcopy(project)
        del portable['_meta']
        portable['profile'] = 'profile.json'
        for asset_spec in spec.get('assets', []):
            require(isinstance(asset_spec, dict), 'Asset spec must be an object')
            asset = copy.deepcopy(asset_spec)
            aid = ident(asset.get('id'), 'asset.id')
            image_path = safe_file(root, asset.get('file'), f'{aid}.file')
            info = image_info(image_path)
            for key in ('sha256', 'dimensions_px', 'rgba_sha256'):
                if key in asset:
                    require(asset[key] == info[key], f'{aid} spec has wrong {key}')
                asset[key] = info[key]
            asset['file'] = capture(asset_spec['file'], 'assets')
            source_spec = asset_spec.get('source')
            require(isinstance(source_spec, dict), f'{aid}.source is required')
            source_info = image_info(safe_file(root, source_spec.get('file'), f'{aid}.source.file'))
            for key in ('sha256', 'dimensions_px'):
                if key in source_spec:
                    require(source_spec[key] == source_info[key], f'{aid} spec has wrong source {key}')
                asset['source'][key] = source_info[key]
            asset['source']['file'] = capture(source_spec['file'], 'sources')
            for key in ('review_file', 'provenance_file'):
                asset[key] = capture(asset_spec.get(key), 'evidence')
            approval = asset.get('approval')
            if approval is not None:
                require(isinstance(approval, dict), 'approval must be an object')
                # Never auto-bind approval to unseen pixels: both hashes are explicit inputs.
                for key in ('evidence_file', 'delegation_file'):
                    if key in approval:
                        approval[key] = capture(approval[key], 'evidence')
            manifest['assets'].append(asset)
        # Original selected paths are preserved in original_project, not live dependencies.
        for key, role in (('selected_design', 'identity'), ('approved_master', 'native_master')):
            candidates = [a for a in manifest['assets'] if a['role'] == role and a['status'] == 'accepted']
            portable[key] = {'file': candidates[0]['file'], 'sha256': candidates[0]['sha256']} if len(candidates) == 1 else None
        for index, support in enumerate(supports):
            if 'directory' not in support:
                manifest['supports'].append({**support, 'file': capture(support['file'], 'evidence')})
                continue
            source, destination, (directories, files) = trees[index]
            require(not stage.resolve().is_relative_to(source.resolve()), 'Output cannot be inside a copied support tree')
            target = stage / destination
            require(not target.exists(), 'Conflicting support tree destination')
            target.mkdir(parents=True)
            for name in directories:
                (target / name).mkdir()
            for name in files:
                path = source / name
                require(not path.is_symlink() and path.is_file(), 'Support input changed while creating bundle')
                descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
                with os.fdopen(descriptor, 'rb') as stream:
                    require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'Support input is not a regular file')
                    data = stream.read(MAX_SUPPORT_FILE_BYTES + 1)
                require(len(data) <= MAX_SUPPORT_FILE_BYTES, 'Support file exceeds byte safety limit')
                with (target / name).open('xb') as stream:
                    stream.write(data)
                tree_hashes[path] = hashlib.sha256(data).hexdigest()
            manifest['supports'].append({**support, 'directory': destination, 'directories': directories})
        run_name = spec.get('run_directory')
        if run_name:
            require(isinstance(run_name, str), 'run_directory must be relative')
            # Resolve directories independently; forbid traversal even if it lands inside.
            require(not Path(run_name).is_absolute() and '..' not in Path(run_name).parts and '\\' not in run_name,
                    'run_directory must be a contained relative directory')
            source_run = (root / run_name).resolve(strict=True)
            require(source_run.is_relative_to(root) and source_run.is_dir(), 'run_directory escapes spec root')
            no_symlinks(root / run_name)
            require(not stage.is_relative_to(source_run) and not out.is_relative_to(source_run), 'Output cannot be inside the copied run')
            shutil.copytree(source_run, stage / 'run', copy_function=shutil.copy2)
            manifest['run_directory'] = 'run'
            portable['run_directory'] = 'run'
            manifest['continuation_mode'] = 'same_run'
            counters, attempts = run_budget(stage / 'run', project)
            write_json(stage / 'budget-evidence.json', {'attempts': attempts, 'derived_from': 'run/events.jsonl'})
            manifest['budget_evidence_file'] = 'budget-evidence.json'
        else:
            portable.pop('run_directory', None)
            evidence_path = safe_file(root, spec.get('budget_evidence_file'), 'budget_evidence_file')
            evidence = read_json(evidence_path)
            counters = budget_from_attempts(evidence.get('attempts'), project['budget'])
            manifest['budget_evidence_file'] = capture(spec['budget_evidence_file'], 'evidence')
            manifest['continuation_mode'] = 'evidence_only'
        if 'budget_state' in spec:
            require(spec['budget_state'] == counters, 'Spec budget_state conflicts with current evidence')
        manifest['budget_state'] = counters
        write_json(stage / 'project.json', portable)
        manifest['project'] = 'project.json'
        manifest['project_sha256'] = sha256(stage / 'project.json')
        required_ids = manifest.get('required_assets', [])
        by_id = {a['id']: a for a in manifest['assets']}
        manifest['handoff_ready'] = (manifest.get('status') == 'accepted' and bool(required_ids)
                                     and all(aid in by_id and by_id[aid]['status'] == 'accepted' for aid in required_ids)
                                     and not counters['pending_attempts'])
        manifest['inventory'] = [{'file': p.relative_to(stage).as_posix(), 'sha256': sha256(p), 'bytes': p.stat().st_size}
                                 for p in sorted(stage.rglob('*')) if p.is_file()]
        write_json(stage / 'bundle.json', manifest)
        report = check_bundle(stage)
        # Recheck inputs after construction so a changing source is never silently copied.
        for (name, original_hash), relative in copies.items():
            require(sha256(name) == original_hash, 'Input changed while creating bundle')
        for source, destination, snapshot in trees.values():
            require(scan_support_tree(source) == snapshot, 'Support input tree changed while creating bundle')
        for path, original_hash in tree_hashes.items():
            require(not path.is_symlink() and sha256(path) == original_hash, 'Support input changed while creating bundle')
        require(sha256(project['_meta']['profile_path']) == manifest['profile_sha256'], 'Profile changed while creating bundle')
        stage.rename(out)
        report['bundle'] = str(out)
        return report
    except BaseException:
        # Copied snapshots can be read-only; only this new temporary tree is removed.
        for path in stage.rglob('*'):
            if path.is_dir():
                path.chmod(0o755)
        stage.chmod(0o755)
        shutil.rmtree(stage)
        raise


def template():
    return {'schema_version': 1, 'project': 'project.json', 'stage': 'identity', 'status': 'study',
            'technical_status': 'unverified', 'visual_status': 'unverified',
            'next_step': 'Review the identity study at actual native preview size',
            'required_assets': ['identity-01'], 'budget_evidence_file': 'budget-evidence.json',
            'assets': [{'id': 'identity-01', 'file': 'identity.png', 'role': 'identity',
                        'status': 'study', 'technical_status': 'unverified', 'visual_status': 'unverified',
                        'source': {'file': 'identity.png', 'kind': 'generated'},
                        'review_file': 'review.json', 'provenance_file': 'provenance.json', 'approval': None}],
            'supports': [{'file': 'request.txt', 'role': 'request'}], 'timeline': []}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    make_template = commands.add_parser('template', help='Write an editable unaccepted study spec; no overwrite')
    make_template.add_argument('output')
    create = commands.add_parser('create', help='Copy self-contained evidence and verify a fresh bundle')
    create.add_argument('spec')
    create.add_argument('output')
    check = commands.add_parser('check', help='Verify all hashes, dimensions, roles, counters, and declared gates')
    check.add_argument('bundle')
    args = parser.parse_args(argv)
    try:
        if args.command == 'template':
            write_json(args.output, template())
            report = {'template': args.output, 'status': 'study', 'accepted': False}
        elif args.command == 'create':
            report = create_bundle(args.spec, args.output)
        else:
            report = check_bundle(args.bundle)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (BundleError, ProjectError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f'Bundle error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
