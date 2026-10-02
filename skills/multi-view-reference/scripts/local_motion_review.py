#!/usr/bin/env python3
"""Local-only coverage preflight and adjacent post-composite technical previews.

No artwork is generated, repaired, accepted, or overwritten. Native/NN snapshots
copy exact RGBA cells; background/overlay images are labeled diagnostic previews.
Component and delta alerts do not recognize anatomy, identity, or mask sufficiency.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pixel_pipeline as pipeline
from motion_support import (COVERAGE_PARTS, exact_rgba_png, local_coverage, publish,
                            rectangles, require, selection, sha, verify_encoded_png)

BACKGROUNDS = {'white': (255, 255, 255), 'dark': (24, 24, 24),
               'high-contrast': (255, 0, 255), 'checker': None}


def nn(raw, width, height, scale):
    """Integer nearest-neighbor cell replication, including hidden RGB and alpha."""
    return b''.join(b''.join(raw[(y * width + x) * 4:(y * width + x + 1) * 4] * scale
                            for x in range(width)) * scale for y in range(height))


def mask_cells(cells, width, height):
    return b''.join(b'\xff\xff\xff\xff' if i in cells else b'\0\0\0\xff'
                    for i in range(width * height))


def on_background(raw, width, height, background):
    """Binary-alpha preview; every opaque artwork cell remains byte-identical."""
    require(background in BACKGROUNDS, 'Unknown preview background')
    result = bytearray(raw)
    for i in range(width * height):
        if raw[i * 4 + 3] == 0:
            color = BACKGROUNDS[background]
            if color is None:
                gray = 192 if (i % width + i // width) % 2 == 0 else 96
                color = (gray, gray, gray)
            result[i * 4:i * 4 + 4] = bytes((*color, 255))
    return bytes(result)


def selection_overlay(rendered, cells):
    """Cyan tint is a review aid only; never an animation source."""
    result = bytearray(rendered)
    for i in cells:
        r, g, b = rendered[i * 4:i * 4 + 3]
        result[i * 4:i * 4 + 3] = bytes((r // 2, (g + 255) // 2, (b + 255) // 2))
    return bytes(result)


def adjacent(columns, width, height):
    return b''.join(b''.join(raw[y * width * 4:(y + 1) * width * 4] for raw in columns)
                    for y in range(height))


def component_cells(raw, width, height):
    """Eight-connected nonzero-alpha groups; decorative islands may be intentional."""
    remaining = {i for i in range(width * height) if raw[i * 4 + 3]}
    groups = []
    while remaining:
        first = remaining.pop()
        group, todo = {first}, [first]
        while todo:
            i = todo.pop()
            x, y = i % width, i // width
            for yy in range(max(0, y - 1), min(height, y + 2)):
                for xx in range(max(0, x - 1), min(width, x + 2)):
                    n = yy * width + xx
                    if n in remaining:
                        remaining.remove(n)
                        group.add(n)
                        todo.append(n)
        groups.append(group)
    return sorted(groups, key=lambda cells: (-len(cells), min(cells)))


def delta_diagnostics(a, b, width, height, active, anchors=frozenset()):
    source, candidate = component_cells(a, width, height), component_cells(b, width, height)
    changed = {i for i in range(width * height) if a[i * 4:i * 4 + 4] != b[i * 4:i * 4 + 4]}
    outside = changed - active
    anchor_drift = changed & anchors
    summaries, fragments = [], []
    source_index = {i: index for index, cells in enumerate(source) for i in cells}
    candidate_index = {i: index for index, cells in enumerate(candidate) for i in cells}
    split_source = {index for index, cells in enumerate(source)
                    if len({candidate_index[i] for i in cells if i in candidate_index}) > 1}
    for index, cells in enumerate(candidate):
        xs, ys = [i % width for i in cells], [i // width for i in cells]
        unchanged = cells.isdisjoint(changed)
        wholly_static = cells.isdisjoint(active)
        split = bool({source_index[i] for i in cells if i in source_index} & split_source)
        record = {'index': index, 'opaque_pixels': len(cells),
                  'bbox': [min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1],
                  'unchanged_from_master': unchanged, 'wholly_outside_selection': wholly_static}
        summaries.append(record)
        if unchanged and wholly_static and split:
            fragments.append(record)
    warnings = []
    if len(candidate) > len(source):
        warnings.append(f'Eight-connected opaque components increased from {len(source)} to {len(candidate)}; inspect separation and edges')
    if fragments:
        warnings.append(f'{len(fragments)} unchanged component(s) outside selection overlap a formerly connected source component; '
                        'possible retained source fragments. Inspect whole-part coverage; this is an alert, not a semantic diagnosis')
    return {'changed_rgba_pixels': len(changed), 'changed_pixels_outside_selection': len(outside),
            'outside_changed_coordinates_sample': [[i % width, i // width] for i in sorted(outside)[:32]],
            'changed_pixels_inside_anchors': len(anchor_drift),
            'anchor_changed_coordinates_sample': [[i % width, i // width] for i in sorted(anchor_drift)[:32]],
            'alpha_erased_pixels': sum(a[i * 4 + 3] == 255 and b[i * 4 + 3] == 0 for i in range(width * height)),
            'alpha_added_pixels': sum(a[i * 4 + 3] == 0 and b[i * 4 + 3] == 255 for i in range(width * height)),
            'components': {'connectivity': 8, 'master_count': len(source), 'candidate_count': len(candidate),
                           'candidate': summaries, 'possible_retained_source_fragments': fragments},
            'limitation': 'Counts and connectivity are alerts only. Unchanged/disconnected cells may be intentional; no alert does not establish identity or coverage.'}, warnings


def review(master, regions, output, candidate=None, scale=8, neighbor=None):
    require(type(scale) is int and 1 <= scale <= 64, 'scale must be an integer in 1..64')
    require(neighbor is None or candidate is not None, '--neighbor is only valid for compare with a candidate')
    master, regions = Path(master).resolve(strict=True), Path(regions).resolve(strict=True)
    output = Path(output).absolute()
    require(not output.exists() and not output.is_symlink(), f'Refusing to overwrite existing output directory: {output}')
    spec_hash = sha(regions)
    spec = pipeline.read_json(regions)
    require(isinstance(spec, dict), 'Preflight/compare require a schema_version 2 object, not legacy rectangles')
    require(spec.get('animation_mode', 'local') == 'local', 'This helper is local-only; full_body has no static lock')
    info, raw = pipeline.decode_png(master)
    width, height = info['width'], info['height']
    require(all(raw[i] in (0, 255) for i in range(3, len(raw), 4)), 'Master must have binary alpha')
    active, selected_mask = selection(spec, width, height, regions.parent, pipeline.decode_png, require_local=True)
    coverage, errors, groups = local_coverage(spec, info, width, height, regions.parent, pipeline.decode_png,
                                             require_v2=True, require_review=candidate is not None)
    anchors = rectangles(spec.get('anchor_regions', []), width, height, 'anchor_regions')
    sources = [(master, info['file_sha256']), (regions, spec_hash)]
    if selected_mask:
        sources.append((Path(selected_mask['file']), selected_mask['file_sha256']))
    for record in coverage['declaration_masks'].values():
        sources.append((Path(record['file']), record['file_sha256']))
    drawings = [('master', raw)]
    diagnostics, warnings, candidate_record = None, [], None
    neighbor_record, neighbor_diagnostics, transition_diagnostics = None, None, None
    neighbor_raw = None
    if neighbor is not None:
        neighbor = Path(neighbor).resolve(strict=True)
        ni, neighbor_raw = pipeline.decode_png(neighbor)
        require((width, height) == (ni['width'], ni['height']), 'Neighbor must match native master dimensions/alignment')
        require(all(neighbor_raw[i] in (0, 255) for i in range(3, len(neighbor_raw), 4)), 'Neighbor must have binary alpha')
        sources.append((neighbor, ni['file_sha256']))
        neighbor_record = {'file': str(neighbor), 'file_sha256': ni['file_sha256'], 'rgba_sha256': ni['rgba_sha256']}
        drawings.append(('neighbor', neighbor_raw))
        neighbor_diagnostics, neighbor_warnings = delta_diagnostics(raw, neighbor_raw, width, height, active, anchors)
        warnings.extend('Neighbor versus original master: ' + warning for warning in neighbor_warnings)
        if neighbor_diagnostics['changed_pixels_outside_selection']:
            errors.append(f"{neighbor_diagnostics['changed_pixels_outside_selection']} neighbor RGBA cells changed outside original locked selection; reject this neighbor, do not rebind the master or expand the mask")
        if neighbor_diagnostics['changed_pixels_inside_anchors']:
            errors.append(f"{neighbor_diagnostics['changed_pixels_inside_anchors']} neighbor RGBA cells drifted inside original anchor_regions; reject or regenerate without recentering")
    if candidate is not None:
        candidate = Path(candidate).resolve(strict=True)
        ci, other = pipeline.decode_png(candidate)
        require((width, height) == (ci['width'], ci['height']), 'Candidate must match native master dimensions/alignment')
        require(all(other[i] in (0, 255) for i in range(3, len(other), 4)), 'Candidate must have binary alpha')
        sources.append((candidate, ci['file_sha256']))
        candidate_record = {'file': str(candidate), 'file_sha256': ci['file_sha256'], 'rgba_sha256': ci['rgba_sha256']}
        drawings.append(('candidate', other))
        diagnostics, candidate_warnings = delta_diagnostics(raw, other, width, height, active, anchors)
        warnings.extend(candidate_warnings)
        if diagnostics['changed_pixels_outside_selection']:
            errors.append(f"{diagnostics['changed_pixels_outside_selection']} candidate RGBA cells changed outside locked selection; reject this candidate, do not expand the mask after drift")
        if diagnostics['changed_pixels_inside_anchors']:
            errors.append(f"{diagnostics['changed_pixels_inside_anchors']} candidate RGBA cells drifted inside original anchor_regions; reject or regenerate without recentering")
        if neighbor_raw is not None:
            transition_diagnostics, transition_warnings = delta_diagnostics(neighbor_raw, other, width, height, active, anchors)
            warnings.extend('Neighbor to candidate: ' + warning for warning in transition_warnings)
    assets = []
    preview_records = []

    def add(name, pixels, w=width, h=height, *, columns=None, diagnostic=False):
        require(w * h * scale * scale <= pipeline.MAX_PIXELS, 'Preview exceeds safe pixel limit; use a smaller --scale')
        for suffix, cells, pw, ph in [('native', pixels, w, h), ('nn', nn(pixels, w, h, scale), w * scale, h * scale)]:
            data = exact_rgba_png(cells, pw, ph)
            verify_encoded_png(data, cells, pipeline.decode_png)
            filename = f'{name}-{suffix}.png'
            assets.append((output / filename, data))
            preview_records.append({'file': filename, 'file_sha256': hashlib.sha256(data).hexdigest(),
                                    'rgba_sha256': hashlib.sha256(cells).hexdigest(), 'width': pw, 'height': ph,
                                    'scale': 1 if suffix == 'native' else scale,
                                    'columns_left_to_right': columns,
                                    'diagnostic_only': diagnostic, 'native_cells_verified': True})

    for name, drawing in drawings:
        add(name, drawing)
    add('effective-selection', mask_cells(active, width, height), diagnostic=True)
    for kind in COVERAGE_PARTS:
        add(kind, mask_cells(groups[kind], width, height), diagnostic=True)
    for background in BACKGROUNDS:
        rendered = [on_background(drawing, width, height, background) for _, drawing in drawings]
        add('adjacent-' + background, adjacent(rendered, width, height), width * len(drawings), height,
            columns=[name for name, _ in drawings], diagnostic=True)
        coverage_columns = [rendered[0], selection_overlay(rendered[0], active)]
        coverage_columns.extend(selection_overlay(rendered[0], groups[kind]) for kind in COVERAGE_PARTS)
        add('coverage-' + background, adjacent(coverage_columns, width, height), width * len(coverage_columns), height,
            columns=['master', 'effective selection (cyan tint)', 'original moving footprint (cyan tint)',
                     'future motion envelope (cyan tint)', 'vacated/erased area (cyan tint)'], diagnostic=True)
    report = {'schema_version': 2, 'operation': 'compare' if candidate else 'preflight',
              'technical_pass': not errors, 'errors': errors, 'warnings': warnings,
              'master': {'file': str(master), 'file_sha256': info['file_sha256'], 'rgba_sha256': info['rgba_sha256']},
              'candidate': candidate_record, 'neighbor': neighbor_record,
              'regions': {'file': str(regions), 'file_sha256': spec_hash},
              'width': width, 'height': height, 'coverage_contract': coverage, 'diagnostics': diagnostics,
              'neighbor_against_original_master': neighbor_diagnostics,
              'neighbor_to_candidate': transition_diagnostics,
              'visual_status': 'unreviewed', 'automatic_visual_acceptance': False,
              'review_required': ['Inspect native and integer-NN previews on white, dark, checker, and high-contrast backgrounds',
                                  'Verify the WHOLE original moving part, future envelope, and vacated/erased area before locking',
                                  'After composition inspect adjacent master/candidate for retained fragments, seams, clipped motion, and identity'],
              'limitation': 'Technical containment cannot verify that the declared footprint is anatomically complete. '
                            'Previews and component/delta alerts assist a separate visual review; they never grant acceptance.',
              'previews': preview_records}
    assets.append((output / 'review.json', (json.dumps(report, indent=2) + '\n').encode()))
    for path, expected in sources:
        require(sha(path) == expected, f'Input changed during review: {path}')
    # Exclusive directory reservation, then exclusive file creation. Failed runs do
    # not leave a partly published review or replace any prior review/art artifact.
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(exist_ok=False)
    try:
        publish(assets)
        for path, expected in sources:
            require(sha(path) == expected, f'Input changed during review: {path}')
    except BaseException:
        shutil.rmtree(output)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('preflight', 'compare'):
        command = commands.add_parser(name)
        command.add_argument('--master', required=True)
        command.add_argument('--regions', required=True)
        command.add_argument('--output', required=True, help='NEW directory; existing paths are never overwritten')
        command.add_argument('--scale', type=int, default=8)
        if name == 'compare':
            command.add_argument('--candidate', required=True, help='Already composed native frame; this command does not compose or repair')
            command.add_argument('--neighbor', help='Optional adjacent composed frame; coverage remains bound to original --master')
    args = parser.parse_args(argv)
    try:
        result = review(args.master, args.regions, args.output, getattr(args, 'candidate', None), args.scale,
                        getattr(args, 'neighbor', None))
        print(json.dumps(result, indent=2))
        return 0 if result['technical_pass'] else 2
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
