# Working notes for Claude

## Release checklist — version and metadata consistency

The version is single-sourced from `officeclaw.__version__`, but several files
*restate* it or the Python floor in prose. Those copies drift silently, and one
of them is acted on by machines: 1.1.0 shipped a skill manifest still claiming
`version: "1.0.4"` and `Requires Python 3.9+`, which would let an OpenClaw host
install the skill into a 3.9 environment where it cannot run. 1.1.1 exists only
to correct that.

Before tagging any release, confirm every one of these agrees:

- [ ] `src/officeclaw/__init__.py` — `__version__` (the single source; the wheel
      and sdist metadata derive from it via `[tool.hatch.version]`)
- [ ] `skill/SKILL.md` frontmatter — `metadata.version` **and** the
      `compatibility:` line's Python floor
- [ ] `skill/SKILL.md` Installation section — the minimum version it tells
      agents to install (it documents the version it ships with, so the pin
      equals `__version__`), the `expect X or newer` line, and the feature list
      justifying it
- [ ] `skill/SKILL.md` command coverage — every CLI command must appear, or an
      agent will not know it exists
- [ ] `CHANGELOG.md` — a `## [x.y.z]` heading with today's date
- [ ] `pyproject.toml` — `requires-python` and the `Programming Language ::
      Python ::` classifiers
- [ ] `README.md` — the "Requires Python …" line
- [ ] `docs/ARCHITECTURE.md` — its `requires-python` snippet and CI matrix list
- [ ] `.github/workflows/test.yml` — the `python-version:` matrix
- [ ] The git tag: `vX.Y.Z` must equal `__version__` (the publish workflow
      fails the build if not, but check before pushing a tag — tags are
      annoying to retract and PyPI versions cannot be reused)

`tests/test_version_consistency.py` enforces the machine-checkable half of this
— including that every command in the CLI tree appears in SKILL.md —
so a drifted manifest fails CI rather than shipping. Run it with
`uv run pytest tests/test_version_consistency.py -v`.

### Things that ship where you might not expect

- The **sdist includes `skill/`**; the wheel does not. A skill-file fix
  therefore needs a release to reach PyPI consumers, but reaches OpenClaw
  installs (which symlink a git checkout) as soon as it is merged.
- The **OpenClaw skill install is a symlink** to a contributor's own checkout,
  not a copy: `~/dev/workspace/skills/officeclaw -> /home/poe/dev/officeclaw`.
  Updating "the skill" there means that user pulling the tag, not editing files
  in this repo.

## Verifying a release before tagging

```bash
uv run pytest -q                       # includes live integration tests when authenticated
uv run ruff check src/ tests/ && uv run black --check src/ tests/
uv run mypy src/officeclaw/ --ignore-missing-imports
uv run pip-audit                       # fails on any advisory in the locked tree
uv build && uv run twine check dist/*
tar -xzOf dist/officeclaw-*.tar.gz '*/skill/SKILL.md' | head -12   # manifest actually shipped
```

Install the built wheel into a clean venv on the **oldest supported Python** and
run the CLI before tagging; that catches floor and packaging problems that the
project venv hides.

## Documentation examples are executable

Command examples in `skill/SKILL.md` are read by agents and run verbatim. When
changing the CLI, re-validate them — a stale `--query` flag in this file is a
command that simply fails for the agent. The check is mechanical: extract every
`officeclaw …` line and confirm the command and its flags appear in `--help`.
