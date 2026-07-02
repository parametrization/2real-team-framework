---
name: project_framework_extraction_state
description: Where the noorinalabs→2real framework extraction stands — shipped to v0.4.0, what's built, what's deferred. Read first to pick up.
metadata:
  type: project
---

The `framework/` layer is the **product-neutral, config-driven extraction** of the
orchestration machinery from the sibling `noorinalabs-main` repo (`.claude/` +
`ontology/`). Source of candidate material: the `intake/` branch's
`GENERICISATION-BACKLOG.md` (36 net-new artifacts: 20 hooks, 7 charter files, 5 libs,
4 skills + the shared-config knob set + stack-opinionated assets §C).

**Current baseline (2026-07-02): no active work in flight.** The foundation (PR #41) shipped
long ago; the project is **released at v0.4.0** on both registries (Phase 3 installer
overhaul — see below). Both Python and Node
packages publish via **OIDC trusted publishing** — no long-lived tokens (PR #57 switched the
workflows; trusted publishers are configured on PyPI and npmjs.com for
`parametrization/2real-team-framework` + the respective `publish-*.yml` workflow). v0.3.0 had
failed to publish (PyPI trusted-publisher unconfigured; `NPM_TOKEN` expired end of May 2026);
v0.3.1 (PR #58) republished cleanly via OIDC with provenance/attestations. v0.3.2 (PR #59) is a
docs release: the README Skills section now documents all 11 skills (6 team-workflow + 5
runtime) so the PyPI/npm long-description metadata — baked per release — covers the runtime
skills installed by `--with-hooks`. Repo holds **zero** Actions secrets. Verify live state with
`gh release list` / `gh pr list` before assuming.

**v0.4.0 (2026-07-02, Phase 3 = PRs #64–#97, released from main @ `6605da8`):** the installer
overhaul. Unified `install.config.yaml` (v1 schema, stdlib `miniyaml`, precedence flags > user
YAML > shipped defaults at `framework/config/install.config.default.yaml`, resolved snapshot
written to `.claude/install.config.json`) + `--non-interactive`; meta/child install modes
(children get parent-relative hook paths, product vs infra flavor; one ontology at the meta
root with cross-repo aggregation — children get none); ontology generated at install; pre-push
installer (`noop` default); `.claude/`-scoped permissions allowlist merged into settings;
7-file modular charter template with `{{key}}` context substitution; Node CLI bridges to the
bundled Python bootstrap (prepack copies `framework/` into the npm package); Agent/Stop events
route through the dispatchers; skills 5→13. CI runs on PRs to `deployments/**` too. Also ships
the previously unreleased CLAUDE.md-at-root behavior (#60/#61). Release tag convention: `v0.x.y`
— both publish workflows fire on ANY published release, so exactly one release per version.

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
1. ~~Full wave/phase lifecycle skill chain~~ — **largely shipped in v0.4.0** (Phase 3 Wave 2
   ported/enriched: phase-review, wave-audit, wave-retro, team-reset, plan-phase, retro,
   wave-start, close-stale-issues → 13 skills total). Remaining coupling to revisit: GitHub
   Projects v2 field-sync (`board.*`), reviewer counts (`policy.reviewers_required`).
2. **Review-gate tranche**: port `validate_pr_review` (~1189-line N-reviewer/TechDebt gate) +
   the `pr_review_state` oracle that reuses it + `validate_review_comment_format`.
   (Explicitly deferred again by user during Phase 3 planning.)
3. `validate_branch_freshness`; mid-wave reachability `gh` wrapper around
   `lifecycle.classify_reachability`.
4. ~~Node CLI runtime install~~ — **shipped in v0.4.0** (#70): node CLI bundles `framework/`
   and subprocesses the Python bootstrap (`node/src/framework-install.ts`).
5. Optional LLM persona personalities (`python/src/real_team/personas.py`).
6. Open tech-debt issues from Phase 3: #74, #75, #77, #82, #90, #94.

**Architecture overview:** [[reference_config_driven_architecture]].
**Commit/PR mechanics for this repo:** [[feedback_framework_commit_pr_mechanics]].
