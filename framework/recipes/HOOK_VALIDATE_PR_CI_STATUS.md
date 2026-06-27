# Recipe: `validate_pr_ci_status` (PreToolUse Bash)

## Purpose
Block `gh pr merge` when the PR's CI is not green, so a merge cannot land over
failing, pending, or missing checks. Reads `gh pr view --json statusCheckRollup`
and decides via a single `empty | failing | pending | ready` taxonomy.

## What it enforces
- **Failing checks** → block.
- **Pending checks** → block, unless `--auto` is passed (GitHub merges on green).
- **Empty rollup** ("no checks reported") → not the same as green. When blocking
  is enabled, it discriminates via the sibling
  `validate_workflow_paths_coverage` coverage signal: a repo with an
  every-PR workflow gets a hard block (anomalous dropped trigger); a fully
  path-filtered repo gets a warn-allow (legitimate docs-only zero-check).
- **`--admin`** → no longer an unconditional bypass. Requires
  `ADMIN_MERGE_EXCEPTION="<class>:<rationale>"` naming a configured class;
  absent/unknown → block. Authorized use is logged for audit.

## Config keys used
- `ci.merge_requires_green` (default `true`) — if `false`, `check()` returns None.
- `ci.empty_rollup_is_blocking` (default `true`) — if `false`, empty rollup is warn-allow.
- `ci.neutral_pending_check_prefixes` (default `[]`) — CheckRun name prefixes
  whose `NEUTRAL` conclusion counts as *pending* not *pass*.
- `policy.admin_merge_exceptions` (default `{}`) — map of class→rationale; empty
  means every `--admin` blocks.

## Adaptation notes
- Exports `check(input_data)->dict|None` + `main()`; wired through `dispatcher.py`.
- Shares `classify_rollup`/`classify_check` with `lib/pr_ci_state.py` (single
  source of truth — do not fork the taxonomy).
- Empty-rollup discrimination imports `validate_workflow_paths_coverage` (must
  sit in the same hooks dir). Stdlib-only; 15s gh timeouts; fails open on API error.
