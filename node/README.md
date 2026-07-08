# 2real-team-framework

A drop-in AI agent team framework for [Claude Code](https://claude.ai/code)
projects. Bootstrap a simulated team of specialized agents with persistent
identities, trust matrices, feedback loops, and structured workflows.

This is the **Node.js CLI** for the framework. The same package is also
published on PyPI (`pip install 2real-team-framework`); both CLIs share the
same templates, presets, and framework runtime, and expose the same `init`
contract. Full documentation lives in the
[GitHub repository README](https://github.com/parametrization/2real-team-framework#readme).

## Install

```bash
npm install -g 2real-team-framework

# Or use without installing
npx 2real-team-framework init --preset library
```

## Quick start

```bash
# Interactive bootstrap in the current directory
2real-team init

# Fully specified, zero prompts
2real-team init --preset fullstack-monorepo --team-size 10 \
  --project-name my-app --non-interactive

# Driven by a unified YAML install config (shared with the framework's own
# installer; CLI flags win over the YAML)
2real-team init --config install.yaml --non-interactive
```

`init` scaffolds the team layer (charter, roster cards, trust matrix, feedback
log, skills, root `CLAUDE.md`) and — by default — also installs the
config-driven **framework runtime** (hooks, libs, lifecycle state machine,
`framework.config.json`, `settings.json` wiring) by bridging to the bundled
Python bootstrapper (`framework/install/bootstrap.py`).

### `init` options

| Flag | Meaning |
| --- | --- |
| `--preset <name>` | `fullstack-monorepo`, `data-pipeline`, or `library` |
| `--team-size <n>` | Override the preset's default headcount |
| `--config <yaml>` | Unified install config **or** legacy flat team config (auto-detected) |
| `--non-interactive` | Guarantee zero prompts; flags > YAML > defaults answer everything |
| `--with-hooks` / `--no-hooks` | Install the framework runtime (default: on) |
| `--owner <owner>` | GitHub org/user recorded as `scm.owner` |
| `--merge-model <m>` | `wave-branch` or `direct-to-main` |
| `--with-ontology` / `--no-ontology` | Seed the ontology layer; unset defers to the install config |

### Python runtime requirement

The framework runtime installer is Python; the bridge looks for `python3`
(falling back to `python`) on PATH. If no interpreter is found, `init` still
completes the team scaffolding and prints what was skipped and how to finish —
install [Python 3](https://www.python.org/downloads/) and re-run
`2real-team init --with-hooks`, or use the PyPI package instead.

## Other commands

```bash
2real-team status              # Show team composition
2real-team validate            # Verify charter/roster/skills consistency
2real-team add-member --role "Software Engineer"
2real-team remove-member "Ada Park"
2real-team update-member "Ada Park" --level Staff
2real-team randomize-member "Ada Park"
```

### Teardown

Both commands bridge to the bundled Python (like `init`), so they share the
Python runtime requirement above. Left interactive they keep the Python side's
consent gate — they prompt on a TTY and refuse on a non-TTY rather than
mutating unattended; `--non-interactive` is the automation contract and
`--dry-run` previews without writing.

```bash
2real-team uninstall           # Remove the framework runtime; restore pre-install state
2real-team uninstall --dry-run # Preview what would be removed; write nothing
2real-team restore             # Put back originals the install displaced (not a full teardown)
```

## What's in this package

- `dist/` — the compiled CLI
- `templates/`, `presets/`, `skills/` — shared scaffolding data
- `framework/` — the config-driven runtime (installer + assets + config +
  recipes; tests are excluded from the tarball)

## License

Apache-2.0
