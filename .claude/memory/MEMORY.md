# Project Memory — 2real-team-framework

One line per memory; topic files in `.claude/memory/*.md` are read on demand. Recording a
memory: create/edit `<kebab-slug>.md` with frontmatter (`name`, `description`, `metadata.type`),
add a pointer line here, link related memories with `[[slug]]`, and commit it so it travels with
the branch. Update an existing file rather than duplicating; delete memories that turn out wrong.

- [Framework extraction state](project_framework_extraction_state.md) — baseline: released v0.10.0 (Phase 6 W8 "complete the installer": S1 #222 product `2real-team uninstall`/`--teardown` byte-provenance-guarded [#142]; S2 #223 kill ontology mtime freshness flake via regeneration barrier [#141]; S3 #224 `cli_bridge_soft_degrade` metric + `--compare` install-quality CI gate [#148]; 3 PRs/1 CR cycle/746 tests, file-disjoint stories; **first wave with a REAL blocking catch** — reviewer Tariq stopped user-data-loss on the flagship uninstall that co-reviewer Nia approved past; reserved-5 Tariq VALIDATED on the catch, Nia 4→4 w/ documented review-miss, Paloma/Ibrahim 4→4; **headline: amend-in-place [required by the gate oracle] ERASES review-cycle trust signals — best review scored mechanically 0, distribution overrode by hand**), OIDC both registries; deferred: installer-hardening #162/#155, more #102 P2, #110. Read first.
- [Config-driven architecture](reference_config_driven_architecture.md) — config→assets→bootstrap→dispatcher; one shared-config object, stdlib-only fail-open, hook contract, `cfg.path.parent.parent` = repo root.
- [Lifecycle state machine](reference_lifecycle_state_machine.md) — lifecycle.py: monotonic wave allocator, merge models, classify_reachability, transitions + CLI.
- [Per-child union rosters](reference_per_child_union_rosters.md) — roster_gen partition (meta=org roles, child=lead+domain engineers); identity gate enforces meta∪child via parent-merge.
- [CLI framework bundling](reference_cli_framework_bundling.md) — hatch BundleSharedDataHook → `real_team/_bundled/framework`; `init --with-hooks` subprocesses the bundled bootstrap `--no-team`.
- [upsert_status_keys seeding](project_upsert_status_keys_seeding.md) — can't seed empty `{}`; first write must be seeded directly in compact multi-line shape (lifecycle `_initial_text`).
- [Commit/PR mechanics](feedback_framework_commit_pr_mechanics.md) — owner identity via `-c`, msgs via `-F file`, title via `gh api PATCH` (projects-classic), push unpiped; CI runs `ruff check` only.
- [Session handoff](handoff.md) — latest pickup point; read first at session start.
