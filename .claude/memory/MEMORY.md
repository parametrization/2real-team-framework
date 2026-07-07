# Project Memory — 2real-team-framework

One line per memory; topic files in `.claude/memory/*.md` are read on demand. Recording a
memory: create/edit `<kebab-slug>.md` with frontmatter (`name`, `description`, `metadata.type`),
add a pointer line here, link related memories with `[[slug]]`, and commit it so it travels with
the branch. Update an existing file rather than duplicating; delete memories that turn out wrong.

- [Framework extraction state](project_framework_extraction_state.md) — baseline: released v0.10.1 (Phase 6 W9 "fix the gate & scorer": S1 #229 trust scorer credits resolved catches from comment edit-history [closes the W13 amend-in-place erasure] + difficulty weight [#233]; S2 #230 CI-green merge precondition — block a pending/`--auto` merge when base has no branch-protection enforcement + node quarantine [#235, premise corrected by Tariq's investigation]; S3 #231 documented amend-in-place + rollup escape-hatch charter steps + wave-end review-load [#232]; 3 PRs/0 CR/~797 tests, file-disjoint; first run of the new edit-history+difficulty scorer; Tariq 5→5 [standout S2 root-cause], Nia 4→4 [flagship S1, 5-ready], Ibrahim/Paloma 4→4; **⚠️ 2 orchestration incidents [reused-agent-name worktree collision; merged S1 w/ a red-flake CI check] — both recovered; CI-green hook now LIVE on main**), OIDC both registries; deferred: installer-hardening #162/#155, #234 node RNG, rulesets branch-protection probe, more #102 P2, #110. Read first.
- [Config-driven architecture](reference_config_driven_architecture.md) — config→assets→bootstrap→dispatcher; one shared-config object, stdlib-only fail-open, hook contract, `cfg.path.parent.parent` = repo root.
- [Lifecycle state machine](reference_lifecycle_state_machine.md) — lifecycle.py: monotonic wave allocator, merge models, classify_reachability, transitions + CLI.
- [Per-child union rosters](reference_per_child_union_rosters.md) — roster_gen partition (meta=org roles, child=lead+domain engineers); identity gate enforces meta∪child via parent-merge.
- [CLI framework bundling](reference_cli_framework_bundling.md) — hatch BundleSharedDataHook → `real_team/_bundled/framework`; `init --with-hooks` subprocesses the bundled bootstrap `--no-team`.
- [upsert_status_keys seeding](project_upsert_status_keys_seeding.md) — can't seed empty `{}`; first write must be seeded directly in compact multi-line shape (lifecycle `_initial_text`).
- [Commit/PR mechanics](feedback_framework_commit_pr_mechanics.md) — owner identity via `-c`, msgs via `-F file`, title via `gh api PATCH` (projects-classic), push unpiped; CI runs `ruff check` only.
- [Session handoff](handoff.md) — latest pickup point; read first at session start.
