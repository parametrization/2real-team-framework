<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-06 (Phase 6 Wave 1 COMPLETE; v0.6.0 SHIPPED to main + both registries)

## Pickup (next concrete step)
**Phase 6 Wave 1 ("Prove it on real repos" — validation) is DONE and released. main is at
v0.6.0.** Nothing is in flight. Owner chose to **roll up Phase 6 after just Wave 1** (not stack a
Wave 2 first). The next action is an **owner decision**: pick the **Phase 6 Wave 2 theme** (reserved
stub meta-issue **#165**, currently "theme TBD") OR open a new phase. Do NOT start Wave 2 without
theme + kickoff approval.

When the owner sets the theme + approves kickoff: scope via `lifecycle.py wave allocate/start/scope`
(next global wave = **7**; reservation-aware allocator claims **#165**; phase-local ordinal = Phase 6
Wave 2), then `/wave-start` (approval-gated). Base = `main` (Phase 6 W1 fully merged; no wave to stack on).

### Candidate Wave 2 / next material (owner picks the theme)
- **Top carry-forward — #102**: port the ~18 mined noorinalabs assets into the framework. The W1
  audit (`framework/recipes/NOORINALABS_RECONCILE.md`) reframed this as **fork-reconciliation** and
  found it's a per-hook rewiring effort (P0 promotion/genericization pipeline, P1
  `validate_branch_freshness.py` + roster-union) — sized as its own wave, deferred out of W1's tail.
- **W1 tech-debt (all OPEN):** **#164** verdict amend-in-place erases per-reviewer `must_fix_caught`
  from `trust_signals` (real scoring gap — see below) · **#162** amend path leaves stale config
  module lists (`config_module_lists_complete`) · **#163** unguarded `os.close` in `_fsync_dir`
  fail-open path · **#161** CONTRIBUTING flag-table row implies `--json` depends on `--compare`.
- **Phase 5 deferred tech-debt (still OPEN):** **#142** product `uninstall`/`--teardown` · **#148**
  `cli_bridge_soft_degrade` + `--compare` CI gate · **#141** flaky meta-install idempotency test.
  (**#149** durability CLOSED this wave.)
- **Exploratory:** #110 (ship installer as a CC skill). **Longstanding:** review-gate tranche
  (`validate_pr_review` + `pr_review_state`), mid-wave reachability `gh` wrapper, LLM personas.

### 3 process proposals from the W1 retro (in feedback_log, NOT yet applied — need owner approval)
1. **Fix #164** so QA credit survives the amendment convention (read comment edit history, or record
   catches at issue-time into state.json, or post a distinct `Replied` follow-up instead of editing
   in place). Without it, every clean-after-fix wave under-credits reviewers.
2. **Pre-review author self-check gate:** "every new behavior has a load-bearing (revert→fail) test."
   All 3 W1 must-fixes were this exact class.
3. **Make lifecycle kickoff-persistence non-optional** — W1 ran un-stamped (`state.json` stuck at
   wave-5) and needed retroactive reconciliation at wrapup.

## What shipped this session — Phase 6 Wave 1 → v0.6.0
**Rollup PR #166** (`deployments/phase6/wave-1` → main, merge **8da3562**). Version bump `da1b705`.
**Release v0.6.0** (target main) → OIDC published. **Verified live: npm 0.6.0 (`latest`); PyPI 0.6.0
`/0.6.0/json` = 200** (index endpoint lagged at 0.5.0 — Fastly CDN, normal). Lightweight tag
`deployments-phase6-wave-1` on the merge commit (traceability, **no** Release → no double-publish).
Deployment branch deleted; wave meta **#150 closed**.

5 PRs (real-repo provisioner #154/#153; botfarm upgrade study #157/#109; noorinalabs reconcile
#156/#101; installer docs #159/#152; durability hardening #160/#149). Scope = `framework/`
dev-tooling + 2 install fixes + docs; **no `framework/assets/**` runtime changes → #116 dual-deploy
did NOT apply.** 466 tests, ruff clean.

**Validation proved in the wild:** read-only source invariant held on every real source (no
`SourceMutatedError`); byte-identical botfarm restore on a 150-file diverged install; live-pin caught
botfarm's `main` advancing mid-session; real durability bugs (parent-dir fsync gap, archive
non-atomicity) surfaced → fixed same-wave (#160).

## Team / trust
- **5 PRs, 3 changes-requested cycles** (all Tariq, all load-bearing/mutation-proven), 40%
  concentration, 0 CI-red. First wave with real CR cycles since Wave 2 (broke the 3-wave clean streak).
- **Tariq 4→5** — the **first earned 5 in project history** (distribution-discipline reserved 5:
  `must_fix_caught=3` vs 0 for everyone else). Paloma/Ibrahim/Nia hold at **4** (delta 0). Negative
  lines: Paloma shipped-without-test ×2, Ibrahim 1 tautological fsync test, Nia lowest output.
- **Scoring caveat (#164):** the mechanical scorer, run post-amendment, reported all-zeros and
  dropped Tariq — signals were RECONSTRUCTED from historic PR timelines; `cr-cycles=3` preserved via
  `wave_6_counter_corrections` (claimed stands). `trust_matrix.md` (Wave 6 section) + `feedback_log.md`
  (W6 retro) updated + committed.
- **Orchestrator self-correction:** reviewer-spawn instructions had `Requestor`/`Requestee` swapped
  (Requestor = reviewer; keys trust scoring). Tariq caught it; 3 mis-attributed comments PATCHed in
  place. Rule recorded in [[feedback_framework_commit_pr_mechanics]].

## Mechanical state
- Branch: **main** @ `da1b705` (clean). Release **v0.6.0** live on both registries.
- Open PRs: none. Deployment branch deleted; worktrees pruned (only main checkout).
- Open issues: **#165** (Wave 2 stub, theme TBD) · tech-debt **#161/#162/#163/#164** (W1) +
  **#142/#148/#141** (Phase 5) + **#102** (asset port) + **#110** (installer-as-skill).
- Lifecycle: `last_completed_wave=wave-6` (phase 6, wave-branch, pr=5, cr_cycles=3, concentration=40%,
  + `wave_6_counter_corrections`); `global_wave_seq=6`; `wave_7_meta_issue=#165` reserved; next
  allocate = **wave 7** (Phase 6 Wave 2, theme TBD).
- Baseline memory refreshed: see [[project_framework_extraction_state]] (now v0.6.0).
