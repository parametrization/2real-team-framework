---
name: project_framework_extraction_state
description: Where the noorinalabs→2real framework extraction stands — PR #41, what's built, what's deferred. Read first to pick up.
metadata:
  type: project
---

The `framework/` layer is the **product-neutral, config-driven extraction** of the
orchestration machinery from the sibling `noorinalabs-main` repo (`.claude/` +
`ontology/`). Source of candidate material: the `intake/` branch's
`GENERICISATION-BACKLOG.md` (36 net-new artifacts: 20 hooks, 7 charter files, 5 libs,
4 skills + the shared-config knob set + stack-opinionated assets §C).

**Active work:** PR #41, branch `framework/foundation-config-hooks-bootstrap`
(GitHub `parametrization/2real-team-framework`, default branch `main`). OPEN, CI green
across all jobs (python 3.10–3.13 + framework 3.10–3.13 + node 18/20/22) as of last push
`9e09628`. Verify live state with `gh pr view 41` before assuming.

**Built + tested end-to-end** (framework tests 39 passing, python tests 103 passing):
- The config keystone (`framework/config/framework.config.schema.json`) + loader/logger/parsers.
- Both dispatchers (PreToolUse/PostToolUse) reading `hooks.pre_bash`/`hooks.post_bash`.
- 10 hooks: 4 safety (no_verify, git_config, worktree_self_delete, zsh_wordsplit) + 2 SCM
  (validate_labels, warn_pipe_mask_rc) + 3 CI (validate_pr_ci_status,
  validate_workflow_paths_coverage, block_squash_wave_merge) + 1 identity (validate_commit_identity).
- 4 libs: pr_ci_state (CI oracle), upsert_status_keys, trust_signals, lifecycle.
  See [[reference_lifecycle_state_machine]] and [[project_upsert_status_keys_seeding]].
- The deterministic bootstrapper + repo-introspecting roster generator with per-child
  union rosters (see [[reference_per_child_union_rosters]]).
- The `wave-lifecycle` orchestration skill.
- CLI wiring: `2real-team init` installs the runtime by default (see [[reference_cli_framework_bundling]]).

**Deferred — the pickup queue** (also in `framework/README.md` § "Next"):
1. **Review-gate tranche** (biggest remaining primitive): port `validate_pr_review`
   (the ~1189-line N-reviewer/TechDebt gate) + the `pr_review_state` oracle that reuses it
   + `validate_review_comment_format`. Scoped honestly as deferred rather than half-ported.
2. `validate_branch_freshness`.
3. A mid-wave reachability `gh` wrapper around `lifecycle.classify_reachability`.
4. **Node CLI runtime install** — the node `init` would subprocess `python3` the same
   bundled bootstrap (runtime is Python-only).
5. Optional LLM persona personalities (wire in `python/src/real_team/personas.py`).

**Architecture overview:** [[reference_config_driven_architecture]].
**Commit/PR mechanics for this repo:** [[feedback_framework_commit_pr_mechanics]].
