---
name: export-to-aseprite
description: Package existing PNG artwork into an Aseprite file only when the user explicitly requests Aseprite export. Support a still PNG, an ordered PNG sequence with timing, a sprite sheet with explicit layout and timing, or genuinely separate source-layer PNGs. Preserve exact pixels, alpha, supplied palette, timing, layers and tags without generating or editing art. Independent of character-design, refinement and animation skills; never run as an automatic finishing step.
---

# Export to Aseprite

Read `references/runtime.md` before using tools or scripts; installation does not supply the required execution capabilities.

Package supplied artwork. Do not draw, regenerate, clean up, recolor, resample, infer hidden layers, or modify sources. Treat export as a separate explicitly requested task, including its own verification and deliverable. A request for animation, a sprite sheet, or pixel art alone does not authorize this export.

## Choose the input route

- **One still PNG:** Export one frame immediately. The format's default 100 ms field is serialization metadata for that still, not inferred animation timing. Preserve an explicitly supplied duration instead.
- **PNG sequence:** Obtain the exact ordered timeline and millisecond duration of every entry. Repeat entries remain separate frames. Never deduplicate holds, sort filenames into a presumed timeline, or infer animation timing.
- **Sprite sheet:** Obtain frame dimensions and grid layout (including margins/spacing), or explicit equal-size rectangles, plus ordered cell/rectangle entries and durations. Ask about missing layout/timing. Do not segment art heuristically.
- **Real source layers:** Use separately supplied layer PNGs plus canvas, bottom-to-top layer order, cel/frame assignments, offsets and source metadata. Preserve supported normal-blend layer visibility, editability, opacity, and cel opacity. Never claim editable body/face/prop layers can be recovered from one flattened PNG.
- **Other native source formats:** This tool does not import PSD, ORA, layered Aseprite, GIF, APNG or tilemaps. Ask for supported source PNGs/metadata, or offer a separately authorized native-app route. Do not flatten or silently discard unsupported features.

Use [references/input-contract.md](references/input-contract.md) for exact schemas, limitations, and all optional metadata. Copy the relevant template from `assets/`, then replace its example values with actual supplied information. Translate an existing timeline only when its order, timing, cel sources and tags are unambiguous; preserve the original and record the translation.

## Export and verify

Requirements: Python 3.10+ and Pillow. Inspect availability first; don't install an Aseprite application just to export. Use the bundled deterministic writer, which produces RGBA Aseprite files, as below (`SKILL_DIR` is this skill's resolved directory):

```bash
python "$SKILL_DIR/scripts/aseprite_export.py" static /path/art.png /path/art.aseprite --report /path/art-export.json
python "$SKILL_DIR/scripts/aseprite_export.py" manifest /path/export.json /path/animation.aseprite --report /path/animation-export.json
python "$SKILL_DIR/scripts/aseprite_export.py" inspect /path/animation.aseprite --manifest /path/export.json
```

Use new output/report paths. The tool refuses existing paths and source collisions. It only extracts explicitly specified sheet rectangles; it never changes any decoded pixel. It writes one genuine source layer for flattened input, with an honest default name, and does not manufacture semantic layers.

Before reporting success:
1. Inspect the resulting report: decoded source pixels, canvas, frame count, every duration, palette, layer metadata, offsets, and tags must match. The exporter decodes its output and compares them before writing it.
2. Confirm source files remain unchanged. Preserve the source hashes, manifest, report, and output file hash with the deliverable.
3. Run a real Aseprite application-open check when the application is actually available and authorized. Record its version and outcome separately. See [references/verification.md](references/verification.md). A structural decoder pass is not proof that the desktop application opened it.
4. If something fails, retain failure evidence, fix only the demonstrated packaging defect within scope, then rerun verification. Do not repair the art to make export pass.

## Fidelity and honest delivery

Deliver the `.aseprite`, compact export report, and translated manifest when one was needed. State frame/layer count and whether application-open was verified. Do not imply visual/art-quality approval from a packaging test.

- Preserve exact decoded RGBA bytes, including RGB under zero alpha and partial alpha. RGB/grayscale/indexed PNGs are represented as RGBA cels without quantization.
- Preserve an indexed PNG's complete palette entries/order/alpha as an Aseprite palette chunk. Source index encoding becomes RGBA; this is not an indexed-mode export. Reject conflicting source palettes or color profiles rather than invent a conversion.
- Preserve shared sRGB/ICC color profiles. For cHRM-only PNGs, retain raw chromaticity in the report and disclose that Aseprite remains untagged; do not invent sRGB or claim color-managed appearance equivalence. Reject unsupported 16-bit/HDR or standalone gamma metadata; ask for an appropriate source or separately approved metadata/conversion work.
- Copy no PNG ancillary metadata other than supported palette/color profiles. Don't call this a byte-identical PNG archive.
- Preserve explicit tags and their ranges, directions and repeat fields. Do not add a tag the user did not supply. Tag directions do not reorder the underlying timeline.
- Keep animation durations as positive integer milliseconds in Aseprite's 1–65535 range. Ask about unrepresentable timing; do not round, split, clamp or retime it silently.
