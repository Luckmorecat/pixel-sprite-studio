# Validation of portable packaging

Validated on Linux with Python 3.12.14, ImageMagick 7.1.1-43, Pillow 12.3.0, Node.js 24.19.0 and the npm `skills` CLI 1.7.0.

- `skills add ./pixel-art-skills-repo --list` discovered all six expected skill names
- Actual project-scoped `--copy` installs in separate temporary sandboxes succeeded for all six skills and for `export-to-aseprite` alone; every installed file matched the repository byte-for-byte, including scripts, references, assets and requirements
- Installed exporter and animation copies also passed their 42- and 157-test suites respectively
- The exporter-only install contained exactly one skill; the full install contained exactly six. Existing/global skill installations were not changed
- Five independent core packages each ran 157 synthetic tests successfully
- Standalone Aseprite exporter ran 42 synthetic tests successfully
- Total: 827 test executions, with no failures or skipped tests in this environment; the core suites intentionally repeat identical shared-helper tests to validate independent packages
- Core helper source files are byte-identical across the five packages and unchanged from the frozen 4.1.0 source; exporter Python files are unchanged from its standalone source
- All JSON templates parse; skill frontmatter names match directories; no private/environment-specific source locators or symlink dependencies were included

These results cover discovery, packaging and deterministic helper behavior. They do not certify generated-art quality, cross-agent integration, native Windows execution, macOS/WSL execution, or an Aseprite desktop application-open check. No image-generation calls were made. No existing installed skill was modified.

Run `python3 scripts/validate.py` to repeat local checks. Missing ImageMagick may cause tests to skip, so inspect the actual summaries. Dependency installs and model access are separate from skill installation.
