#!/usr/bin/env bash
# Exact RGBA selection only; supports rectangles and predeclared shaped masks.
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 "$script_dir/motion_support.py" "$@"
