---
name: reference_config_driven_architecture
description: The config→assets→bootstrap→dispatcher model — one shared-config object, stdlib-only fail-open, the hook contract, and config-path resolution.
metadata:
  type: reference
---

The framework's robustness rests on three design rules:

1. **One shared-config object.** Every opinionated value (org, branch grammar, reviewer
   count, admin-merge exceptions, CI policy, shell) lives in `.claude/framework.config.json`.
   Hooks read it through `_framework_config`; none hard-codes a project choice. This lever
   turned ~77 "needs-genericisation" artifacts into config edits instead of rewrites.
2. **Stdlib only, fail-open.** No third-party deps — a freshly-cloned repo's hooks run with
   zero install. Missing/invalid config → safe defaults; a hook that raises is skipped; the
   gate never crashes the tool call.
3. **The dispatcher seam is config.** `hooks.pre_bash` / `hooks.post_bash` list active checks
   in order; enable/disable/reorder by editing config, not code.

**Hook contract:** `check(input_data) -> dict | None`.
- `None` → allow.
- `{"decision":"block","reason":...}` → dispatcher exits 2 (block). First block wins in Pre;
  Post never blocks.
- `{"decision":"allow","systemMessage":...}` → warn (advisory).

**Config-path resolution** (`_framework_config`):
- Read a value via `_framework_config.config(input_data).get("dotted.key", default)`.
- `cfg.path` == `<root>/.claude/framework.config.json`, so **repo root = `cfg.path.parent.parent`**.
- `_find_config_file` walks up checking `is_file()` on `.claude/framework.config.json`
  (so it skips a child repo's bare `.claude/` that lacks the config).

**Default `hooks.pre_bash`** (loader `_DEFAULTS` and the schema must stay in lockstep):
`block_no_verify, block_git_config, no_worktree_self_delete, warn_zsh_wordsplit,
validate_labels, validate_workflow_paths_coverage, validate_pr_ci_status,
block_squash_wave_merge`.

Related: [[reference_lifecycle_state_machine]], [[reference_per_child_union_rosters]],
[[project_upsert_status_keys_seeding]].
