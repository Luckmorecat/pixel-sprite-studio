#!/usr/bin/env python3
"""Enlarge an accepted native master as an exact, integer nearest-neighbor reference.

This technical derivative copies RGBA cells unchanged. It is the primary art
reference, not a prediction of the dimensions returned by an image generator.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import pixel_pipeline as pipeline
from motion_support import exact_rgba_png, publish, verify_encoded_png


def enlarge(source, output, scale, acceptance, project_path=None):
    scale = pipeline.integer(scale, 'scale', 1, 64)
    source, acceptance = Path(source).resolve(strict=True), Path(acceptance).resolve(strict=True)
    output = Path(output)
    pipeline.require(output.suffix == '.png', 'Output must be a PNG')
    info, raw = pipeline.decode_png(source)
    review = pipeline.read_json(acceptance)
    pipeline.require(isinstance(review, dict) and review.get('status') == 'accepted'
                     and review.get('artifact_sha256') == info['file_sha256']
                     and isinstance(review.get('notes'), str) and review['notes'].strip(),
                     'Reference enlargement requires accepted, hash-bound native review with notes; technical checks do not grant acceptance')
    stats, _ = pipeline.pixel_stats(raw, info['width'])
    pipeline.require(stats['binary_alpha'], 'Accepted native master must have binary alpha')
    project = None
    if project_path:
        from project_config import enforce_normalization
        project = enforce_normalization(project_path, info['width'], info['height'])
        pipeline.require(stats['palette_count_visible'] <= project['palette_max'], 'Master violates project palette_max')
        margins = stats['clear_margins']
        pipeline.require(margins is not None and min(margins.values()) >= project['min_margin'], 'Master violates project min_margin')
    w, h = info['width'] * scale, info['height'] * scale
    pipeline.require(w * h <= pipeline.MAX_PIXELS, 'Enlarged reference exceeds safe pixel limit')
    rows = []
    for y in range(info['height']):
        row = raw[y * info['width'] * 4:(y + 1) * info['width'] * 4]
        rows.append(b''.join(row[i:i + 4] * scale for i in range(0, len(row), 4)) * scale)
    enlarged = b''.join(rows)
    data = exact_rgba_png(enlarged, w, h)
    verify_encoded_png(data, enlarged, pipeline.decode_png)
    record = {'schema_version': 1, 'operation': 'Exact integer nearest-neighbor native reference enlargement',
              'source': {'file': str(source), 'file_sha256': info['file_sha256'], 'rgba_sha256': info['rgba_sha256'],
                         'width': info['width'], 'height': info['height']},
              'output': {'file': str(output.resolve()), 'file_sha256': hashlib.sha256(data).hexdigest(),
                         'rgba_sha256': hashlib.sha256(enlarged).hexdigest(), 'width': w, 'height': h},
              'scale': scale, 'acceptance_sha256': pipeline.digest(acceptance.read_bytes()), 'acceptance': review,
              'project_provenance': project['project_provenance'] if project else None,
              'native_cells_verified': True, 'palette_and_alpha_preserved': True,
              'reference_role': 'primary generation reference derived from accepted native master',
              'output_geometry_warning': 'Inspect actual generator output dimensions. This reference does not establish generated source size, crop, grid phase, or alignment.',
              'creative_repair': False}
    pipeline.require(pipeline.digest(source.read_bytes()) == info['file_sha256'], 'Native source changed during enlargement')
    provenance = output.with_suffix('.reference.json')
    pipeline.require(source not in (output.resolve(), provenance.resolve()) and acceptance not in (output.resolve(), provenance.resolve()),
                     'Reference output would overwrite an input')
    publish([(output, data), (provenance, (json.dumps(record, indent=2) + '\n').encode())])
    pipeline.require(pipeline.digest(output.read_bytes()) == record['output']['file_sha256'], 'Enlarged output hash mismatch')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--scale', required=True, type=int)
    parser.add_argument('--acceptance', required=True)
    parser.add_argument('--project')
    args = parser.parse_args()
    try:
        print(json.dumps(enlarge(args.input, args.output, args.scale, args.acceptance, args.project), indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
