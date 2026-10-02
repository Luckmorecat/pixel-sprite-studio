# Runtime and portability

This skill is self-contained. Resolve its installed directory and use its bundled `scripts/`, `references/` and `assets/`; no sibling skill, private catalog, image-generation tool, or Aseprite installation is required for structural export.

Use Python 3.10+ and Pillow. Create a virtual environment and install this skill's `requirements.txt` only with appropriate authorization. Example from the resolved skill directory:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

On native Windows use `py -m venv .venv` and `.venv\Scripts\Activate.ps1` in PowerShell, then `python -m pip install -r requirements.txt`. Cross-platform execution is intended; the current automated validation is Linux only.

Run outputs in a separate project directory. A real application-open check is optional and separately reported; structural decoding does not prove the desktop Aseprite application opened the result. No software or credentials are bundled or installed automatically. The skill remains explicit-request-only even in hosts that ignore `agents/openai.yaml` metadata.
