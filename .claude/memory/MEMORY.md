# Project Memory — 2real-team-framework

One line per memory; topic files in `.claude/memory/*.md` are read on demand. Recording a
memory: create/edit `<kebab-slug>.md` with frontmatter (`name`, `description`, `metadata.type`),
add a pointer line here, link related memories with `[[slug]]`, and commit it so it travels with
the branch. Update an existing file rather than duplicating; delete memories that turn out wrong.

- [Framework extraction state](project_framework_extraction_state.md) — baseline: released v0.9.2 (Phase 6 W7 "harden the armed gate": S1 #214 fail-open the oracle on comment-fetch error via `unknown` sentinel [#207]; S2 #215 example.json `reviewers_required`→1 + guard, per-PR cr-cycles wording [#208/#211]; S3 #216 charter-manifest checksum cross-check + gitignore normalize [2 W9 carry-overs] — **deferred-debt list now EMPTY**; 3 PRs/0 CR/717 tests, first wave whose story merges ran through the LIVE gate; reserved-5 ROTATED on pre-registered criteria — Tariq 4→5 [authored flagship #207], Nia 5→4 [clean-no-catch decay], Paloma/Ibrahim 4→4; rollup landed via direct-push escape hatch since the permanently-armed gate refuses the verdict-less rollup PR), OIDC both registries; deferred: more #102 P2, installer-completeness #162/#142/#148/#141/#155, #110. Read first.
- [Config-driven architecture](reference_config_driven_architecture.md) — config→assets→bootstrap→dispatcher; one shared-config object, stdlib-only fail-open, hook contract, `cfg.path.parent.parent` = repo root.
- [Lifecycle state machine](reference_lifecycle_state_machine.md) — lifecycle.py: monotonic wave allocator, merge models, classify_reachability, transitions + CLI.
- [Per-child union rosters](reference_per_child_union_rosters.md) — roster_gen partition (meta=org roles, child=lead+domain engineers); identity gate enforces meta∪child via parent-merge.
- [CLI framework bundling](reference_cli_framework_bundling.md) — hatch BundleSharedDataHook → `real_team/_bundled/framework`; `init --with-hooks` subprocesses the bundled bootstrap `--no-team`.
- [upsert_status_keys seeding](project_upsert_status_keys_seeding.md) — can't seed empty `{}`; first write must be seeded directly in compact multi-line shape (lifecycle `_initial_text`).
- [Commit/PR mechanics](feedback_framework_commit_pr_mechanics.md) — owner identity via `-c`, msgs via `-F file`, title via `gh api PATCH` (projects-classic), push unpiped; CI runs `ruff check` only.
- [Session handoff](handoff.md) — latest pickup point; read first at session start.
