# Project Memory — 2real-team-framework

One line per memory; topic files in `.claude/memory/*.md` are read on demand. Recording a
memory: create/edit `<kebab-slug>.md` with frontmatter (`name`, `description`, `metadata.type`),
add a pointer line here, link related memories with `[[slug]]`, and commit it so it travels with
the branch. Update an existing file rather than duplicating; delete memories that turn out wrong.

- [Framework extraction state](project_framework_extraction_state.md) — baseline: released v0.8.1 (Phase 6 W4 "trust the promotion pipeline": dogfooded #102-P0 in anger — caught+fixed an AUTO fenced-code false-positive, settled ledger policy #187 with bootstrap.ensure_gitignore_entries; closed charter-tree dual-deploy hole via charter_drift.py --check gate #189 which caught 4 live drifts; both W3-retro proposals applied; 2 PRs/0 CR/645 tests; all trust delta 0), OIDC on both registries; deferred: #102 **P2 tranche** (next candidate, now on a dogfooded pipeline), installer-completeness #162/#142/#148/#141/#155, #110, review-gate tranche, 2 tech-debt fold-ins. Read first.
- [Config-driven architecture](reference_config_driven_architecture.md) — config→assets→bootstrap→dispatcher; one shared-config object, stdlib-only fail-open, hook contract, `cfg.path.parent.parent` = repo root.
- [Lifecycle state machine](reference_lifecycle_state_machine.md) — lifecycle.py: monotonic wave allocator, merge models, classify_reachability, transitions + CLI.
- [Per-child union rosters](reference_per_child_union_rosters.md) — roster_gen partition (meta=org roles, child=lead+domain engineers); identity gate enforces meta∪child via parent-merge.
- [CLI framework bundling](reference_cli_framework_bundling.md) — hatch BundleSharedDataHook → `real_team/_bundled/framework`; `init --with-hooks` subprocesses the bundled bootstrap `--no-team`.
- [upsert_status_keys seeding](project_upsert_status_keys_seeding.md) — can't seed empty `{}`; first write must be seeded directly in compact multi-line shape (lifecycle `_initial_text`).
- [Commit/PR mechanics](feedback_framework_commit_pr_mechanics.md) — owner identity via `-c`, msgs via `-F file`, title via `gh api PATCH` (projects-classic), push unpiped; CI runs `ruff check` only.
- [Session handoff](handoff.md) — latest pickup point; read first at session start.
