# Recipe: `validate_workflow_paths_coverage` (PreToolUse Bash)

## Purpose
Block `gh pr create` / `gh pr ready` when a PR changes a file under
`.github/workflows/**` that no workflow's `on.pull_request.paths:` filter
covers — the "workflow-file orphan" class, where GitHub silently skips CI on the
workflow change and the PR can reach a `CLEAN` + empty-rollup state nobody validated.

## What it enforces
A workflow file in the PR diff must be covered by at least one BASE-branch
workflow that either:
- has `'.github/workflows/**'` (or a matching glob) in its `pull_request.paths:`, OR
- has an `on.pull_request:` trigger with NO `paths:` filter (matches everything).

If any changed workflow file is uncovered → block with remediation (add the glob
in a precursor PR, add a no-paths workflow, or confirm no CI needed + `--admin`).

## Config keys used
None. The discriminator is intrinsically generic — it queries the repo's own
base-branch workflows via `gh api` and parses their `paths:` filters. Base
defaults to `main` (override with `--base`); repo/head resolve from flags or the
invocation cwd's git remote/branch.

## Adaptation notes
- Exports `check(input_data)->dict|None` + `main()`; wired through `dispatcher.py`.
- `_build_coverage_signal(repo, base)` is reused by `validate_pr_ci_status`'s
  empty-rollup discriminator — keep both hooks in the same dir so the import resolves.
- Regex-based YAML parser (stdlib-only, no PyYAML); handles canonical block-style
  workflows. Anything unparseable → no-coverage-signal (conservative).
- Fails open on any gh/API failure or unresolvable repo/head. 15–20s timeouts.
