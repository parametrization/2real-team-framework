# Project Memory — 2real-team-framework

One line per memory; topic files in `.claude/memory/*.md` are read on demand. Recording a
memory: create/edit `<kebab-slug>.md` with frontmatter (`name`, `description`, `metadata.type`),
add a pointer line here, link related memories with `[[slug]]`, and commit it so it travels with
the branch. Update an existing file rather than duplicating; delete memories that turn out wrong.

- [Framework extraction state](project_framework_extraction_state.md) — baseline: released v0.9.1 (Phase 6 W6 "activate the review gate": ARMED the PR-review gate on THIS repo — `.claude/framework.config.json` now `reviewers_required=2` + `pr_review_gate_enabled=true`, so every PR needs 2 distinct clean reviewer verdicts to merge; framework DEFAULTS stay dormant for adopters; escape hatch = direct config commit to main; S1 #202 armed+proved live, S3 #204 folded W5 proposals into charter + N=2 rule (Nia sole charter integration-owner), S2 #203 mutation-proved N=2 across trust/lifecycle; 3 PRs/0 CR/706 tests, first 2-reviewer wave; all implementers delta 0, Nia holds 5/Tariq holds 4), OIDC both registries; deferred: gate-activation hardening (#207/#208/#211 + 2 W9 carry-overs), more #102 P2, installer-completeness #162/#142/#148/#141/#155, #110. Read first.
- [Config-driven architecture](reference_config_driven_architecture.md) — config→assets→bootstrap→dispatcher; one shared-config object, stdlib-only fail-open, hook contract, `cfg.path.parent.parent` = repo root.
- [Lifecycle state machine](reference_lifecycle_state_machine.md) — lifecycle.py: monotonic wave allocator, merge models, classify_reachability, transitions + CLI.
- [Per-child union rosters](reference_per_child_union_rosters.md) — roster_gen partition (meta=org roles, child=lead+domain engineers); identity gate enforces meta∪child via parent-merge.
- [CLI framework bundling](reference_cli_framework_bundling.md) — hatch BundleSharedDataHook → `real_team/_bundled/framework`; `init --with-hooks` subprocesses the bundled bootstrap `--no-team`.
- [upsert_status_keys seeding](project_upsert_status_keys_seeding.md) — can't seed empty `{}`; first write must be seeded directly in compact multi-line shape (lifecycle `_initial_text`).
- [Commit/PR mechanics](feedback_framework_commit_pr_mechanics.md) — owner identity via `-c`, msgs via `-F file`, title via `gh api PATCH` (projects-classic), push unpiped; CI runs `ruff check` only.
- [Session handoff](handoff.md) — latest pickup point; read first at session start.
