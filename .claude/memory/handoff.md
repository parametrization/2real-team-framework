<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-05 (Phase 5 Wave 1 COMPLETE; Wave 2 gated on owner decisions)

## Pickup (next concrete step)
**Phase 5 Wave 1 (discovery tranche) is complete and integrated to the wave branch — NOT to main.**
Next step is **Phase 5 Wave 2 kickoff** (meta-issue **#140**, the build tranche), which is
**gated on 6 owner-decision items** below. When the owner answers them + approves kickoff:
scope Wave 2 via `lifecycle.py wave allocate/start/scope` (next global wave = **5**), base the
Wave 2 branch **on `deployments/phase5/wave-1`** (waves stack — see integration decision), then
`/wave-start 5 2` (approval-gated).

### Wave 2 (#140) scope — the BUILD tranche
- **#105** automated install/test/teardown harness emitting #104 stats across #103's B1–B12 sample.
- **#107** consented user-level install (backup-or-amend `~/.claude`) — closes the **G1** gap.
- **#108** consent + backup/archive/restore for repo-level `.claude` (shares code with #107).
- Fold in tech-debt **#138** (record_id join-key collision) + **#139** (metric-vocab reconciliation).
- Deferred to later Phase 5: #101/#102 (reverse-map noorinalabs), #109 (botfarm before/after), #110 (ship as CC skill).

### 6 owner-decision items that GATE Wave 2 kickoff (from the W1 spikes)
1. **Sample set**: hermetic B1–B9 as default CI set; which real fixtures (B10 noorinalabs / B11 botfarm_inc / B12 this-repo), all copy-first/never-mutate-live; large-repo B9 ~2000 files.
2. **Teardown**: harness-side v1 (no product uninstall) vs ship real `uninstall`/`--teardown`. (Team recommends harness-side v1.)
3. **G1 (load-bearing)**: consented user-level write of `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (+ `teammateMode`, `worktree.baseRef=fresh`) to `~/.claude/settings.json`, backup-or-amend, never clobber.
4. **Permission-glob split (G4)**: repo-relative perms repo-installed; absolute `~/.claude/**` + cross-repo globs user-level.
5. **Golden manifest**: single source for `files_installed_complete` + retire hardcoded counts (#139).
6. **Leave-manual set**: confirm frontend-design plugin / statusline / personal prefs stay manual.

## Decisions made this session (Phase 5 Wave 1 execution)
- **Theme set (owner)**: Phase 5 = installer robustness + install/test/teardown harness (folding #131). #133 re-themed.
- **Phase 5 Wave 1 (global wave 4, `deployments/phase5/wave-1`)** delivered **4 issues**:
  #131 scorer false-positive gate (PR #134, Paloma), #106 user-space audit (PR #135, Ibrahim),
  #103 test-repo taxonomy+metrics (PR #136, Tariq), #104 install methodology (PR #137, Nia).
  All charter-reviewed cross-assigned (author≠reviewer), **0 must-fix, 0 CR cycles, 25% concentration, 376 tests**.
- **Integration decision (owner)**: **stack Wave 2 on Wave 1, roll up Phase 5 as a unit** — one rollup
  PR + one release (~v0.5.0) when the user-facing installer features (#105/#107/#108) land. Wave 1 is
  discovery (3 design docs + the #131 dev-tooling fix): nothing user-facing → no standalone release.
- **Trust**: team holds at **4 across the board** (all delta 0 — single clean PR isn't a bump). Second
  consecutive fully-clean mechanical score; #131 landed this wave so the scorer has **zero** known artifacts left.
- **#131 CLOSED** — the last Phase 4 scorer artifact is fixed (gate `review_false_positives` on
  `_has_must_fix_items`) + regression test on the exact PR #115 shape. `framework/assets/lib/trust_signals.py`.

## Open threads / follow-ups
- **#138** (tech-debt) — metric-record `record_id = <bucket>/<installer>/<metric>` collides across
  permutations (B4 gate matrix); add a permutation discriminant OR composite record. Fold into #105.
- **#139** (tech-debt) — reconcile install-quality metric vocabulary in #103's doc (metric-level
  `install_success_rate`; add `cli_bridge_soft_degrade`; distinguish `reinstall_idempotent` vs
  `reinstall_parity_clean`; golden-manifest for hardcoded counts). Fold into Wave 2.
- **Process watch**: `must_fix_caught` gives reviewers no scored upside on a clean wave (good review
  registers as tech-debt). Not a bug; watch across waves.
- Deferred backlog #101/#102/#109/#110 still Phase 5 material (later waves).

## Mechanical state
- Branch: **`deployments/phase5/wave-1`** @ `af4ca9f` (pushed, **unmerged** — stays open for Wave 2 to stack on).
- **main** @ `014ea8e` (unchanged this session). No release cut this session (per stacking decision).
- Open PRs: (none). Feature branches deleted; worktrees pruned.
- Open issues: #138, #139 (W2 tech-debt) · #140 (W2 meta) · #101/#102/#105/#107/#108/#109/#110 (Phase 5 backlog).
- Lifecycle: `last_completed_wave=wave-4` (phase 5, wave-branch, 4 PRs, cr_cycles=0, concentration=25%);
  `global_wave_seq=4`; next allocate = **wave 5** (Phase 5 Wave 2, reserved meta-issue **#140**).
