---
name: project_framework_extraction_state
description: Where the noorinalabs→2real framework extraction stands — shipped to v0.5.0 (Phase 5 complete: installer robustness), what's built, what's deferred. Read first to pick up.
metadata:
  type: project
---

The `framework/` layer is the **product-neutral, config-driven extraction** of the
orchestration machinery from the sibling `noorinalabs-main` repo (`.claude/` +
`ontology/`). Source of candidate material: the `intake/` branch's
`GENERICISATION-BACKLOG.md` (36 net-new artifacts: 20 hooks, 7 charter files, 5 libs,
4 skills + the shared-config knob set + stack-opinionated assets §C).

**Current baseline (2026-07-06): released v0.5.0 — Phase 5 (installer robustness) COMPLETE,
merged to main, published to PyPI + npm.** Phase 4 ("self-hosting & quality machinery", two
waves) made the framework trustworthy when run on itself. **Phase 5** ("installer robustness")
made the installer trustworthy on repos *other than this one*. See [[handoff]] for the exact
pickup (next = owner picks Wave 6 theme, reserved stub #150). The foundation (PR #41) shipped
long ago; Phase 3 installer overhaul (v0.4.0) is below.

**Phase 5 → v0.5.0 (2026-07-06, rollup PR #151 → main @ `7e6fe8b`) — installer robustness.**
Both waves rolled up as a unit (owner decision: stack W2 on W1, one release). Published via OIDC
to PyPI + npm (both `latest` = 0.5.0); lightweight tag `deployments-phase5-wave-2` for
traceability only. **8 feature PRs, 0 must-fix, 0 CR cycles, 442 tests.**
- **Wave 1 (global 4) — discovery**: **#131** scorer false-positive gate (last Phase-4 artifact —
  gate `review_false_positives` on `_has_must_fix_items`); **#106** `~/.claude` user-space audit →
  found load-bearing gap **G1** (installer never wrote the agent-teams env flag, so a fresh install
  couldn't spawn a team); **#103** test-repo taxonomy B1–B12 + ~31 metrics; **#104**
  install/test/teardown methodology. 3 design docs in `framework/recipes/`
  (`INSTALL_QUALITY_HARNESS.md`, `INSTALL_TEST_METHODOLOGY.md`, `USER_SPACE_AUDIT.md`).
- **Wave 2 (global 5) — build**: **#105** `python3 -m framework.harness` install/test/teardown
  harness (11 modules; B1–B9 + inline dogfood default; B10/B11 real fixtures opt-in behind
  `--include-real`, clone-at-pinned-SHA, never touch live repos) + **#138** record_id permutation
  discriminant; **#139** golden manifest `expected_install_set(config)` in `framework/install/manifest.py`
  (single source for install-completeness, derived from the installer's own iterators, `--check`
  drift guard, retires hardcoded counts); **#107** consented **idempotent** user-level install
  (`bootstrap.py --user-space`) — **closes G1** (check-existing no-op / backup-or-amend / never
  clobbers; reusable `consent.py`/`backup.py`/`user_space.py`); **#108** repo-level consent +
  backup/archive/**restore** (`repo_space.py` archives to sibling `.claude-backups/<UTC>/`, out of
  Claude load scope, byte-identical restore) + **#145** atomic settings write
  (`atomic_io.atomic_write_text`: temp→fsync→os.replace) across both paths.
- A latent flat-vs-nested config seam (harness passed flat permutation dicts; #139 reads nested
  dotted config) was caught in #105 review and fixed **pre-merge** via
  `permutation_to_install_config`, so `files_installed_complete` grades against the real manifest
  (activation verified post-merge, `install_success_rate 1.00`).
- Install code (`framework/install/`) and harness (`framework/harness/`) are NOT part of the
  `.claude/**` runtime → outside reinstall-parity scope. Team trust holds at **4 across the board**
  — third consecutive fully-clean score (steady state). Deferred follow-ups (all OPEN tech-debt):
  **#142** product `uninstall` · **#148** `cli_bridge_soft_degrade` + `--compare` CI gate · **#149**
  durability/fidelity hardening · **#141** pre-existing flaky meta-install idempotency test.

**Phase 4 (2026-07-05, two waves off `deployments/phase4/wave-{1,2}`):**
- **Wave 1 → v0.4.1** (#98 trust-vocab, #99 dogfood lifecycle into wave skills, #100 phase-aware
  `branch.integration`, #111 `validate_review_comment_format` gate). Dogfooding the retro surfaced
  4 defects → #116/#117/#118/#119.
- **Wave 2 → v0.4.2** (10 issues): **#116** reinstall-on-change rule + `framework/install/reinstall.py`
  + `--check` CI parity gate (byte-mirror scoped to `skills/`; hooks/lib canonical-by-reference;
  charter via `--refresh-charter`); **#117** `{wave}`→phase-local ordinal; **#118** verdict-grammar
  semantic warn tier; **#119** roster name normalization; **#77** `--refresh-charter` three-way
  charter refresh (`team/.charter-manifest.json`); **#82** copy-shared rm+recopy; **#94** merge-model
  wording + `policy.merge_model`→`wave-branch`; **#74** ontology_gen consumer-runtime exclusion;
  **#75** meta-child ontology install test; **#90** wave-audit zero-pad. 373 tests.
- **Wave 1 authoritative re-score closed** (corrected 3 mis-tagged approvals per #118); last scorer
  artifact isolated as **#131**. See `trust_matrix.md` + `feedback_log.md`. Both Python and Node
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
   the `pr_review_state` oracle that reuses it. (`validate_review_comment_format` **shipped** in
   Phase 4: #111 ported it, #118 added the semantic warn tier.) Rest still deferred.
3. `validate_branch_freshness`; mid-wave reachability `gh` wrapper around
   `lifecycle.classify_reachability`.
4. ~~Node CLI runtime install~~ — **shipped in v0.4.0** (#70): node CLI bundles `framework/`
   and subprocesses the Python bootstrap (`node/src/framework-install.ts`).
5. Optional LLM persona personalities (`python/src/real_team/personas.py`).
6. ~~Phase 3 tech-debt #74/#75/#77/#82/#90/#94~~ — **all shipped in Phase 4 Wave 2 (v0.4.2)**.
7. ~~**Phase 5 (installer robustness)**~~ — **COMPLETE, shipped in v0.5.0** (both waves: #131 scorer
   gate, #103/#104/#106 design+audit, #105 harness, #107/#108 consented user/repo install closing G1,
   #138/#139/#145 folded). Remaining Phase 5 *exploratory* backlog (deferred, OPEN): #101/#102
   (reverse-map noorinalabs against the new harness), #109 (botfarm before/after), #110 (ship the
   installer as a CC skill); plus tech-debt #142/#148/#149/#141.

**Architecture overview:** [[reference_config_driven_architecture]].
**Commit/PR mechanics for this repo:** [[feedback_framework_commit_pr_mechanics]].
