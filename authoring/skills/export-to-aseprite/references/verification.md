# Verification scope

The encoder writes the official Aseprite header, normal-layer, compressed-RGBA-cel, tag, optional palette, and optional color-profile chunks. The strict inspector is intentionally not a general native-file reader. It rejects chunks outside this export subset.

Source: https://github.com/aseprite/aseprite/blob/main/docs/ase-file-specs.md

## Deterministic checks

The export command independently parses its encoded bytes and compares the resulting canvas, actual cel RGBA bytes, duration of every frame, cel coordinates/opacity, layer order/name/visibility/editability/opacity, all tags, palette entries, and color profile with the normalized source contract. Repeated timeline entries are actual separate frames. It reports source file hashes, decoded RGBA hashes, and output SHA-256.

The bundled synthetic suite also has a separate offset-based decoder. Run:

```bash
python "$SKILL_DIR/scripts/test_aseprite_export.py"
```

It tests hidden transparent RGB, partial alpha, palette alpha/order/unused colors, profiles, repeated/reordered frames, nonuniform timing, tags, both sheet routes, real layers, explicit blank frames, collisions, deterministic output, and rejection of ambiguous/unsupported inputs.

## Real application check

Check whether `aseprite` is actually installed with `command -v aseprite`, and record `aseprite --version`. Do not substitute a format decoder or a similarly named fork for an Aseprite application test. Do not install a paid application or unrecognized software for this check.

When installed and authorized, use a new directory for a batch-read check, for example:

```bash
aseprite --batch /path/export.aseprite --data /path/app-read/metadata.json --format json-array
```

Compare Aseprite's reported frame count, durations, tags, layer information where exposed, and canvas to the source. If the installed version does not support the proposed flags or cannot emit this metadata, consult its own help rather than assuming success. A nonzero exit, missing file, or incomplete metadata remains a failed/incomplete app-read check.

A batch-read test verifies the application parser, not a visual desktop-open review. For an authorized desktop-open check, open the file without saving over it, inspect the layer/timeline panes and representative frames, and record what was actually observed. Do not operate a shared desktop concurrently. Real layers should appear as the supplied layers, and duplicate frames/holds should remain in the timeline.

The export report deliberately starts with `app_open_verified: false`. Do not overwrite it merely because structural decoding passed. Record an actual application result separately with command/version or screenshot evidence. If Aseprite is absent, deliver the structurally verified file and disclose that application-open was not tested. Do not equate either packaging pass with visual-art approval.
