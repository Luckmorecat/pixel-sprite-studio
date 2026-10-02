# Authoring and package generation

Edit `authoring/core/` for shared scripts, references and templates. Edit `authoring/skills/<name>/` for unique entrypoints, agent UI metadata, icons and skill-specific assets; the exporter keeps its independent implementation there. `SKILL.md.in` is source text, not another installable skill. Only `skills/` contains discoverable packages.

Run `python3 scripts/build_packages.py`, then `python3 scripts/validate.py`. Commit canonical sources and generated packages together. Build is deterministic and offline; copied installations need no build step or sibling directory. `--check` compares the complete generated inventory and every byte, including references, templates, UI metadata and package-specific files. The separate validator also checks shared scripts/references/templates across five core packages; icons and the action-specific example profile intentionally differ.

Do not modify generated files directly. Do not add run records, prompts, user images or trial outputs to this repository. For isolated artistic tests read `evaluation.md`; synthetic helper passes are not artistic validation.
