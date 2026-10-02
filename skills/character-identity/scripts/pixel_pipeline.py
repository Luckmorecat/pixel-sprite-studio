#!/usr/bin/env python3
"""Package unchanged native PNGs and audit pixel animations (Python stdlib + ImageMagick).

Python reads PNG/GIF metadata, writes indexed PNGs and analyzes decoded pixels;
ImageMagick performs PNG decoding and rendered previews. Exact indexed PNG intermediates
preserve GIF palette entries without quantization. This script does not create/edit
artwork. Repeated input drawings remain separate real timeline frames.

Manifest paths are relative to the manifest. Required: width, height, master
(PNG path), frames ([{file: PNG path, duration_ms: integer}]), tag (name).
Optional: animation_mode (local/full_body), motion_regions ([{x,y,width,height}],
half-open rectangles), motion_mask (opaque binary PNG; white selects), palette_max
(maximum union of visible colors across master and frames), min_margin (minimum
clear canvas-border pixels on all four sides). Missing regions mean unrestricted
motion in legacy manifests; explicit local requires a selector. [] permits no
changes. Full-body mode has no static pixel lock: geometry/reviewer evidence is
separate and does not prove identity. Binary alpha is always required. The project
option or a project path in the manifest/plan enforces shared configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

from motion_support import selection, full_body_qa

MAX_PIXELS = 16_777_216
MAX_FRAMES = 4096
MAX_TOTAL_PIXELS = 67_108_864
DELIVERABLES = ('master.png', 'sequence', 'spritesheet.png', 'contact-sheet.png',
                'contact-sheet-index.json', 'playback-native.gif', 'playback.gif',
                'playback.html', 'manifest.json', 'timing.json', 'qa.json')


class PipelineError(ValueError):
    """Invalid inputs, unsupported structure, or failed verification."""


def require(condition, message):
    if not condition:
        raise PipelineError(message)


def integer(value, label, lo, hi):
    require(type(value) is int and lo <= value <= hi,
            f'{label} must be an integer in {lo}..{hi}')
    return value


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def read_json(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f'Duplicate JSON key: {key!r}')
            result[key] = value
        return result
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f'Invalid JSON: {exc}') from exc


def exclusive_json(path, value, protected=()):
    path = Path(path).absolute()
    require(path.resolve() not in {Path(p).resolve() for p in protected},
            'Report destination would overwrite an input')
    try:
        with path.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write('\n')
    except FileExistsError as exc:
        raise PipelineError(f'Refusing to overwrite existing report: {path}') from exc


def imagemagick():
    tool = shutil.which('magick')
    if tool:
        return [tool]
    tool = shutil.which('convert')
    require(tool, 'ImageMagick is required: install magick (or legacy convert) from an official source')
    return [tool]


def run_im(args):
    command = imagemagick() + list(map(str, args))
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=False, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PipelineError(f'ImageMagick failed: {exc}') from exc
    require(result.returncode == 0,
            'ImageMagick failed: ' + result.stderr.decode('utf-8', 'replace')[:3000])
    return result.stdout


def png_info(path):
    """Read PNG container metadata, reject APNG/16-bit conversion and unsafe sizes."""
    data = Path(path).read_bytes()
    require(data[:8] == b'\x89PNG\r\n\x1a\n', f'Not a PNG: {path}')
    pos, ihdr, ended = 8, None, False
    while pos < len(data):
        require(pos + 12 <= len(data), f'Truncated PNG chunk: {path}')
        size = struct.unpack_from('>I', data, pos)[0]
        kind = data[pos + 4:pos + 8]
        end = pos + 12 + size
        require(end <= len(data), f'Truncated PNG payload: {path}')
        body = data[pos + 8:pos + 8 + size]
        crc = struct.unpack_from('>I', data, pos + 8 + size)[0]
        require(zlib.crc32(kind + body) & 0xffffffff == crc, f'PNG CRC mismatch: {path}')
        if pos == 8:
            require(kind == b'IHDR' and size == 13, f'Invalid PNG IHDR: {path}')
            ihdr = struct.unpack('>IIBBBBB', body)
        require(kind != b'acTL', f'Animated PNG is not a single drawing: {path}')
        if kind == b'IEND':
            require(size == 0 and end == len(data), f'Invalid PNG end/trailing data: {path}')
            ended = True
            break
        pos = end
    require(ihdr is not None and ended, f'Incomplete PNG: {path}')
    width, height, depth, color_type, compression, filtering, interlace = ihdr
    require(0 < width <= 65535 and 0 < height <= 65535 and width * height <= MAX_PIXELS,
            f'PNG dimensions exceed safe limits: {path}')
    require(depth in (1, 2, 4, 8), f'PNG must be at most 8 bits/channel; refusing lossy conversion: {path}')
    require(compression == 0 and filtering == 0 and interlace in (0, 1), f'Unsupported PNG encoding: {path}')
    return {'width': width, 'height': height, 'bit_depth': depth,
            'color_type': color_type, 'file_sha256': digest(data)}


def decode_png(path):
    info = png_info(path)
    raw = run_im(['PNG:' + str(Path(path).resolve()), '-alpha', 'on', '-depth', '8', 'RGBA:-'])
    require(len(raw) == info['width'] * info['height'] * 4,
            f'Decoded PNG byte count does not match dimensions: {path}')
    info['rgba_sha256'] = digest(raw)
    return info, raw


def resolve_project(path, manifest, project_path=None):
    reference = manifest.get('project')
    if reference is not None:
        require(isinstance(reference, str) and reference, 'project must name a project JSON file')
        reference = (Path(path).parent / reference).resolve(strict=True)
    if project_path is not None:
        project_path = Path(project_path).resolve(strict=True)
        require(reference is None or reference == project_path,
                '--project contradicts the manifest project reference')
    project_path = project_path or reference
    if project_path is not None:
        from project_config import enforce_manifest
        try:
            manifest = enforce_manifest(manifest, project_path)
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc
    return manifest, project_path


def load_manifest(path, manifest=None, project_path=None):
    path = Path(path).resolve(strict=True)
    if manifest is None:
        manifest = read_json(path)
    require(isinstance(manifest, dict), 'Manifest must be a JSON object')
    manifest, project_path = resolve_project(path, manifest, project_path)
    w = integer(manifest.get('width'), 'width', 1, 65535)
    h = integer(manifest.get('height'), 'height', 1, 65535)
    require(w * h <= MAX_PIXELS, 'Canvas exceeds safe pixel limit')
    frames = manifest.get('frames')
    require(isinstance(frames, list) and 1 <= len(frames) <= MAX_FRAMES,
            f'frames must contain 1..{MAX_FRAMES} entries')
    require(w * h * len(frames) <= MAX_TOTAL_PIXELS, 'Timeline exceeds safe decoded pixel limit')
    tag = manifest.get('tag')
    require(isinstance(tag, str) and tag.strip() and '\x00' not in tag
            and len(tag.encode('utf-8')) <= 65535, 'tag must be a nonempty UTF-8 name')

    def reference(value, label):
        require(isinstance(value, str) and value, f'{label} must name a PNG file')
        resolved = (path.parent / value).resolve(strict=True)
        require(resolved.is_file(), f'{label} is not a file: {resolved}')
        return resolved

    master = reference(manifest.get('master'), 'master')
    resolved_frames = []
    for i, frame in enumerate(frames):
        require(isinstance(frame, dict), f'frames[{i}] must be an object')
        resolved_frames.append({'path': reference(frame.get('file'), f'frames[{i}].file'),
                                'duration_ms': integer(frame.get('duration_ms'),
                                                       f'frames[{i}].duration_ms', 1, 65535)})
    regions = manifest.get('motion_regions')
    if regions is not None:
        require(isinstance(regions, list), 'motion_regions must be a list of rectangles')
        for i, rect in enumerate(regions):
            require(isinstance(rect, dict), f'motion_regions[{i}] must be an object')
            x = integer(rect.get('x'), f'motion_regions[{i}].x', 0, w - 1)
            y = integer(rect.get('y'), f'motion_regions[{i}].y', 0, h - 1)
            rw = integer(rect.get('width'), f'motion_regions[{i}].width', 1, w)
            rh = integer(rect.get('height'), f'motion_regions[{i}].height', 1, h)
            require(x + rw <= w and y + rh <= h, f'motion_regions[{i}] extends outside canvas')
    if 'palette_max' in manifest:
        integer(manifest['palette_max'], 'palette_max', 1, MAX_PIXELS)
    if 'min_margin' in manifest:
        integer(manifest['min_margin'], 'min_margin', 0, min(w, h) // 2)
    mode = manifest.get('animation_mode', 'legacy')
    require('animation_mode' not in manifest or mode in ('local', 'full_body'), 'animation_mode must be local or full_body')
    require(manifest.get('binary_alpha', True) is True, 'Binary alpha is required')
    try:
        active, mask_record = selection(manifest, w, h, path.parent, decode_png)
    except ValueError as exc:
        raise PipelineError(str(exc)) from exc
    if mode == 'local':
        require(active is not None, 'animation_mode local requires motion_regions or motion_mask')
        require(len(active) < w * h, 'Local motion may not select the full canvas')
    constraints = manifest.get('constraints', {})
    require(isinstance(constraints, dict), 'constraints must be an object')
    allowed = {'timeline_frame_count': MAX_FRAMES, 'distinct_drawing_count': MAX_FRAMES,
               'min_distinct_drawing_count': MAX_FRAMES, 'max_distinct_drawing_count': MAX_FRAMES,
               'max_timeline_frame_count': MAX_FRAMES, 'total_duration_ms': MAX_FRAMES * 65535}
    require(not set(constraints) - set(allowed), 'Unknown constraints: ' + ', '.join(sorted(set(constraints) - set(allowed))))
    for key, value in constraints.items():
        integer(value, f'constraints.{key}', 1, allowed[key])
    return {'path': path, 'manifest': manifest, 'width': w, 'height': h,
            'master': master, 'frames': resolved_frames, 'regions': regions,
            'selection': active, 'mask_record': mask_record, 'animation_mode': mode,
            'project_path': project_path}


def load_pose_plan(path, project_path=None):
    """Compile semantic pose references; never generate, align or alter artwork."""
    path = Path(path).resolve(strict=True)
    plan = read_json(path)
    require(isinstance(plan, dict) and type(plan.get('schema_version')) is int
            and plan['schema_version'] == 1, 'Pose plan requires schema_version: 1')
    poses, timeline = plan.get('poses'), plan.get('timeline')
    require(isinstance(poses, dict) and poses, 'poses must map semantic IDs to file/status objects')
    require(isinstance(timeline, list) and 1 <= len(timeline) <= MAX_FRAMES,
            f'timeline must contain 1..{MAX_FRAMES} entries')
    for pose_id, pose in poses.items():
        require(isinstance(pose_id, str) and pose_id.strip(), 'Pose IDs must be nonempty strings')
        require(isinstance(pose, dict), f'Pose {pose_id!r} must be an object')
        require(pose.get('status') in ('accepted', 'approved', 'generated'),
                f'Pose {pose_id!r} requires status accepted, approved, or generated; study/needs_revision cannot execute (legacy states are declarations, not visual approval)')
        file = pose.get('file')
        require(isinstance(file, str) and file, f'Pose {pose_id!r} is missing its native PNG file')
        require((path.parent / file).is_file(),
                f'Pose {pose_id!r} native file is missing: {file}; generate or supply it before assembly')
        if pose.get('status') == 'accepted':
            current_hash = digest((path.parent / file).read_bytes())
            review = pose.get('quality_review', {})
            require(isinstance(review, dict) and review.get('status') == 'accepted'
                    and isinstance(review.get('notes'), str) and review['notes'].strip()
                    and review.get('artifact_sha256') == current_hash,
                    f'Accepted pose {pose_id!r} needs a hash-bound accepted quality_review with notes')

    def pose_reference(pose_id, label):
        require(isinstance(pose_id, str) and pose_id in poses,
                f'{label} references missing pose ID {pose_id!r}; available IDs: {", ".join(poses)}')
        return poses[pose_id]['file']

    compiled = {key: plan[key] for key in ('width', 'height', 'tag', 'motion_regions', 'motion_mask', 'motion_mask_sha256', 'mask_semantics',
                                          'palette_max', 'binary_alpha', 'min_margin', 'constraints', 'project',
                                          'animation_mode', 'geometry_constraints', 'full_body_reviews', 'scope', 'anchor_px') if key in plan}
    compiled['master'] = pose_reference(plan.get('master_pose'), 'master_pose')
    required_phases = plan.get('required_phases', [])
    require(isinstance(required_phases, list) and all(isinstance(p, str) and p.strip() for p in required_phases)
            and len(set(required_phases)) == len(required_phases), 'required_phases must list distinct nonempty phase names')
    phases = [f.get('phase') for f in timeline if isinstance(f, dict)]
    require(all(p in phases for p in required_phases), 'Timeline is missing required semantic phases: '
            + ', '.join(p for p in required_phases if p not in phases))
    compiled['frames'] = []
    for i, frame in enumerate(timeline):
        require(isinstance(frame, dict), f'timeline[{i}] must be an object')
        require('phase' not in frame or isinstance(frame['phase'], str) and frame['phase'].strip(),
                f'timeline[{i}].phase must be a nonempty phase name')
        compiled['frames'].append({'file': pose_reference(frame.get('pose_id'), f'timeline[{i}]'),
                                   'pose_id': frame['pose_id'], 'duration_ms': frame.get('duration_ms'),
                                   **({'phase': frame['phase']} if 'phase' in frame else {})})
    loaded = load_manifest(path, compiled, project_path=project_path)
    loaded['pose_plan'] = plan
    return loaded


def bbox(indices, width):
    if not indices:
        return None
    xs = [i % width for i in indices]
    ys = [i // width for i in indices]
    return {'x': min(xs), 'y': min(ys), 'width': max(xs) - min(xs) + 1,
            'height': max(ys) - min(ys) + 1}


def pixel_stats(raw, width):
    pixels = [raw[i:i + 4] for i in range(0, len(raw), 4)]
    alpha = sorted({pixel[3] for pixel in pixels})
    visible = {pixel for pixel in pixels if pixel[3]}
    occupied = bbox([i for i, pixel in enumerate(pixels) if pixel[3]], width)
    height = len(pixels) // width
    margins = None if occupied is None else {
        'left': occupied['x'], 'top': occupied['y'],
        'right': width - occupied['x'] - occupied['width'],
        'bottom': height - occupied['y'] - occupied['height']}
    touches = [side for side, value in (margins or {}).items() if value == 0]
    return {'rgba_sha256': digest(raw), 'binary_alpha': all(a in (0, 255) for a in alpha),
            'alpha_values': alpha, 'palette_count_visible': len(visible),
            'palette_count_rgba_including_hidden': len(set(pixels)),
            'opaque_pixels': sum(pixel[3] == 255 for pixel in pixels),
            'nontransparent_bbox': occupied, 'clear_margins': margins,
            'canvas_edge_contacts': touches,
            'clipping_assessment': 'Edge contact needs visual review; pixel bounds cannot prove clipping'
                if touches else 'No canvas-edge contact; internal occlusion still needs visual review'}, visible


def delta(before, after, width, regions, selection=None):
    changed, visual, outside = [], 0, []
    for index, offset in enumerate(range(0, len(before), 4)):
        a, b = before[offset:offset + 4], after[offset:offset + 4]
        if a != b:
            changed.append(index)
            visual += bool(a[3] or b[3])
            if selection is not None:
                if index not in selection:
                    outside.append(index)
            elif regions is not None:
                x, y = index % width, index // width
                if not any(r['x'] <= x < r['x'] + r['width'] and
                           r['y'] <= y < r['y'] + r['height'] for r in regions):
                    outside.append(index)
    return {'changed_pixels': len(changed), 'visually_changed_pixels': visual,
            'changed_bbox': bbox(changed, width),
            'outside_motion_regions': len(outside) if regions is not None or selection is not None else None,
            'outside_motion_bbox': bbox(outside, width) if regions is not None or selection is not None else None}


def audit(loaded):
    errors, warnings, cache = [], [], {}
    union = set()
    expected = (loaded['width'], loaded['height'])
    all_paths = [loaded['master']] + [f['path'] for f in loaded['frames']]
    for path in dict.fromkeys(all_paths):
        info, raw = decode_png(path)
        require((info['width'], info['height']) == expected,
                f'Native size mismatch: {path}: {info["width"]}x{info["height"]}, expected {expected[0]}x{expected[1]}')
        stats, colors = pixel_stats(raw, expected[0])
        union.update(colors)
        info.update(stats)
        cache[path] = (info, raw)
        if not stats['binary_alpha']:
            errors.append(f'Non-binary alpha in {path.name}: {stats["alpha_values"]}')
        if stats['canvas_edge_contacts']:
            warnings.append(f'{path.name} touches canvas edges {stats["canvas_edge_contacts"]}; inspect visually for clipping')
        requested_margin = loaded['manifest'].get('min_margin')
        if (requested_margin is not None and stats['clear_margins'] is not None
                and min(stats['clear_margins'].values()) < requested_margin):
            errors.append(f'{path.name} clear margins {stats["clear_margins"]} violate min_margin {requested_margin}')
    master_info, master_raw = cache[loaded['master']]
    frames, adjacent = [], []
    full_body = loaded['animation_mode'] == 'full_body'
    regions = None if full_body else loaded['regions']
    active = None if full_body else loaded['selection']
    if full_body and (loaded['regions'] is not None or loaded['mask_record'] is not None):
        warnings.append('Local selectors are not enforced in full_body mode; whole-body artwork changes are allowed')
    hashes = []
    for i, f in enumerate(loaded['frames']):
        info, raw = cache[f['path']]
        hashes.append(visual_hash(raw))
        d = delta(master_raw, raw, expected[0], regions, active)
        frames.append(dict(info, frame=i, file=str(f['path']), duration_ms=f['duration_ms'],
                           delta_from_master=d))
        if d['outside_motion_regions']:
            errors.append(f'Frame {i} changes {d["outside_motion_regions"]} pixels outside motion_regions/motion_mask relative to master')
        if i:
            d = delta(cache[loaded['frames'][i - 1]['path']][1], raw, expected[0], regions, active)
            adjacent.append(dict(d, from_frame=i - 1, to_frame=i))
    loop = delta(cache[loaded['frames'][-1]['path']][1], cache[loaded['frames'][0]['path']][1],
                 expected[0], regions, active)
    max_palette = loaded['manifest'].get('palette_max')
    if max_palette is not None and len(union) > max_palette:
        errors.append(f'Visible palette union {len(union)} exceeds palette_max {max_palette}')
    if len(set(hashes)) == 1 and len(hashes) > 1:
        warnings.append('All timeline frames have identical visible decoded pixels; this is a timed hold, not distinct animation drawings')
    durations = [f['duration_ms'] for f in loaded['frames']]
    actual = {'timeline_frame_count': len(frames), 'distinct_drawing_count': len(set(hashes)),
              'min_distinct_drawing_count': len(set(hashes)), 'max_distinct_drawing_count': len(set(hashes)),
              'max_timeline_frame_count': len(frames), 'total_duration_ms': sum(durations)}
    constraints = loaded['manifest'].get('constraints', {})
    for key, expected_value in constraints.items():
        meets = (actual[key] >= expected_value if key.startswith('min_') else
                 actual[key] <= expected_value if key.startswith('max_') else actual[key] == expected_value)
        if not meets:
            errors.append(f'Constraint {key}={expected_value} failed; measured {actual[key]}')
    gif_durations = [max(1, (d + 5) // 10) * 10 for d in durations]
    if durations != gif_durations:
        warnings.append('GIF stores centiseconds: preview durations are rounded to nearest 10 ms with a 10 ms minimum; timing.json and the PNG viewer preserve the requested schedule')
    if any(f['palette_count_visible'] + (0 in f['alpha_values']) > 256 for f in frames):
        warnings.append('A frame exceeds GIF\'s 256 palette entries (255 visible colors with transparency); lossless GIF export will be rejected')
    full_body_report = None
    if full_body:
        try:
            full_body_report, body_errors = full_body_qa(loaded['manifest'], master_info, master_raw,
                [cache[f['path']] for f in loaded['frames']], expected[0], expected[1])
            errors.extend(body_errors)
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc
    report = {'schema_version': 1, 'passed': not errors, 'errors': errors, 'warnings': warnings,
              'width': expected[0], 'height': expected[1], 'timeline_frame_count': len(frames),
              'distinct_drawing_count': len(set(hashes)), 'palette_count_visible_union': len(union),
              'palette_max': max_palette, 'motion_regions': loaded['regions'],
              'motion_mask': loaded['mask_record'], 'animation_mode': loaded['animation_mode'],
              'full_body_qa': full_body_report,
              'project_provenance': loaded['manifest'].get('project_provenance'),
              'min_margin': loaded['manifest'].get('min_margin'),
              'constraints': constraints, 'visual_status': 'unreviewed',
              'action_readability': 'unreviewed; pixel differences alone cannot verify the requested action',
              'master': dict(master_info, file=str(loaded['master'])), 'frames': frames,
              'adjacent_deltas': adjacent,
              'loop_delta': dict(loop, from_frame=len(frames) - 1, to_frame=0),
              'timing': {'requested_duration_ms': durations, 'gif_duration_ms': gif_durations,
                         'requested_total_ms': sum(durations), 'gif_total_ms': sum(gif_durations)},
              'verification': {'visual_art_quality': 'Requires human visual review; no hand-tuned or aesthetic quality claim',
                               'pixel_comparisons': 'Exact RGBA bytes, including RGB hidden under zero alpha'}}
    return report, cache


class GifReader:
    """Bounded byte reader for GIF frame metadata."""

    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, size):
        require(size >= 0 and self.pos + size <= len(self.data), 'Truncated GIF structure')
        value = self.data[self.pos:self.pos + size]
        self.pos += size
        return value

    def unpack(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))

    def done(self):
        require(self.pos == len(self.data), 'Unexpected trailing GIF payload')


def gif_info(path):
    """Read GIF frame delays/size without pretending GIF is a lossless source."""
    r = GifReader(Path(path).read_bytes())
    require(r.take(6) in (b'GIF87a', b'GIF89a'), 'Invalid GIF signature')
    w, h, packed, _, _ = r.unpack('<HHBBB')
    if packed & 0x80:
        r.take(3 * (1 << ((packed & 7) + 1)))
    delays, pending, sizes = [], 0, []

    def subblocks():
        while True:
            n = r.take(1)[0]
            if not n:
                return
            r.take(n)

    while True:
        marker = r.take(1)[0]
        if marker == 0x3b:
            r.done()
            break
        if marker == 0x21:
            label = r.take(1)[0]
            if label == 0xf9:
                require(r.take(1) == b'\x04', 'Invalid GIF control extension')
                _, pending, _ = r.unpack('<BHB')
                require(r.take(1) == b'\x00', 'Invalid GIF extension terminator')
            else:
                subblocks()
        elif marker == 0x2c:
            x, y, fw, fh, packed = r.unpack('<HHHHB')
            sizes.append({'x': x, 'y': y, 'width': fw, 'height': fh})
            if packed & 0x80:
                r.take(3 * (1 << ((packed & 7) + 1)))
            r.take(1)
            subblocks()
            delays.append(pending * 10)
            pending = 0
        else:
            raise PipelineError(f'Invalid GIF block 0x{marker:02x}')
    return {'width': w, 'height': h, 'frame_count': len(delays), 'duration_ms': delays,
            'frame_rectangles': sizes}


def visual_hash(raw):
    """Ignore RGB only where alpha is zero; GIF cannot preserve invisible RGB."""
    canonical = bytearray(raw)
    for offset in range(0, len(canonical), 4):
        if canonical[offset + 3] == 0:
            canonical[offset:offset + 3] = b'\0\0\0'
    return digest(canonical)


def visual_runs(hashes, durations):
    runs = []
    for sha, duration in zip(hashes, durations):
        if runs and runs[-1]['visual_sha256'] == sha:
            runs[-1]['duration_ms'] += duration
        else:
            runs.append({'visual_sha256': sha, 'duration_ms': duration})
    return runs


def verify_gif(path, loaded, cache, factor=1):
    """Decode disposal/composition and compare visual runs, accepting coalesced holds."""
    info = gif_info(path)
    w, h = loaded['width'] * factor, loaded['height'] * factor
    require((info['width'], info['height']) == (w, h), 'GIF dimensions failed verification')
    require(0 < info['frame_count'] <= MAX_FRAMES, 'GIF frame count exceeds safe limits')
    require(w * h * info['frame_count'] <= MAX_TOTAL_PIXELS, 'Decoded GIF exceeds safe pixel limit')
    decoded = run_im(['GIF:' + str(Path(path).resolve()), '-coalesce', '-alpha', 'on',
                      '-depth', '8', 'RGBA:-'])
    frame_bytes = w * h * 4
    require(len(decoded) == frame_bytes * info['frame_count'], 'Decoded GIF byte count failed verification')
    observed_hashes = [visual_hash(decoded[i:i + frame_bytes])
                       for i in range(0, len(decoded), frame_bytes)]
    expected_hashes, enlarged = [], {}
    for frame in loaded['frames']:
        source = frame['path']
        if source not in enlarged:
            raw = cache[source][1]
            if factor != 1:
                # Analyze exact nearest-neighbor replication, not an image-editing operation.
                row_bytes = loaded['width'] * 4
                rows = []
                for y in range(loaded['height']):
                    row = raw[y * row_bytes:(y + 1) * row_bytes]
                    rows.append(b''.join(row[i:i + 4] * factor for i in range(0, len(row), 4)) * factor)
                raw = b''.join(rows)
            enlarged[source] = visual_hash(raw)
        expected_hashes.append(enlarged[source])
    requested = [frame['duration_ms'] for frame in loaded['frames']]
    quantized = [max(1, (duration + 5) // 10) * 10 for duration in requested]
    expected_runs = visual_runs(expected_hashes, requested)
    rounded_runs = visual_runs(expected_hashes, quantized)
    observed_runs = visual_runs(observed_hashes, info['duration_ms'])
    visuals_match = [r['visual_sha256'] for r in expected_runs] == [r['visual_sha256'] for r in observed_runs]
    durations_match = [r['duration_ms'] for r in expected_runs] == [r['duration_ms'] for r in observed_runs]
    rounded_match = [r['duration_ms'] for r in rounded_runs] == [r['duration_ms'] for r in observed_runs]
    info.update({'decoded_visual_pixels_match': visuals_match,
                 'encoded_timing_matches_requested': durations_match,
                 'encoded_timing_matches_quantized': rounded_match,
                 'passed': visuals_match and durations_match,
                 'requested_runs': expected_runs, 'decoded_runs': observed_runs,
                 'comparison': 'Coalesced identical consecutive visual holds; transparent RGB ignored; all visible RGBA exact',
                 'viewer_timing_verified': False,
                 'limitations': 'GIF delays have 10 ms resolution. Browsers may clamp short delays; this verifies encoded timing, not observed playback timing.'})
    return info


def render_html(directory, manifest, scale):
    data = json.dumps({'width': manifest['width'], 'height': manifest['height'],
                       'scale': scale, 'frames': manifest['frames']}).replace('<', '\\u003c')
    template = '''<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Native PNG animation playback</title>
<style>
body{font:16px system-ui;margin:24px;color:#eee;background:#222}button{font:inherit;margin-right:8px}
.views{display:flex;align-items:flex-start;gap:32px;flex-wrap:wrap}img{image-rendering:pixelated}
.checker{background:repeating-conic-gradient(#aaa 0% 25%,#ddd 0% 50%) 0/16px 16px}
#contact{display:flex;flex-wrap:wrap;gap:16px}figure{margin:0}figcaption{font:13px monospace;margin:8px 0}
#status{font:16px monospace}p{max-width:900px}
</style>
<h1>Native PNG animation playback</h1>
<p>Original PNG sequence, nearest-neighbor display. The exact millisecond schedule is in timing.json.
Browser rendering is refresh-rate limited; this viewer does not certify aesthetic quality or measured wall-clock timing.</p>
<p><button id="play">Pause</button><button id="restart">Restart</button><button id="next">Next frame</button></p>
<p id="status">Loading all PNG frames…</p>
<div class="views"><figure><img class="checker" id="native" alt="Native-size current frame"><figcaption>Native size</figcaption></figure>
<figure><img class="checker" id="large" alt="Nearest-neighbor enlarged current frame"><figcaption>Nearest-neighbor enlarged</figcaption></figure></div>
<h2>Indexed timeline</h2><div id="contact"></div>
<script type="application/json" id="timeline">__DATA__</script>
<script>
const data=JSON.parse(document.getElementById('timeline').textContent);
const native=document.getElementById('native'),large=document.getElementById('large'),status=document.getElementById('status');
native.width=data.width;native.height=data.height;large.width=data.width*data.scale;large.height=data.height*data.scale;
let starts=[],total=0;data.frames.forEach(f=>{starts.push(total);total+=f.duration_ms});
let images=[],running=true,origin=0,elapsed=0,current=-1,ready=false;
function show(i){if(current!==i){native.src=images[i].src;large.src=images[i].src;current=i}
status.textContent=`Frame ${i+1}/${images.length} | loop elapsed ${Math.floor(elapsed%total)} / ${total} ms | frame hold ${data.frames[i].duration_ms} ms | ${running?'playing':'paused'}`}
function locate(t){let i=0;while(i+1<starts.length&&starts[i+1]<=t)i++;return i}
function tick(now){if(ready){if(running)elapsed=now-origin;show(locate(elapsed%total))}requestAnimationFrame(tick)}
document.getElementById('play').onclick=()=>{if(!ready)return;if(running)elapsed=performance.now()-origin;else origin=performance.now()-elapsed;
running=!running;document.getElementById('play').textContent=running?'Pause':'Play'};
document.getElementById('restart').onclick=()=>{elapsed=0;origin=performance.now();if(ready)show(0)};
document.getElementById('next').onclick=()=>{if(!ready)return;running=false;document.getElementById('play').textContent='Play';
elapsed=starts[(current+1)%images.length];show((current+1)%images.length)};
Promise.all(data.frames.map((f,i)=>new Promise((resolve,reject)=>{const img=new Image;img.onload=()=>resolve(img);img.onerror=()=>reject(new Error(`Missing PNG: ${f.file}`));img.src=f.file;
const fig=document.createElement('figure'),preview=document.createElement('img'),caption=document.createElement('figcaption');
preview.src=f.file;preview.width=data.width*2;preview.height=data.height*2;preview.className='checker';
caption.textContent=`${i+1} / index ${i} · ${f.duration_ms} ms${f.pose_id?' · '+f.pose_id:''}`;
fig.append(preview,caption);document.getElementById('contact').append(fig)})))
.then(result=>{images=result;ready=true;origin=performance.now();show(0)})
.catch(error=>{status.textContent='Playback failed: '+error.message});requestAnimationFrame(tick);
</script>
'''
    (directory / 'playback.html').write_text(template.replace('__DATA__', data), encoding='utf-8')


def write_gif_indexed_png(path, raw, width, height):
    """Encode existing RGBA as exact indices, never choose/merge/quantize colors.

    ImageMagick's implicit truecolor-to-GIF conversion can merge nearby RGB
    entries even below 256 colors. Supplying an already indexed PNG avoids that
    conversion. Each frame may have its own palette; invisible RGB is the only
    discarded information, consistently with the independent GIF verifier.
    """
    require(len(raw) == width * height * 4, 'Indexed PNG dimensions do not match RGBA bytes')
    colors, transparent = set(), False
    for offset in range(0, len(raw), 4):
        alpha = raw[offset + 3]
        require(alpha in (0, 255), 'GIF requires binary alpha; refusing lossy conversion')
        if alpha:
            colors.add(raw[offset:offset + 3])
        else:
            transparent = True
        require(len(colors) + transparent <= 256,
                'GIF palette capacity exceeded: at most 256 opaque colors, or 255 visible '
                'colors plus transparency, per frame; refusing lossy color quantization')
    # Transparent black and visible black must be distinct entries when both exist.
    ordered = sorted(colors)
    palette = ([b'\0\0\0'] if transparent else []) + ordered
    lookup = {color: index + transparent for index, color in enumerate(ordered)}
    indices = bytes(lookup[raw[o:o + 3]] if raw[o + 3] else 0 for o in range(0, len(raw), 4))
    scanlines = b''.join(b'\0' + indices[y * width:(y + 1) * width] for y in range(height))

    def png_chunk(kind, body):
        return (struct.pack('>I', len(body)) + kind + body
                + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff))

    png = (b'\x89PNG\r\n\x1a\n'
           + png_chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 3, 0, 0, 0))
           + png_chunk(b'PLTE', b''.join(palette))
           + (png_chunk(b'tRNS', b'\0') if transparent else b'')
           + png_chunk(b'IDAT', zlib.compress(scanlines)) + png_chunk(b'IEND', b''))
    Path(path).write_bytes(png)


def render_previews(directory, manifest, scale, columns):
    files = [directory / f['file'] for f in manifest['frames']]
    inputs = ['PNG:' + str(p) for p in files]
    run_im(inputs + ['+append', '-define', 'png:color-type=6', str(directory / 'spritesheet.png')])
    rows = []
    for start in range(0, len(inputs), columns):
        rows += ['('] + inputs[start:start + columns] + ['+append', ')']
    # Contact sheet: row-major timeline, transparent unused last-row cells; nearest-neighbor only.
    run_im(rows + ['-background', 'none', '-gravity', 'NorthWest', '-append',
                   '-filter', 'point', '-resize', str(scale * 100) + '%',
                   '-define', 'png:color-type=6', str(directory / 'contact-sheet.png')])
    index = {'indexing': 'Frame index is zero-based; display frame number is one-based',
             'sheet': 'contact-sheet.png', 'scale': scale, 'columns': columns, 'frames': []}
    for i, frame in enumerate(manifest['frames']):
        index['frames'].append({'frame': i, 'display_frame_number': i + 1,
                                'duration_ms': frame['duration_ms'], 'file': frame['file'],
                                'row': i // columns, 'column': i % columns,
                                'image_bounds': {'x': i % columns * manifest['width'] * scale,
                                                 'y': i // columns * manifest['height'] * scale,
                                                 'width': manifest['width'] * scale,
                                                 'height': manifest['height'] * scale}})
    write_json(directory / 'contact-sheet-index.json', index)
    require(manifest['width'] * scale <= 65535 and manifest['height'] * scale <= 65535,
            'Scaled GIF dimensions exceed the format limit of 65535 pixels')
    with tempfile.TemporaryDirectory(prefix='.gif-palettes-', dir=directory) as temporary:
        indexed = []
        for i, source in enumerate(files):
            info, raw = decode_png(source)
            exact = Path(temporary) / f'frame-{i:04d}.png'
            write_gif_indexed_png(exact, raw, info['width'], info['height'])
            indexed.append('PNG:' + str(exact))
        for filename, factor in [('playback-native.gif', 1), ('playback.gif', scale)]:
            gif = []
            for source, frame in zip(indexed, manifest['frames']):
                delay = max(1, (frame['duration_ms'] + 5) // 10)
                gif += ['(', '-delay', str(delay), '-dispose', 'background', source,
                        '-sample', str(factor * 100) + '%', ')']
            run_im(gif + ['-loop', '0', str(directory / filename)])


def pack(manifest_path, output, scale=6, columns=4, gif_fidelity='strict', pose_plan=False, project_path=None):
    integer(scale, 'scale', 1, 32)
    integer(columns, 'columns', 1, 256)
    require(gif_fidelity in ('strict', 'report'), 'gif_fidelity must be strict or report')
    loaded = (load_pose_plan(manifest_path, project_path=project_path) if pose_plan
              else load_manifest(manifest_path, project_path=project_path))
    report, cache = audit(loaded)
    require(report['passed'], 'Input QA failed: ' + '; '.join(report['errors']))
    output = Path(output).absolute()
    require(not output.exists() and not output.is_symlink(),
            f'Output must be a fresh, nonexistent directory: {output}')
    require(output.parent.is_dir(), 'Output parent directory must already exist')
    sources = [loaded['path'], loaded['master']] + [f['path'] for f in loaded['frames']]
    require(all(output.resolve() != p and output.resolve() not in p.parents for p in sources),
            'Output destination would overwrite source paths')
    require(loaded['width'] * loaded['height'] * len(loaded['frames']) * scale * scale
            <= MAX_TOTAL_PIXELS, 'Scaled previews exceed safe pixel budget; reduce --scale')
    with tempfile.TemporaryDirectory(prefix='.pixel-pack-', dir=output.parent) as temporary:
        stage = Path(temporary)
        (stage / 'sequence').mkdir()
        portable = {key: loaded['manifest'][key] for key in
                    ('width', 'height', 'tag', 'motion_regions', 'mask_semantics', 'animation_mode',
                     'geometry_constraints', 'full_body_reviews', 'scope', 'anchor_px', 'motion_mask_sha256', 'palette_max', 'binary_alpha', 'min_margin',
                     'constraints', 'project_provenance')
                    if key in loaded['manifest']}

        def copy_native(source, relative):
            shutil.copyfile(source, stage / relative)
            require(digest((stage / relative).read_bytes()) == cache[source][0]['file_sha256'],
                    f'Source changed during packaging: {source}')
            # Read-only export plus hashes; not a claim of filesystem-level tamper resistance.
            (stage / relative).chmod(0o444)

        if loaded['mask_record']:
            mask = loaded['mask_record']
            mask_source = Path(mask['file'])
            require(digest(mask_source.read_bytes()) == mask['file_sha256'], 'motion_mask changed during packaging')
            shutil.copyfile(mask_source, stage / 'motion-mask.png')
            require(digest((stage / 'motion-mask.png').read_bytes()) == mask['file_sha256'], 'motion_mask changed while copying')
            portable['motion_mask'] = 'motion-mask.png'
        copy_native(loaded['master'], 'master.png')
        portable['master'] = 'master.png'
        portable['frames'] = []
        for i, frame in enumerate(loaded['frames']):
            relative = f'sequence/frame-{i:04d}.png'
            copy_native(frame['path'], relative)
            exported = {'file': relative, 'duration_ms': frame['duration_ms']}
            pose_id = loaded['manifest']['frames'][i].get('pose_id')
            if pose_id is not None:
                exported['pose_id'] = pose_id
            if 'phase' in loaded['manifest']['frames'][i]:
                exported['phase'] = loaded['manifest']['frames'][i]['phase']
            portable['frames'].append(exported)
        portable['provenance'] = {'source_manifest_sha256': digest(loaded['path'].read_bytes()),
                                  'artwork_handling': 'Original PNG files copied byte-for-byte, read-only; no visual pixel edits',
                                  'alignment': 'Identity native canvas; no crop, translation, rescaling or recentering'}
        if pose_plan:
            shutil.copyfile(loaded['path'], stage / 'pose-plan.json')
            portable['provenance']['pose_plan'] = 'pose-plan.json'
        write_json(stage / 'manifest.json', portable)
        start = 0
        timing_frames = []
        for i, frame in enumerate(portable['frames']):
            timing_frames.append(dict(frame, frame=i, start_ms=start, end_ms=start + frame['duration_ms']))
            start += frame['duration_ms']
        write_json(stage / 'timing.json', {'schema_version': 1, 'unit': 'milliseconds',
                                          'loop': True, 'total_duration_ms': start,
                                          'timeline_frame_count': len(timing_frames), 'frames': timing_frames})
        render_previews(stage, portable, scale, columns)
        render_html(stage, portable, scale)
        gif = verify_gif(stage / 'playback.gif', loaded, cache, scale)
        native_gif = verify_gif(stage / 'playback-native.gif', loaded, cache)
        fidelity_ok = gif['passed'] and native_gif['passed']
        require(gif_fidelity != 'strict' or fidelity_ok,
                'GIF fidelity failed: visible pixels or exact timing differ from PNG timeline. '
                'Use 10 ms timing and GIF-compatible colors, or --gif-fidelity report to export with explicit fidelity failure.')
        if not fidelity_ok:
            report['warnings'].append('GIF fidelity verification failed; inspect exports.gif/native_gif. PNG sequence and timing.json remain authoritative. This is not a lossless GIF pass.')
        sheet, sheet_raw = decode_png(stage / 'spritesheet.png')
        require((sheet['width'], sheet['height']) == (loaded['width'] * len(loaded['frames']), loaded['height']),
                'Spritesheet dimensions failed verification')
        row_size = loaded['width'] * 4
        sheet_row_size = row_size * len(loaded['frames'])
        for i, f in enumerate(loaded['frames']):
            raw = cache[f['path']][1]
            require(all(sheet_raw[y * sheet_row_size + i * row_size:y * sheet_row_size + (i + 1) * row_size]
                        == raw[y * row_size:(y + 1) * row_size] for y in range(loaded['height'])),
                    f'Spritesheet pixel mismatch at frame {i}')
        contact, _ = decode_png(stage / 'contact-sheet.png')
        require((contact['width'], contact['height']) ==
                (loaded['width'] * min(columns, len(loaded['frames'])) * scale,
                 loaded['height'] * math.ceil(len(loaded['frames']) / columns) * scale),
                'Contact sheet dimensions failed verification')
        report['exports'] = {'spritesheet': sheet, 'contact_sheet': contact, 'gif': gif,
                             'native_gif': native_gif, 'contact_sheet_labels': 'contact-sheet-index.json',
                             'preview_scale': scale, 'contact_columns': columns,
                             'spritesheet_decoded_inputs_match': True,
                             'gif_fidelity_policy': gif_fidelity, 'gif_fidelity_passed': fidelity_ok,
                             'html_viewer': 'playback.html', 'html_viewer_playback_observed': False}
        report['master']['file'] = portable['master']
        for frame, portable_frame in zip(report['frames'], portable['frames']):
            frame['file'] = portable_frame['file']
        report['passed'] = report['passed'] and fidelity_ok
        report['package_created'] = True
        report['file_hashes'] = {str(path.relative_to(stage)): digest(path.read_bytes())
                                for path in sorted(stage.rglob('*')) if path.is_file()}
        write_json(stage / 'qa.json', report)
        output.mkdir()
        try:
            for child in stage.iterdir():
                shutil.move(str(child), output / child.name)
        except Exception:
            shutil.rmtree(output)
            raise
    return {'passed': report['passed'], 'package_created': True, 'output': str(output),
            'timeline_frame_count': len(loaded['frames']), 'distinct_drawing_count': report['distinct_drawing_count'],
            'deliverables': list(DELIVERABLES) + (['pose-plan.json'] if pose_plan else [])
                            + (['motion-mask.png'] if loaded['mask_record'] else []),
            'warnings': report['warnings'], 'gif_fidelity_passed': fidelity_ok,
            'visual_status': 'unreviewed'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    for name, help_text in [('pack', 'Package native PNGs into a new directory'),
                            ('plan', 'Resolve semantic native poses and package their timeline')]:
        packing = sub.add_parser(name, help=help_text)
        packing.add_argument('manifest')
        packing.add_argument('output_dir')
        packing.add_argument('--project', help='Shared project JSON; contradictions are rejected')
        packing.add_argument('--scale', type=int, default=6)
        packing.add_argument('--columns', type=int, default=4)
        packing.add_argument('--gif-fidelity', choices=('strict', 'report'), default='strict',
                             help='strict rejects lossy pixels/timing; report exports them with passed=false (exit 2)')
    qa_parser = sub.add_parser('qa', help='Check input manifest and decoded PNG pixels')
    qa_parser.add_argument('manifest')
    qa_parser.add_argument('--project', help='Shared project JSON; checks animation limits too')
    qa_parser.add_argument('--output', help='Write report to a new JSON file; never overwrite')
    args = parser.parse_args(argv)
    try:
        protected = []
        if args.command in ('pack', 'plan'):
            result = pack(args.manifest, args.output_dir, scale=args.scale, columns=args.columns,
                          gif_fidelity=args.gif_fidelity, pose_plan=args.command == 'plan', project_path=args.project)
        elif args.command == 'qa':
            loaded = load_manifest(args.manifest, project_path=args.project)
            result, _ = audit(loaded)
            protected = [loaded['path'], loaded['master']] + [f['path'] for f in loaded['frames']]
        if getattr(args, 'output', None):
            exclusive_json(args.output, result, protected)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result['passed'] else 2
    except (ValueError, OSError, UnicodeError, struct.error) as exc:
        print(json.dumps({'passed': False, 'error': str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
