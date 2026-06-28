---
name: project_framework_extraction_state
description: Where the noorinalabs→2real framework extraction stands — shipped to v0.3.1, what's built, what's deferred. Read first to pick up.
metadata:
  type: project
---

The `framework/` layer is the **product-neutral, config-driven extraction** of the
orchestration machinery from the sibling `noorinalabs-main` repo (`.claude/` +
`ontology/`). Source of candidate material: the `intake/` branch's
`GENERICISATION-BACKLOG.md` (36 net-new artifacts: 20 hooks, 7 charter files, 5 libs,
4 skills + the shared-config knob set + stack-opinionated assets §C).

**Current baseline (2026-06-28): no active work in flight.** The foundation (PR #41) shipped
long ago; the project is **released at v0.3.1** on both registries. Both Python and Node
packages publish via **OIDC trusted publishing** — no long-lived tokens (PR #57 switched the
workflows; trusted publishers are configured on PyPI and npmjs.com for
`parametrization/2real-team-framework` + the respective `publish-*.yml` workflow). v0.3.0 had
failed to publish (PyPI trusted-publisher unconfigured; `NPM_TOKEN` expired end of May 2026);
v0.3.1 (PR #58) republished cleanly via OIDC with provenance/attestations. Repo now holds
**zero** Actions secrets. Verify live state with `gh release list` / `gh pr list` before assuming.

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
- **Skill discovery fix + generic session-lifecycle skills (2026-06-27, on `main`):** this
  repo's flat `.claude/skills/<name>.md` files were converted to `<name>/SKILL.md` (Claude Code
  only discovers the dir layout). Added generic, config-driven, fail-open `session-start` +
  `handoff` skills (framework/assets/skills/ install payload + active in `.claude/skills/`).
- **Ontology system ported (2026-06-27, PR on branch `framework/ontology-system`):** the
  two-layer model genericised — `lib/ontology_gen/` structural generator + cross-repo
  aggregator with **automatic child-git-repo discovery** (`discover_repos` scans the parent's
  immediate subdirs for `.git`), `hooks/ontology_tracker.py` (config-aware, INERT unless an
  ontology dir exists), a new `hooks.post_file` PostToolUse dispatch path (Edit/Write/MultiEdit),
  and `/ontology-librarian` + `/ontology-rebuild` skills. Bootstrap now copies `lib/` recursively
  (subpackages + `__init__.py`). 47 framework tests. See `framework/recipes/ONTOLOGY_SYSTEM.md`.

**Deferred — the pickup queue** (also in `framework/README.md` § "Next"). Owner directive
2026-06-27: port the FULL orchestration suite generically — nothing is fundamentally
project-coupled, it's config-decouplable:
1. **Full wave/phase lifecycle skill chain** (genericise on the `lifecycle.py` engine):
   `phase-review` → `wave-scope` → `wave-kickoff` → `wave-wrapup` → `wave-retro`, plus
   `board-audit`. The valuable end-to-end process: theme → scope → kickoff → implement →
   wrapup → retro. Coupling to decouple via config: GitHub Projects v2 field-sync (`board.*`),
   the state-file schema (already generic in `lifecycle.py`), repo-name lists (`project.model`
   + child discovery), reviewer counts (`policy.reviewers_required`).
2. **Review-gate tranche**: port `validate_pr_review` (~1189-line N-reviewer/TechDebt gate) +
   the `pr_review_state` oracle that reuses it + `validate_review_comment_format`.
3. `validate_branch_freshness`; mid-wave reachability `gh` wrapper around
   `lifecycle.classify_reachability`.
4. **Node CLI runtime install** — node `init` subprocesses `python3` the bundled bootstrap.
5. Optional LLM persona personalities (`python/src/real_team/personas.py`).

**Architecture overview:** [[reference_config_driven_architecture]].
**Commit/PR mechanics for this repo:** [[feedback_framework_commit_pr_mechanics]].
