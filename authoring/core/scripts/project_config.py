#!/usr/bin/env python3
"""Strict, shared pixel-project constraints. Python standard library only.

Public API:
  load_project(path) -> project dict, with resolved metadata under _meta.
  enforce_manifest(manifest, project_path) -> deep-copied merged manifest.
  enforce_normalization(project_path, width=None, height=None, colors=None)
      -> dict(width, height, colors, palette_max, binary_alpha, min_margin,
              anchor_px, project_provenance).
Missing explicit helper arguments inherit the project. Any explicit conflicting
value is an error, including a stricter bound: change the project deliberately.
Exact observed counts are compared to bounds, never equated to those bounds.
ProjectError subclasses ValueError. No input file is changed.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys


class ProjectError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ProjectError(message)


def integer(value, label, minimum=0, maximum=16_777_216):
    require(type(value) is int and minimum <= value <= maximum,
            f'{label} must be an integer in {minimum}..{maximum}')
    return value


def read_json(path):
    def pairs(items):
        obj = {}
        for key, value in items:
            require(key not in obj, f'Duplicate JSON key: {key}')
            obj[key] = value
        return obj
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs,
                           parse_constant=lambda x: (_ for _ in ()).throw(ProjectError(f'Invalid JSON constant: {x}')))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectError(f'Cannot read JSON {path}: {exc}') from exc
    require(isinstance(value, dict), f'{path} must contain a JSON object')
    return value


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative_file(root, value, label):
    """Resolve a portable contained relative file; symlink escapes also fail."""
    require(isinstance(value, str) and value and '\\' not in value and '\x00' not in value,
            f'{label} must be a relative POSIX file path')
    part = PurePosixPath(value)
    require(not part.is_absolute() and '..' not in part.parts and ':' not in part.parts[0],
            f'{label} must not be absolute or escape its root')
    root = Path(root).resolve()
    try:
        path = (root / value).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ProjectError(f'{label} file is missing: {value}') from exc
    require(path.is_relative_to(root) and path.is_file(), f'{label} escapes its root or is not a file: {value}')
    return path


def pair(value, label, zero=False):
    require(isinstance(value, list) and len(value) == 2, f'{label} must be [x,y]')
    for i, entry in enumerate(value):
        integer(entry, f'{label}[{i}]', 0 if zero else 1, 65535)
    return value


def load_project(path):
    try:
        path = Path(path).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ProjectError(f'Project file is missing: {path}') from exc
    project = read_json(path)
    require('_meta' not in project, 'Project _meta is reserved for resolved metadata')
    require(project.get('schema_version') in ('2.0', '3.0'), 'Project schema_version must be "3.0" (or legacy "2.0")')
    for field in ('asset_id', 'brief'):
        require(isinstance(project.get(field), str) and project[field].strip(), f'Project {field} is required')
    canvas = pair(project.get('native_canvas_px'), 'native_canvas_px')
    require(canvas[0] * canvas[1] <= 16_777_216, 'Native canvas exceeds safe pixel limit')
    limits = project.get('limits')
    require(isinstance(limits, dict), 'Project limits must be an object')
    require(not set(limits) - {'palette_max', 'binary_alpha', 'min_margin'}, 'Unknown project limit')
    integer(limits.get('palette_max'), 'limits.palette_max', 2, 256)
    require(limits.get('binary_alpha') is True, 'limits.binary_alpha must be true; this toolchain cannot silently relax alpha')
    integer(limits.get('min_margin'), 'limits.min_margin', 0, (min(canvas) - 1) // 2)
    budget = project.get('budget')
    require(isinstance(budget, dict), 'Project budget must be an object')
    integer(budget.get('max_calls'), 'budget.max_calls', 0, 100000)
    for key, value in budget.items():
        integer(value, f'budget.{key}', 0, 100000)
    anchor = project.get('anchor_px')
    if anchor is not None:
        pair(anchor, 'anchor_px', zero=True)
        require(anchor[0] < canvas[0] and anchor[1] < canvas[1], 'anchor_px lies outside native canvas')
    animation = project.get('animation')
    if animation is not None:
        require(isinstance(animation, dict), 'animation must be an object')
        allowed = {'mode', 'duration_ms', 'max_unique_drawings', 'max_timeline_entries', 'min_unique_drawings'}
        require(not set(animation) - allowed, 'Unknown animation constraint: ' + ', '.join(sorted(set(animation) - allowed)))
        require(animation.get('mode') in ('local', 'full_body'), 'animation.mode must be local or full_body')
        integer(animation.get('duration_ms'), 'animation.duration_ms', 1, 268431360)
        maximum = integer(animation.get('max_unique_drawings'), 'animation.max_unique_drawings', 1, 4096)
        entries = integer(animation.get('max_timeline_entries'), 'animation.max_timeline_entries', 1, 4096)
        require(maximum <= entries, 'max_unique_drawings exceeds max_timeline_entries')
        if 'min_unique_drawings' in animation:
            minimum = integer(animation['min_unique_drawings'], 'animation.min_unique_drawings', 1, 4096)
            require(minimum <= maximum, 'min_unique_drawings exceeds max_unique_drawings')
    profile_path = relative_file(path.parent, project.get('profile'), 'profile')
    profile = read_json(profile_path)
    project['_meta'] = {'project_path': str(path), 'project_sha256': sha256(path),
                        'profile_path': str(profile_path), 'profile_sha256': sha256(profile_path),
                        'profile_data': profile}
    return project


def provenance(project):
    return {'schema_version': project['schema_version'], 'asset_id': project['asset_id'],
            'project_sha256': project['_meta']['project_sha256'],
            'profile_sha256': project['_meta']['profile_sha256']}


def exact(target, key, expected, label=None):
    if key in target:
        require(type(target[key]) is type(expected) and target[key] == expected,
                f'{label or key} conflicts with project: {target[key]!r} != {expected!r}')
    target[key] = copy.deepcopy(expected)


def enforce_manifest(manifest, project_path):
    require(isinstance(manifest, dict), 'Manifest must be an object')
    result = copy.deepcopy(manifest)
    project = load_project(project_path)
    for key, value in zip(('width', 'height'), project['native_canvas_px']):
        exact(result, key, value)
    for key, value in project['limits'].items():
        exact(result, key, value)
    if 'native_canvas_px' in result:
        exact(result, 'native_canvas_px', project['native_canvas_px'])
    if 'limits' in result:
        require(isinstance(result['limits'], dict), 'Manifest limits must be an object')
        for key, value in result['limits'].items():
            require(key in project['limits'] and value == project['limits'][key] and type(value) is type(project['limits'][key]),
                    f'Manifest limits.{key} conflicts with project')
        result['limits'] = copy.deepcopy(project['limits'])
    if project.get('anchor_px') is not None:
        exact(result, 'anchor_px', project['anchor_px'])
    elif 'anchor_px' in result:
        require(result['anchor_px'] is None, 'Manifest anchor must first be declared in project')
    constraints = result.setdefault('constraints', {})
    require(isinstance(constraints, dict), 'constraints must be an object')
    for key, value in constraints.items():
        integer(value, f'constraints.{key}', 1, 268431360)
    scope = result.get('scope', 'animation')
    require(scope in ('static', 'animation'), 'Manifest scope must be static or animation')
    if scope == 'static':
        require(not {'animation_mode', 'animation', 'motion_regions', 'motion_mask', 'motion_mask_sha256', 'mask_semantics', 'geometry_constraints', 'full_body_reviews'} & set(result),
                'Static manifests must not contain animation-specific fields')
        require(not {'total_duration_ms', 'max_timeline_frame_count', 'max_distinct_drawing_count', 'min_distinct_drawing_count'} & set(constraints),
                'Static manifests must not contain animation duration or bound constraints')
    animation = project.get('animation') if scope == 'animation' else None
    if animation:
        exact(result, 'animation_mode', animation['mode'])
        mapping = {'duration_ms': 'total_duration_ms', 'max_unique_drawings': 'max_distinct_drawing_count',
                   'max_timeline_entries': 'max_timeline_frame_count', 'min_unique_drawings': 'min_distinct_drawing_count'}
        for source, target in mapping.items():
            if source in animation:
                exact(constraints, target, animation[source], f'constraints.{target}')
        if 'animation' in result:
            require(isinstance(result['animation'], dict), 'Manifest animation must be an object')
            for key, value in result['animation'].items():
                require(key in animation and type(value) is type(animation[key]) and value == animation[key],
                        f'Manifest animation.{key} conflicts with project')
            result['animation'] = copy.deepcopy(animation)
    for exact_key, max_key, min_key in (
            ('timeline_frame_count', 'max_timeline_frame_count', None),
            ('distinct_drawing_count', 'max_distinct_drawing_count', 'min_distinct_drawing_count')):
        if exact_key in constraints:
            if max_key in constraints:
                require(constraints[exact_key] <= constraints[max_key], f'{exact_key} exceeds {max_key}')
            if min_key and min_key in constraints:
                require(constraints[exact_key] >= constraints[min_key], f'{exact_key} is below {min_key}')
        if min_key and min_key in constraints and max_key in constraints:
            require(constraints[min_key] <= constraints[max_key], f'{min_key} exceeds {max_key}')
    frames = result.get('frames', result.get('timeline'))
    if frames is not None:
        require(isinstance(frames, list), 'frames/timeline must be an array')
        if 'max_timeline_frame_count' in constraints:
            require(len(frames) <= constraints['max_timeline_frame_count'], 'Timeline exceeds project max_timeline_entries')
        if 'timeline_frame_count' in constraints:
            require(len(frames) == constraints['timeline_frame_count'], 'Timeline does not match exact count')
        durations = []
        for i, frame in enumerate(frames):
            require(isinstance(frame, dict), f'Frame {i} must be an object')
            durations.append(integer(frame.get('duration_ms'), f'Frame {i} duration_ms', 1, 65535))
        if 'total_duration_ms' in constraints:
            require(sum(durations) == constraints['total_duration_ms'], 'Timeline duration conflicts with project')
    exact(result, 'project_provenance', provenance(project))
    return result


def enforce_normalization(project_path, width=None, height=None, colors=None):
    project = load_project(project_path)
    expected = dict(zip(('width', 'height'), project['native_canvas_px']))
    expected['colors'] = project['limits']['palette_max']
    for key, value in (('width', width), ('height', height), ('colors', colors)):
        if value is not None:
            require(type(value) is int and value == expected[key], f'Normalization {key} conflicts with project: {value!r} != {expected[key]}')
    return {**expected, **project['limits'], 'anchor_px': project.get('anchor_px'),
            'project_provenance': provenance(project)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project')
    args = parser.parse_args(argv)
    try:
        print(json.dumps(load_project(args.project), indent=2, sort_keys=True))
        return 0
    except ProjectError as exc:
        print(f'Project error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
