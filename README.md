# Pixel Sprite Studio

Six agent skills for pixel-first character design, consistent views, action staging, native-grid refinement, animation, and explicit Aseprite export.

## Install

Requires Node.js/npm, Git, and an agent supported by [Vercel's skills CLI](https://github.com/vercel-labs/skills). Repository: [Luckmorecat/pixel-sprite-studio](https://github.com/Luckmorecat/pixel-sprite-studio).

```sh
# Discover without installing
npx skills add Luckmorecat/pixel-sprite-studio --list

# Install the six skills; select your agent interactively
npx skills add Luckmorecat/pixel-sprite-studio --skill '*' --copy

# Install one skill globally for Codex
npx skills add Luckmorecat/pixel-sprite-studio --skill export-to-aseprite --copy --global --agent codex

# Install all six globally for Codex
npx skills add Luckmorecat/pixel-sprite-studio --skill '*' --copy --global --agent codex

# Review/install from a local checkout
npx skills add ./pixel-sprite-studio --list
```

The examples use `--copy` because the ledger intentionally rejects symlink skill roots/evidence paths. If you choose a symlink install, resolve the actual canonical directory before snapshotting; do not relax the safety check. Omit `--global` for project scope. Use the CLI's supported agent identifier for another host. Private repositories require your existing authorized Git/GitHub/SSH authentication. These commands install skill files; they do not install system dependencies or grant image-model access. Do not use `--all` unless you mean every skill and every supported agent.

## Skills

- `character-identity`: establish an accepted neutral character identity and native-size study
- `multi-view-reference`: derive consistent requested views from an accepted identity
- `action-pose-design`: stage an accepted identity for a requested action or prop interaction
- `refine-pixel-art`: normalize and visually accept reusable native masters
- `animate-pixel-sprite`: plan/generate missing poses or assemble existing poses, preserving native assets and exact timing
- `export-to-aseprite`: package supplied PNGs, explicit sequences, sheets or genuine layers; only on an explicit export request

Typical flow: identity → optional views/action → refinement → optional animation. Export is independent and never an automatic final step. Each skill bundles its own complete helper set, so installing one does not depend on neighboring folders. Shared scripts, references and templates come from canonical `authoring/core/` sources; generated copies are validated byte-for-byte, and each installed package remains self-contained. Templates contain illustrative values; adapt them to the actual project.

## Choose the amount of workflow

A one-stage task ending in this session uses a compact standalone record: request, preserved sources, bounded attempts, separate technical/visual reviews and approval evidence. It does not require frozen skill snapshots or a portable bundle. Multi-stage and cross-session work uses the full project ledger and portable handoff. The request determines the path, not how much paperwork the agent prefers. Supplied full runs retain their original history and counters.

## Runtime requirements

The five creative/core skills require Python 3.10+, Bash, ImageMagick 7 (`magick` on PATH), and POSIX file locking. Use Linux, macOS or WSL; native Windows Python cannot run the ledger's `fcntl` locking. Legacy ImageMagick `convert` supports some packaging commands, but not the complete normalization/assembly workflow. No third-party Python packages are needed by the core helpers.

Creating or repairing art also requires an authorized image-generation/editing tool accepting reference images and returning downloadable rasters. The skills' “imagegen” terminology is a capability requirement, not a bundled API, credential, or universal tool name. No paid-provider fallback is automatic. Existing-art packaging can proceed without generation when the requested work permits it. Visual acceptance requires actual image inspection; playback claims require real playback observation.

The exporter requires Python 3.10+ and Pillow 12.x. From the resolved exporter skill directory, set up a virtual environment and install its requirements when authorized:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/aseprite_export.py --help
```

Windows PowerShell: use `py -m venv .venv`, then `.venv\Scripts\Activate.ps1`. The exporter writes the Aseprite format directly; a separately installed Aseprite app is only needed for an optional application-open check. Automated coverage currently proves Linux execution, not every OS/agent combination. Read each skill's `references/runtime.md` before use.

## Working with the helpers

Resolve the installed skill directory through your agent's skill catalog. Run scripts using that path and keep project inputs/outputs in a separate working directory. Resolve canonical real paths for ledger snapshot, run and evidence inputs; symlink parents (including common macOS `/tmp` aliases) are rejected intentionally. Each `SKILL.md` links relevant contracts and command examples. Python imports resolve within its own bundled `scripts/` directory. There is no package installation hook, API service, or npm package to publish for this repository.

Do not commit user images, generated art, private prompts, run ledgers, approval evidence, credentials, or unrelated project files here. Portable artifact bundles belong to individual projects; their recorded historical paths are not runtime dependencies.

## Validate

```sh
# From this repository root, after runtime dependencies are available
python3 scripts/validate.py
```

This checks six frontmatter names, JSON templates, bundled runtime instructions, generated-source parity across every file and shared scripts/references/templates, and executes each package's synthetic unit tests in an isolated process. Tests make no image-generation or network calls. Skipped tests are reported and are not evidence of coverage. Unit tests establish technical behavior, not artistic success or an Aseprite desktop-open check.

Core 4.2.0 adds an explicit lightweight standalone path while preserving existing full-project schemas. Compact checkpoint exports are cross-checked against their included record, and accepted replacements can explicitly supersede a recorded study without erasing history. Static single-cel handoffs use the existing refinement-stage envelope. The corrected build passes 992 helper test executions (232 unique tests) plus package parity. Independent set/key/final-animation review supplements creator checks when clean reviewers are available; ordinary single stills stay lightweight, and unavailable review is disclosed. Frozen trials demonstrate a lighter path for one already-native standalone task, not better generated-art reliability; see [validation](VALIDATION.md) for scope and limits. Exporter 1.0.2 preserves its existing encoder. See [migration](docs/MIGRATION-4.2.md), [authoring](docs/maintainers/authoring.md) and [maintainer evaluation](docs/maintainers/evaluation.md).

## License

No license has been selected. Installation examples do not grant redistribution or reuse rights beyond applicable law or permission from the rights holder. Choose a license before public distribution if broader reuse is intended.
