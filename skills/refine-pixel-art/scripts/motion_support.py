#!/usr/bin/env python3
"""Exact local selection/compositing and declared full-body evidence checks.

No pose artwork is synthesized. Pixel operations only copy existing RGBA cells
or encode a black/white selection mask. Geometry is not identity recognition.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import zlib


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exact_rgba_png(raw, width, height):
    """Encode supplied cells unchanged; no palette selection or image drawing."""
    require(len(raw) == width * height * 4, 'RGBA dimensions do not match byte count')
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)
    rows = b''.join(b'\0' + raw[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def rectangles(rects, width, height, label='motion_regions'):
    require(isinstance(rects, list), f'{label} must be a list')
    covered = set()
    for rect in rects:
        require(isinstance(rect, dict) and all(type(rect.get(k)) is int for k in ('x', 'y', 'width', 'height')),
                f'{label}: each rectangle requires integer x,y,width,height')
        x, y, rw, rh = (rect[k] for k in ('x', 'y', 'width', 'height'))
        require(x >= 0 and y >= 0 and rw > 0 and rh > 0 and x + rw <= width and y + rh <= height,
                f'{label}: rectangle exceeds native canvas')
        covered.update(yy * width + xx for yy in range(y, y + rh) for xx in range(x, x + rw))
    return covered


def selection(spec, width, height, base_dir, decode_png, *, require_local=False):
    """White selects; opaque black excludes. Multiple selectors need explicit intersection."""
    regions = spec.get('motion_regions')
    mask = spec.get('motion_mask')
    active = rectangles(regions, width, height) if regions is not None else None
    provenance = None
    if mask is not None:
        require(isinstance(mask, str) and mask, 'motion_mask must name a binary black/white PNG')
        path = (Path(base_dir) / mask).resolve(strict=True)
        info, raw = decode_png(path)
        require((info['width'], info['height']) == (width, height), 'motion_mask dimensions must equal native canvas')
        if 'motion_mask_sha256' in spec:
            require(spec['motion_mask_sha256'] == info['file_sha256'], 'motion_mask hash differs from predeclared motion_mask_sha256')
        pixels = [raw[i:i + 4] for i in range(0, len(raw), 4)]
        require(all(p in (b'\0\0\0\xff', b'\xff\xff\xff\xff') for p in pixels),
                'motion_mask must contain only opaque binary black/white pixels; no gray, colors, or transparency')
        selected = {i for i, p in enumerate(pixels) if p[0] == 255}
        require(selected, 'motion_mask must be nonempty')
        require(len(selected) < width * height, 'motion_mask must not select the full canvas')
        if active is not None:
            require(spec.get('mask_semantics') == 'intersection',
                    'Combined motion_regions and motion_mask require mask_semantics: intersection')
            active &= selected
        else:
            require(spec.get('mask_semantics', 'white_selects') == 'white_selects',
                    'A standalone motion_mask uses mask_semantics: white_selects')
            active = selected
        provenance = {'file': str(path), 'file_sha256': info['file_sha256'],
                      'rgba_sha256': info['rgba_sha256'], 'white_selected_pixels': len(selected),
                      'semantics': 'intersection' if regions is not None else 'white_selects'}
    elif 'mask_semantics' in spec or 'motion_mask_sha256' in spec:
        raise ValueError('mask_semantics/motion_mask_sha256 require motion_mask')
    if require_local or mask is not None:
        require(active is not None and active, 'Local motion selection must be nonempty')
        require(len(active) < width * height,
                'Full-canvas motion-region union defeats source preservation; use localized regions')
    return active, provenance


COVERAGE_PARTS = ('original_moving', 'motion_envelope', 'vacated')


def coverage_declaration(spec, kind, width, height, base_dir, decode_png):
    """Read one declared footprint; this does not identify anatomy or infer missing cells."""
    region_key, mask_key = kind + '_regions', kind + '_mask'
    require(region_key in spec or mask_key in spec,
            f'schema_version 2 requires {region_key} or {mask_key}; declare vacated_regions: [] only if none')
    active = rectangles(spec[region_key], width, height, region_key) if region_key in spec else None
    record = None
    if mask_key in spec:
        require(isinstance(spec[mask_key], str) and spec[mask_key], f'{mask_key} must name a binary PNG')
        path = (Path(base_dir) / spec[mask_key]).resolve(strict=True)
        info, raw = decode_png(path)
        require((info['width'], info['height']) == (width, height), f'{mask_key} dimensions must equal native canvas')
        pixels = [raw[i:i + 4] for i in range(0, len(raw), 4)]
        require(all(p in (b'\0\0\0\xff', b'\xff\xff\xff\xff') for p in pixels),
                f'{mask_key} must contain only opaque binary black/white pixels')
        expected = spec.get(mask_key + '_sha256')
        require(expected is None or expected == info['file_sha256'], f'{mask_key} hash differs from predeclared hash')
        cells = {i for i, pixel in enumerate(pixels) if pixel[0] == 255}
        semantics = spec.get(kind + '_mask_semantics', 'white_selects')
        if active is not None:
            require(semantics == 'intersection', f'Combined {region_key} and {mask_key} require {kind}_mask_semantics: intersection')
            active &= cells
        else:
            require(semantics == 'white_selects', f'Standalone {mask_key} uses white_selects semantics')
            active = cells
        record = {'file': str(path), 'file_sha256': info['file_sha256'],
                  'rgba_sha256': info['rgba_sha256'], 'semantics': semantics}
    else:
        require(kind + '_mask_semantics' not in spec and mask_key + '_sha256' not in spec,
                f'{kind}_mask_semantics/{mask_key}_sha256 require {mask_key}')
    require(active or kind == 'vacated', f'{kind} declaration must be nonempty')
    return active, record


def local_coverage(spec, master_info, width, height, base_dir, decode_png,
                   *, require_v2=False, require_review=False):
    """Measure declared containment and validate reviewer binding, never visual truth.

    The contract digest intentionally excludes review notes. It binds native dimensions,
    exact effective/declaration cells, selector declarations, and every mask file hash.
    A dishonest/incomplete original_moving declaration cannot be detected semantically.
    """
    is_v2 = type(spec.get('schema_version')) is int and spec['schema_version'] == 2
    keys = {kind + suffix for kind in COVERAGE_PARTS
            for suffix in ('_regions', '_mask', '_mask_sha256', '_mask_semantics')}
    require(is_v2 or not (set(spec) & (keys | {'coverage_review'})),
            'Coverage declarations/review require schema_version: 2')
    require(not require_v2 or is_v2, 'Local-motion preflight/compare require schema_version: 2 coverage contract')
    if not is_v2:
        return {'schema_version': 1, 'status': 'legacy_unverified',
                'visual_status': 'unreviewed', 'limitation': 'No declared whole-part coverage contract'}, [], {}
    require(spec.get('animation_mode', 'local') == 'local', 'Coverage contract is local-only; do not apply static locks to full_body')
    rectangles(spec.get('anchor_regions', []), width, height, 'anchor_regions')
    active, selection_mask = selection(spec, width, height, base_dir, decode_png, require_local=True)
    groups, masks, measurements, errors = {}, {}, {}, []
    for kind in COVERAGE_PARTS:
        cells, mask = coverage_declaration(spec, kind, width, height, base_dir, decode_png)
        groups[kind] = cells
        if mask:
            masks[kind] = mask
        missing = sorted(cells - active)
        measurements[kind] = {'declared_pixels': len(cells), 'uncovered_pixels': len(missing),
                              'uncovered_coordinates_sample': [[i % width, i // width] for i in missing[:32]]}
        if missing:
            errors.append(f'{kind}: {len(missing)} of {len(cells)} declared cells outside effective selection; '
                          f'first at {missing[0] % width},{missing[0] // width}. '
                          'Reject this plan before lock; revise coverage explicitly and repeat visual review. '
                          'Do not silently expand a locked mask or repair an old artifact.')
    bound_keys = keys | {'motion_regions', 'motion_mask', 'motion_mask_sha256', 'mask_semantics', 'anchor_regions'}
    binding = {'schema_version': 2, 'width': width, 'height': height,
               'declarations': {key: spec[key] for key in sorted(bound_keys) if key in spec},
               'effective_selection': sorted(active),
               'footprints': {key: sorted(value) for key, value in groups.items()},
               'mask_sha256': {key: value['file_sha256'] for key, value in masks.items()},
               'selection_mask_sha256': selection_mask['file_sha256'] if selection_mask else None}
    digest = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    review = spec.get('coverage_review')
    review_valid = False
    if review is not None:
        require(isinstance(review, dict) and review.get('status') in ('passed', 'failed', 'unreviewed'),
                'coverage_review requires status passed, failed, or unreviewed')
        if review['status'] != 'unreviewed':
            require(isinstance(review.get('notes'), str) and review['notes'].strip(), 'coverage_review requires nonempty notes')
            require(review.get('master_sha256') == master_info['file_sha256']
                    and review.get('contract_sha256') == digest,
                    'coverage_review hashes do not match current master/contract; review current images before lock')
        if review['status'] == 'failed':
            errors.append('Visual coverage reviewer marked this plan failed: ' + review['notes'])
        review_valid = review['status'] == 'passed'
    if require_review and not review_valid:
        errors.append('schema_version 2 assembly requires passed coverage_review with master_sha256, '
                      'contract_sha256 and notes after inspecting preflight previews; the tool cannot grant visual acceptance')
    result = {'schema_version': 2, 'status': 'failed' if errors else 'declared_containment_passed',
              'contract_sha256': digest, 'master_sha256': master_info['file_sha256'],
              'selected_pixels': len(active), 'measurements': measurements,
              'selection_mask': selection_mask, 'declaration_masks': masks,
              'coverage_review': review or {'status': 'unreviewed'},
              'visual_status': 'reviewer_asserted_passed' if review_valid else 'unreviewed',
              'limitation': 'Containment checks only the declared cells. A reviewer must verify the WHOLE original moving part, '
                            'future motion envelope, and vacated/erased area. Hash-bound assertions are not automated visual or identity guarantees.'}
    return result, errors, groups


def verify_encoded_png(data, raw, decode_png):
    """Validate an encoded derivative before publishing any of its artifacts."""
    with tempfile.TemporaryDirectory(prefix='pixel-cell-verification-') as temp:
        candidate = Path(temp) / 'encoded.png'
        candidate.write_bytes(data)
        _, actual = decode_png(candidate)
        require(actual == raw, 'Encoded PNG failed exact RGBA cell verification')


def publish(outputs):
    """Exclusive create with rollback; never overwrite sources or existing artifacts."""
    for path, _ in outputs:
        require(not path.exists() and not path.is_symlink(), f'Refusing to overwrite existing output: {path}')
    created = []
    try:
        for path, data in outputs:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                created.append(path)
                stream.write(data)
    except BaseException:
        for path in created:
            path.unlink()
        raise


def assemble(master, candidate, output, regions=None, mask=None):
    import pixel_pipeline as pipeline
    output = Path(output)
    require(output.suffix == '.png', 'Output must be a PNG')
    spec_path = Path(regions).resolve(strict=True) if regions else None
    spec_hash = sha(spec_path) if spec_path else None
    spec = pipeline.read_json(spec_path) if spec_path else {}
    if isinstance(spec, list):
        spec = {'motion_regions': spec}
    require(isinstance(spec, dict), 'Regions specification must be an object or rectangle list')
    require(spec.get('animation_mode', 'local') == 'local',
            'Local patch assembly requires animation_mode local; full_body poses must be packaged unchanged')
    spec = dict(spec)
    if mask:
        require('motion_mask' not in spec, 'Specify motion_mask in the spec or --mask, not both')
        spec['motion_mask'] = str(Path(mask).resolve(strict=True))
    master, candidate = Path(master).resolve(strict=True), Path(candidate).resolve(strict=True)
    mi, a = pipeline.decode_png(master)
    ci, b = pipeline.decode_png(candidate)
    w, h = mi['width'], mi['height']
    require((w, h) == (ci['width'], ci['height']),
            'Master and candidate must be single drawings with identical native dimensions/alignment')
    require(all(raw[i] in (0, 255) for raw in (a, b) for i in range(3, len(raw), 4)),
            'Both native inputs must have binary alpha')
    active, mask_record = selection(spec, w, h, spec_path.parent if spec_path else Path.cwd(),
                                    pipeline.decode_png, require_local=True)
    coverage, coverage_errors, _ = local_coverage(spec, mi, w, h, spec_path.parent if spec_path else Path.cwd(),
                                                 pipeline.decode_png, require_review=True)
    require(not coverage_errors, '\n'.join(coverage_errors))
    anchors = spec.get('anchor_regions', [])
    locked = rectangles(anchors, w, h, 'anchor_regions')
    for i in sorted(locked):
        require(a[i * 4:i * 4 + 4] == b[i * 4:i * 4 + 4],
                f'Pre-composite anchor drift at {i % w},{i // w}; reject or regenerate candidate, do not recenter')
    review = spec.get('alignment_review')
    if review is not None:
        require(isinstance(review, dict) and review.get('status') == 'passed'
                and isinstance(review.get('notes'), str) and review['notes'].strip(),
                'alignment_review requires status passed and nonempty notes')
        require(review.get('master_sha256') == mi['file_sha256'] and review.get('candidate_sha256') == ci['file_sha256'],
                'alignment_review input hashes do not match current files; review current images')
    assembled = b''.join((b if i in active else a)[i * 4:i * 4 + 4] for i in range(w * h))
    encoded = exact_rgba_png(assembled, w, h)
    verify_encoded_png(encoded, assembled, pipeline.decode_png)
    mask_raw = b''.join((b'\xff\xff\xff\xff' if i in active else b'\0\0\0\xff') for i in range(w * h))
    sources = [(master, mi['file_sha256']), (candidate, ci['file_sha256'])]
    if spec_path:
        sources.append((spec_path, spec_hash))
    if mask_record:
        sources.append((Path(mask_record['file']), mask_record['file_sha256']))
    for record in coverage.get('declaration_masks', {}).values():
        sources.append((Path(record['file']), record['file_sha256']))
    for path, expected in sources:
        require(sha(path) == expected, f'Input changed during assembly: {path}')
    def record(path, digest=None):
        return {'file': str(Path(path).resolve()), 'sha256': digest or sha(path)}
    report = {'operation': 'Exact native-coordinate RGBA patch assembly from generated artwork',
              'animation_mode': 'local', 'master': record(master), 'candidate': record(candidate),
              'output': record(output, hashlib.sha256(encoded).hexdigest()),
              'regions': record(spec_path) if spec_path else None,
              'motion_regions': spec.get('motion_regions'), 'motion_mask': mask_record,
              'mask_semantics': mask_record['semantics'] if mask_record else 'rectangle_union',
              'selected_pixels': len(active), 'anchor_regions': anchors, 'width': w, 'height': h,
              'alignment': 'identity; no translation, scaling or recentering',
              'alignment_review': review or {'status': 'unreviewed'},
              'coverage_contract': coverage,
              'raw_candidate_changed_pixels_outside_regions': sum(a[i*4:i*4+4] != b[i*4:i*4+4] for i in range(w*h) if i not in active),
              'changed_pixels': sum(a[i*4:i*4+4] != assembled[i*4:i*4+4] for i in range(w*h)),
              'changed_pixels_outside_regions': 0, 'visual_status': 'unreviewed',
              'visual_review_required': ['adjacent master/composed comparison at native and integer nearest-neighbor sizes',
                                         'whole original moving part covered; no retained detached source fragments',
                                         'patch seams', 'action readability', 'identity within moving regions', 'no clipped motion at mask edge'],
              'app_open_validated': False}
    publish([(output, encoded), (output.with_name(output.stem + '-mask.png'), exact_rgba_png(mask_raw, w, h)),
             (output.with_suffix('.assembly.json'), (json.dumps(report, indent=2) + '\n').encode())])
    require(sha(output) == report['output']['sha256'], 'Assembly output changed')
    return report


def geometry(raw, width):
    points = [(i // 4 % width, i // 4 // width) for i in range(0, len(raw), 4) if raw[i + 3]]
    if not points:
        return {'bbox': None, 'centroid_px': None, 'opaque_pixel_count': 0, 'lowest_occupied_y_px': None}
    xs, ys = zip(*points)
    return {'bbox': [min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1],
            'centroid_px': [sum(xs) / len(xs), sum(ys) / len(ys)],
            'opaque_pixel_count': len(points), 'lowest_occupied_y_px': max(ys)}


def number(value, label, minimum=0):
    require(type(value) in (int, float) and math.isfinite(value) and value >= minimum,
            f'{label} must be a finite number >= {minimum}')
    return value


def point(value, label, width, height):
    require(isinstance(value, list) and len(value) == 2, f'{label} must be [x,y]')
    x, y = (number(v, label) for v in value)
    require(x < width and y < height, f'{label} extends outside native canvas')
    return [x, y]


def full_body_qa(manifest, master_info, master_raw, frames, width, height):
    """Check declared geometric bounds and hash-bound reviewer records, not identity itself."""
    errors = []
    constraints = manifest.get('geometry_constraints', {})
    require(isinstance(constraints, dict), 'geometry_constraints must be an object')
    allowed = {'max_centroid_shift_px', 'bbox_width_ratio', 'bbox_height_ratio',
               'root_anchor_px', 'max_root_drift_px', 'contact_y_px', 'max_contact_drift_px'}
    require(not set(constraints) - allowed, 'Unknown geometry_constraints')
    for key in ('max_centroid_shift_px', 'max_root_drift_px', 'max_contact_drift_px', 'contact_y_px'):
        if key in constraints:
            number(constraints[key], key)
    for key in ('bbox_width_ratio', 'bbox_height_ratio'):
        if key in constraints:
            r = constraints[key]
            require(isinstance(r, list) and len(r) == 2 and all(type(v) in (int, float) for v in r), f'{key} must be [min,max]')
            require(0 < number(r[0], key) <= number(r[1], key), f'{key} range is invalid')
    require(('root_anchor_px' in constraints) == ('max_root_drift_px' in constraints),
            'root_anchor_px and max_root_drift_px must be declared together')
    require(('contact_y_px' in constraints) == ('max_contact_drift_px' in constraints),
            'contact_y_px and max_contact_drift_px must be declared together')
    if 'root_anchor_px' in constraints:
        point(constraints['root_anchor_px'], 'root_anchor_px', width, height)
    if 'contact_y_px' in constraints:
        require(constraints['contact_y_px'] < height, 'contact_y_px extends outside native canvas')
    reviews = manifest.get('full_body_reviews', [])
    require(isinstance(reviews, list), 'full_body_reviews must be a list')
    by_frame = {}
    for record in reviews:
        require(isinstance(record, dict) and type(record.get('frame')) is int
                and 0 <= record['frame'] < len(frames), 'full_body_reviews requires an in-range frame index')
        index = record['frame']
        require(index not in by_frame, 'Duplicate full_body_reviews frame')
        require(record.get('master_sha256') == master_info['file_sha256']
                and record.get('frame_sha256') == frames[index][0]['file_sha256'],
                f'Full-body review input hashes do not match current files for frame {index}')
        for kind in ('identity', 'landmarks', 'contact'):
            item = record.get(kind)
            if item is None:
                continue
            require(isinstance(item, dict) and item.get('status') in ('passed', 'failed', 'unverified')
                    and isinstance(item.get('notes'), str) and item['notes'].strip(),
                    f'Review {kind} requires status passed/failed/unverified and nonempty notes')
            if item['status'] == 'failed':
                errors.append(f'Frame {index} {kind} review failed: {item["notes"]}')
        if 'root_px' in record.get('landmarks', {}):
            point(record['landmarks']['root_px'], 'review root_px', width, height)
        if 'contact_px' in record.get('contact', {}):
            points = record['contact']['contact_px']
            require(isinstance(points, list) and points, 'review contact_px must be nonempty [x,y] points')
            for p in points:
                point(p, 'review contact_px', width, height)
        by_frame[index] = record
    baseline = geometry(master_raw, width)
    reports = []
    for index, (info, raw) in enumerate(frames):
        measured = geometry(raw, width)
        evidence = by_frame.get(index, {})
        checks = {}
        for key, axis in (('bbox_width_ratio', 2), ('bbox_height_ratio', 3)):
            if measured['bbox'] and baseline['bbox']:
                ratio = measured['bbox'][axis] / baseline['bbox'][axis]
                measured[key] = ratio
                if key in constraints:
                    checks[key] = constraints[key][0] <= ratio <= constraints[key][1]
            elif key in constraints:
                checks[key] = False
        if measured['centroid_px'] and baseline['centroid_px']:
            shift = math.dist(measured['centroid_px'], baseline['centroid_px'])
            measured['centroid_shift_px'] = shift
            if 'max_centroid_shift_px' in constraints:
                checks['max_centroid_shift_px'] = shift <= constraints['max_centroid_shift_px']
        elif 'max_centroid_shift_px' in constraints:
            checks['max_centroid_shift_px'] = False
        landmarks = evidence.get('landmarks', {})
        contact = evidence.get('contact', {})
        if 'root_anchor_px' in constraints:
            root = landmarks.get('root_px') if landmarks.get('status') == 'passed' else None
            checks['max_root_drift_px'] = bool(root and math.dist(root, constraints['root_anchor_px']) <= constraints['max_root_drift_px'])
        if 'contact_y_px' in constraints:
            pts = contact.get('contact_px') if contact.get('status') == 'passed' else None
            checks['max_contact_drift_px'] = bool(pts and all(abs(p[1] - constraints['contact_y_px']) <= constraints['max_contact_drift_px'] for p in pts))
        for key, passed in checks.items():
            if not passed:
                errors.append(f'Frame {index} geometry constraint {key} failed or lacks required reviewed evidence')
        reports.append({'frame': index, 'geometry': measured, 'declared_constraint_checks': checks,
                        'review_status': {kind: evidence.get(kind, {}).get('status', 'unverified') for kind in ('identity', 'landmarks', 'contact')},
                        'review_record': evidence or None})
    return {'status': 'review_records_complete' if all(all(v == 'passed' for v in r['review_status'].values()) for r in reports) else 'unverified',
            'master_geometry': baseline, 'constraints': constraints, 'frames': reports,
            'limitation': 'Geometry is technical evidence only. Review records are user-supplied assertions bound to file hashes; this tool does not recognize identity, pose semantics, root anatomy, or physical contact.',
            'exact_static_pixel_lock': 'not applied in full_body mode'}, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--master', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--regions')
    parser.add_argument('--mask')
    args = parser.parse_args()
    try:
        result = assemble(args.master, args.candidate, args.output, args.regions, args.mask)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
