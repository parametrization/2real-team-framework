<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-06 (Phase 5 COMPLETE; v0.5.0 SHIPPED to main + both registries)

## Pickup (next concrete step)
**Phase 5 (installer robustness) is DONE and released. main is at v0.5.0.** Nothing is in
flight. The next action is an **owner decision**: pick the **Wave 6 theme** (reserved stub
meta-issue **#150**, currently "theme TBD"). Do NOT start Wave 6 without the theme + kickoff
approval. Candidate carry-forward material below.

When the owner sets the Wave 6 theme + approves kickoff: scope via `lifecycle.py wave
allocate/start/scope` (next global wave = **6**, reservation-aware allocator claims **#150**),
then `/wave-start` (approval-gated). Base branch = `main` (Phase 5 is fully merged; no wave to
stack on now).

### Candidate Wave 6 / next-phase material (owner picks the theme)
- **Deferred Phase 5 follow-ups (tech-debt, all OPEN):** **#142** product `uninstall`/`--teardown`
  command · **#148** implement `cli_bridge_soft_degrade` metric + wire `--compare` regression gate
  into CI · **#149** install durability/fidelity (parent-dir fsync, foreign-asset detection,
  child/meta manifest snapshot) · **#141** pre-existing flaky `test_meta_install_aggregate_is_idempotent`.
- **Deferred Phase 5 exploratory backlog:** #101/#102 (reverse-map noorinalabs against the new
  harness), #109 (botfarm before/after), #110 (ship the installer as a CC skill).
- **Longstanding deferred:** review-gate tranche (`validate_pr_review` + `pr_review_state`),
  `validate_branch_freshness`, mid-wave reachability `gh` wrapper, LLM persona personalities.

## What shipped this session — Phase 5 → v0.5.0
**Rollup PR #151** (`deployments/phase5/wave-2` → main, merge **7e6fe8b**) carried BOTH Phase 5
waves as a unit. **Release v0.5.0** created (target main) → OIDC published. **Verified live:
PyPI 2real-team-framework 0.5.0, npm 2real-team-framework 0.5.0** (both `latest`). Lightweight
tag `deployments-phase5-wave-2` created for traceability (commit object, **no** Release → no
double-publish). Merged deployment branch deleted; wave meta-issues **#133 + #140 closed**.

- **Wave 1 (global 4) — discovery**: #131 scorer false-positive gate (PR #134), #106 user-space
  audit → found **G1** (PR #135), #103 test-repo taxonomy B1–B12 + ~31 metrics (PR #136), #104
  install/test/teardown methodology (PR #137). 3 design docs in `framework/recipes/`.
- **Wave 2 (global 5) — build**: **#105** `python3 -m framework.harness` install/test/teardown
  harness (B1–B9 + inline dogfood default; B10/B11 real fixtures opt-in behind `--include-real`,
  clone-at-pinned-SHA, never touch live repos) + **#138** record_id permutation discriminant;
  **#139** golden manifest `expected_install_set(config)` (single source for install-completeness,
  derived from installer's own iterators, `--check` drift guard, retires hardcoded counts);
  **#107** consented **idempotent** user-level install (`bootstrap.py --user-space`) — **closes G1**
  (check-existing no-op / backup-or-amend / never clobbers); **#108** repo-level consent +
  backup/archive/**restore** (archive to sibling `.claude-backups/<UTC>/`, out of Claude scope,
  byte-identical restore) + **#145** atomic settings write (temp→fsync→os.replace) across both paths.
- **442 tests** (376→442), ruff clean, reinstall-parity + golden-manifest drift guards green.
- One latent flat-vs-nested config seam bug caught in #105 review and fixed **pre-merge**
  (`permutation_to_install_config`), so `files_installed_complete` grades against the real manifest
  (activation verified post-merge, `install_success_rate 1.00`).

## Team / trust
- **8 feature PRs, 0 must-fix, 0 CR cycles** across both waves. Team holds at **4 across the board**
  — **third consecutive fully-clean mechanical score** (steady state). No retirement triggers.
- `trust_matrix.md` (Wave 4 + Wave 5 sections) and `feedback_log.md` (both retros) updated + committed.

## Mechanical state
- Branch: **main** @ `7e6fe8b` (clean; only regenerable ontology churn). Release **v0.5.0** live.
- Open PRs: none. Deployment branch deleted; worktrees pruned (only main checkout remains).
- Open issues: **#150** (Wave 6 stub, theme TBD) · tech-debt **#142/#148/#149/#141** (Phase 5 deferred).
- Lifecycle: `last_completed_wave=wave-5` (phase 5, wave-branch, 4 PRs, cr_cycles=0, concentration=25%);
  `global_wave_seq=5`; `wave_6_meta_issue=#150` reserved; next allocate = **wave 6** (theme TBD).
- Baseline memory refreshed: see [[project_framework_extraction_state]] (now v0.5.0).
