---
name: reference_cli_framework_bundling
description: How the published 2real-team CLI bundles + installs the framework runtime — hatch BundleSharedDataHook, runtime resolver, and `init --with-hooks` subprocessing the bundled bootstrap.
metadata:
  type: reference
---

`2real-team init` scaffolds the mustache team **and** installs the config-driven runtime by
default (`--with-hooks`, on; `--no-hooks` to skip). Single `init` → complete runnable
`.claude/` (hooks, libs, lifecycle, skill, config, dispatcher wiring), not templates alone.

**Bundling** (`python/hatch_build.py`): `BundleSharedDataHook` copies repo-root dirs
(`_DIRS = ("templates", "presets", "skills", "framework")`) into `real_team/_bundled/<name>`.
`pyproject.toml` sdist force-include also adds `"../framework" = "framework"`. Verified the
wheel actually bundles `framework/` (52 files).

**Runtime resolver** (`python/src/real_team/framework_install.py`):
```python
_PKG_DIR = Path(__file__).resolve().parent
# candidates = [_PKG_DIR/"_bundled"/"framework", _PKG_DIR.parents[2]/"framework"]
#   parents[2] = repo root from python/src/real_team (dev checkout fallback)
# returns the first whose install/bootstrap.py exists
```
`install_framework(target, ...)` subprocesses `python3 <root>/install/bootstrap.py <target>
--no-team --shell ... [--owner ...] [--reviewers ...] [--merge-model ...] [--dry-run]`.
`--no-team` because the CLI already wrote the roster. This bridges the CLI's template layer to
the asset model **without duplicating install logic**.

**cli.py `init` options:** `--with-hooks/--no-hooks` (explicit names — Typer otherwise
generates `--no-with-hooks`), `--owner`, `--merge-model`. After `bootstrap_project` it calls
`install_framework(...)` with status reporting + graceful degradation (returns `None` if the
framework root isn't found). Adds final step "Review .claude/framework.config.json + restart
Claude Code so hooks load."

Gotchas hit: ruff line-length=100 in `python/` (split long `console.print` lines); `%` in an
argparse help string trips Python 3.14 ("badly formed help string") — use `pct` not `%`.

State: [[project_framework_extraction_state]].
