# Contributing to 2real-team-framework

## Development Setup

### Python

```bash
cd python
pip install -e ".[dev]"
```

### Node

```bash
cd node
npm install
```

## Running Tests

```bash
# Python (97+ tests)
cd python && pytest tests/

# Node (83+ tests)
cd node && npm test

# Framework runtime tests (stdlib-only hooks/libs/installer)
python3 -m pytest framework/tests/ -q
```

### Install / test / teardown quality harness

Beyond the unit tests, the installer surface has a dedicated install → assert → teardown
harness that runs the **real** installers (`framework/install/bootstrap.py` and the
`2real-team init` bridge) against synthesized repo-type fixtures, measures per-metric pass
rates, and proves teardown leaves **zero residue**:

```bash
# Fast CI smoke — a subset (B1,B2,B4,B8b) through bootstrap only:
python3 -m framework.harness --quick

# Full hermetic matrix (default buckets B1-B9 + B12), gated against the prior run:
python3 -m framework.harness --compare

# Opt into the [real] B10/B11 buckets (see below):
python3 -m framework.harness --include-real
```

It emits per-bucket / per-category pass rates plus `install_success_rate` and
`reinstall_parity_clean`, writes a machine-readable run envelope JSON under
`framework/tests/install_quality/runs/`, and **exits non-zero** on any failed graded metric (or
a `REGRESSION` verdict under `--compare`), so CI can gate on it.

Key flags:

| Flag | Effect |
|------|--------|
| `--quick` | Fast subset (`B1,B2,B4,B8b`) through the bootstrap installer only — CI smoke |
| `--compare` | Diff against the newest prior run in `--out` and gate on the run-over-run verdict |
| `--include-real` | Opt in to the `[real]` B10/B11 buckets (owner-gated; **OFF by default**) |
| `--real-config PATH` | Sidecar JSON overriding the B10/B11 real-fixture source/pin registry |
| `--buckets IDS` | Comma-separated bucket ids to run (default: hermetic B1-B9 + B12) |
| `--installers LIST` | Which installers to exercise (`bootstrap,cli`; default both) |
| `--scale N` | B9 synthesized file count (default 300) |
| `--no-dogfood` | Skip the B12 `reinstall --check` leg |
| `--json` | Print the full machine JSON to stdout (standalone — works with or without `--compare`) |

**Real-repo mode (`--include-real`, Phase 6).** B10 (`meta-real-world`) and B11
(`standalone-real-world`) run the harness against **real checkouts** instead of synthesized
fixtures. They are defined but **flag-gated OFF** — `--include-real` opts in. The provisioner
(`framework/harness/real_provision.py`) is read-only w.r.t. the source: it `git clone
--no-local`s the source at a **pinned SHA** (resolved via `git ls-remote`, or an explicit pin)
into a scratch dir, and fingerprints the source `HEAD` + `git status --porcelain` before and
after to assert the live tree is untouched. Which source/pin each bucket uses is DATA (a
`RealFixtureSpec` registry) overridable via the `--real-config` sidecar, so the mechanism is
proven hermetically against a throwaway git repo — the large real runs
(`noorinalabs`/`botfarm`, #101/#109) are never cloned in CI.

### Install-completeness & parity guards

The harness relies on two standalone drift guards you can also run directly:

```bash
# Golden install manifest — verify the expected-install-set snapshot is in sync (exit 1 on drift):
python3 framework/install/manifest.py --check

# Reinstall parity — report canonical → live .claude/** drift, write nothing (exit 1 on drift):
python3 framework/install/reinstall.py --check
```

`manifest.py` derives the *exact* `.claude/**` set a correct install produces from
`framework/assets/**` + the resolved config (never a hand-listed literal), so the harness's
completeness checks cannot disagree with what the installer copies. `reinstall.py` enforces the
#116 dual-deploy rule — that this repo's live `.claude/**` copy of byte-mirrored assets stays in
sync with canonical `framework/assets/**`. See `framework/README.md` for the full contract.

## Linting

```bash
# Python
cd python && ruff check src/ tests/

# Node
cd node && npm run lint
```

## Type Checking

```bash
# Python
cd python && mypy src/

# Node
cd node && npx tsc --noEmit
```

## Project Structure

```
2real-team-framework/
  templates/     # Shared Mustache templates (both CLIs read these)
  presets/       # JSON preset definitions (team shapes)
  skills/        # Skill template files
  examples/      # Example YAML config files
  framework/     # Config-driven runtime + installer (stdlib-only; see framework/README.md)
    assets/        # What the bootstrapper installs into <repo>/.claude/ (hooks, lib, skills)
    config/        # framework.config schema + install.config default
    install/       # The installer: bootstrap.py, roster_gen.py, install_config, miniyaml,
                   #   manifest.py (golden manifest), user_space/consent/backup/repo_space
                   #   (consented user + repo install), atomic_io, reinstall.py (#116 parity)
    harness/       # Install/test/teardown quality harness (python3 -m framework.harness)
    tests/         # Framework runtime tests (python3 -m pytest framework/tests/)
  python/        # Python CLI (typer, pydantic, chevron)
    src/real_team/
      cli.py         # CLI commands
      bootstrap.py   # Core bootstrap logic
      models.py      # Pydantic models
      personas.py    # AI persona generation
      presets.py     # Preset loading
      templates.py   # Template rendering
    tests/
  node/          # Node CLI (commander, mustache)
    src/
      index.ts       # CLI entry point
      bootstrap.ts   # Core bootstrap logic
      personas.ts    # AI persona generation
      presets.ts     # Preset loading
      templates.ts   # Template rendering
    tests/
```

## Adding a New Preset

1. Create `presets/<name>.json` with the preset schema:

```json
{
  "name": "my-preset",
  "description": "Description of the team shape",
  "default_team_size": 5,
  "roles": [
    {"role": "Manager", "level": "Senior VP", "count": 1, "required": true},
    {"role": "Engineer", "level": "Senior", "count": 2, "required": false}
  ],
  "skills": ["retro", "wave-start", "wave-end", "review-pr", "plan-phase", "close-stale-issues"],
  "default_ci": "github-actions"
}
```

2. Add tests in both `python/tests/test_cli.py` and `node/tests/cli.test.ts`.

## Adding a New Template

1. Create `templates/<name>.md.mustache` using Mustache syntax.
2. Available variables: `{{project_name}}`, `{{#team_members}}...{{/team_members}}`.
3. Each team member has: `{{name}}`, `{{role}}`, `{{level}}`, `{{email}}`, `{{personality}}`, `{{agent_name}}`, `{{reports_to}}`.

## Adding a New Skill

1. Create `skills/<name>.md.mustache` with the skill template.
2. Add the skill name to the relevant preset's `skills` array.
3. The skill file will be rendered and installed to `.claude/skills/<name>.md`.

## PR Process

1. Fork the repository
2. Create a feature branch from `main`
3. Make changes in **both** Python and Node implementations
4. Run tests and linting for both
5. Submit a PR with a clear description

## Code Conventions

- **Python**: ruff for linting/formatting, mypy strict mode, pydantic models
- **Node**: TypeScript strict, eslint, vitest for testing
- **Templates**: Mustache (logic-less, works in both ecosystems)
- **All changes need tests in BOTH Python and Node**
