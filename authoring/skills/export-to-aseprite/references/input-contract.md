# Input contract

## Common fields

A JSON object with `version: 1`, `mode`, and nonempty `frames`. Paths are relative to the manifest. Unknown fields and duplicate JSON keys are rejected, so unmapped source metadata cannot disappear silently. All measurements and indices are integers; booleans are not numbers.

`tags` is optional. Each tag has a unique `name`, inclusive zero-based `from` and `to`, optional `direction` (`forward`, `reverse`, `ping-pong`, `ping-pong-reverse`; default `forward`), and `repeat` (0–65535; default 0, Aseprite's unspecified/infinite-in-UI value). Omit tags when absent. A supplied repeat does not duplicate frame entries.

Every manifest frame requires `duration_ms` in 1–65535. A still PNG through the `static` command alone may use the explicitly documented 100 ms serialization default; this exception never extends to a manifest sequence or sheet.

## Sequence

Use `mode: "sequence"` and `frames: [{"png": "a.png", "duration_ms": 83}, ...]`. Optional `layer_name` defaults to `Flattened source artwork`. All PNGs must have identical dimensions. Retain duplicate references and their distinct durations. Do not guess filename ordering. See `assets/sequence.template.json`.

## Sheet

Use `mode: "sheet"`, `png`, and either:

- `frame_size: [width,height]`, `grid: {"columns": n, "rows": n, "margin": [x,y], "spacing": [x,y]}` and frames with `cell` and `duration_ms`. Cell indices are row-major, zero-based. Optional margins/spacing default to zero. Margins are symmetric. The layout must exactly account for sheet dimensions, including unused cells. Timeline entries can skip, reorder or repeat cells.
- Frames with `rect: [x,y,width,height]` and `duration_ms`. Coordinates are zero-based; bounds must be inside the sheet. Every rectangle has the same frame size. Use this route for asymmetric margins or irregular cell positions. Do not also specify a grid.

An optional `layer_name` is allowed. Explicit gutters/margins and unreferenced cells are not exported. The exact bytes inside selected rectangles are preserved. See `assets/sheet-grid.template.json` and `assets/sheet-rects.template.json`.

## Genuine layers

Use `mode: "layers"`, `canvas: [width,height]`, and a `layers` array in **bottom-to-top order**. Each layer has a unique `name` and optional `opacity` (0–255, default 255), `visible` (default true), `editable` (default true), and `blend_mode` (only `normal`, the default). These defaults describe ordinary source layers, not an invitation to replace supplied metadata.

Frames have `duration_ms` and `cels`. A cel has `layer` (exact layer name), `png`, optional `x`/`y` (-32768–32767, default 0), and `opacity` (0–255, default 255). PNG dimensions determine cel size. At most one cel per layer/frame. `cels: []` means an explicitly blank frame; absent cels do not inherit earlier art. At least one PNG cel must exist in the project. Off-canvas cels are allowed when explicitly positioned; no clipping is applied. Full-canvas separate layer images work at 0,0.

No groups, blend modes other than normal, tilemaps, linked-cel identity, blend/render-engine equivalence, slice metadata, layer UUIDs, or arbitrary native document metadata are imported. Preserve real source layers only inside this supported subset. Do not divide or duplicate flattened artwork to fabricate them. See `assets/layers.template.json`.

## PNG/color rules and safety bounds

Supported: still PNG with 1/2/4/8-bit samples when valid for its color type; RGB, RGBA, grayscale, gray+alpha and palette inputs. Inputs are decoded losslessly to 8-bit RGBA. Preserve all source sample values after that representation change, including hidden RGB. Output is always RGBA, never a claim of unchanged PNG index encoding.

Indexed PNGs keep complete PLTE entry order and RGB, plus all tRNS alpha values (unspecified entries have alpha 255). Unused entries are kept. All supplied indexed palettes must agree. A shared palette can coexist with truecolor PNGs, but the tool does not quantize those cels. Shared source ICC bytes or sRGB profiles are retained; mixed profiles, standalone gAMA, HDR metadata, 16-bit samples, and animated PNGs are rejected. For cHRM-only input, exact raw chromaticity bytes are preserved in each source report entry. The Aseprite remains untagged because it has no equivalent partial-profile field; do not infer a transfer curve or claim color-managed appearance equivalence. Untagged images stay untagged.

Limits: 65535-pixel width/height, 16,777,216 pixels per image/cel/canvas, 67,108,864 loaded source or expanded timeline pixels, 10,000 timeline frames, 1024 source layers, 536,870,912 file bytes. These are safety bounds, not Aseprite's full feature limits. Do not circumvent them by lossy editing.

Output/report paths must be new and distinct from every input. Output parent directories must exist. Sources are read only. If an I/O failure occurs after the Aseprite file is created but before the sidecar is saved, preserve and inspect that file; don't blindly retry to the same path.
