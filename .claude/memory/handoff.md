<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-06 (Phase 6 Wave 3 COMPLETE; v0.8.0 SHIPPED to main + both registries)

## Pickup (next concrete step)
**Phase 6 Wave 3 ("fail-closed foundation + flagship asset port") is DONE and released. main is at
v0.8.0.** Nothing is in flight. The next action is an **owner decision**: pick the next wave/phase
theme. **No wave is reserved.** Standing candidate = **#102 P2 tranche** (now unblocked by the P0
pipeline that shipped this wave). Do NOT start a wave without theme + kickoff approval (gate).

When the owner sets a theme + approves kickoff: scope via `lifecycle.py wave allocate/start/scope`
(next global wave = **9**; no reservation to claim), then `/wave-start` (approval-gated). Base =
`main`. Lifecycle: `framework/assets/lib/lifecycle.py` (this repo has NO `.claude/lib` — runs from
assets; state file = `.claude/state.json`).

### Candidate next material (owner picks the theme)
- **#102 P2 tranche** (the mapping doc `framework/recipes/NOORINALABS_RECONCILE.md` §3b/§3e/§3f):
  governance charter modules (`tech-decisions`, `artifact-ownership`, `state-claims`, `communication`),
  wave-lifecycle GH-Projects automation (board-field sync, wave-evidence gates), ontology-consultation
  enforcement hooks, headcount-budget check. #102 is still OPEN, annotated with the P0/P1-done note.
- **Installer-completeness wave:** #162 (stale config module lists) + #142 (uninstall/`--teardown`) +
  #148 (`cli_bridge_soft_degrade` + `--compare` CI gate) + #141 (flaky meta-install idempotency) +
  #155 (real-repo provisioner hardening, 5 items).
- **This-wave process debt (2 unapplied proposals in feedback_log, need owner approval):**
  1. **Make `reinstall.py` mirror the charter tree** — `_MANAGED_TREES` covers only `skills/`, so
     `team/charter/**` edits are hand-dual-deployed and a canonical↔runtime charter drift passes CI
     today (Paloma flagged on #181; the #180 norm edit had to be hand-applied to both copies).
  2. **Dogfood the `promotion-audit` skill** (shipped this wave, #102-P0) on this repo's own
     memory/charter and hand-verify its AUTO-tier promotions + DECIDE-tier draft issues once — the way
     the #164 ledger got its first real validation this wave.
- **Exploratory:** #110 (installer-as-CC-skill); #177 rename (report exists in `RENAME_COSTOUT.md`,
  effort M — owner would pick a name + approve before any execution). **Longstanding:** review-gate
  tranche (`validate_pr_review` + `pr_review_state`), mid-wave reachability `gh` wrapper, LLM personas.

## What shipped this session — Phase 6 Wave 3 → v0.8.0
**Rollup PR #186** (`deployments/phase6/wave-3` → main, merge **4af3866**). Version bump **bb2bcd7**.
Retro commit **0945b1c**. Release **v0.8.0** (target main) → OIDC published. **Verified live: npm
0.8.0 (`latest`); PyPI `/0.8.0/json`=200.** Lightweight tag `deployments-phase6-wave-3`. Deployment
branch + all 5 feature branches deleted; worktrees pruned. Meta **#178** + stories **#175/#174/#176/
#179/#180/#177** closed; **#102 kept OPEN** (P2 deferred, annotated).

**5 PRs, 1 changes-requested cycle** (the #184 footgun), 40% concentration, **629 tests**, ruff clean,
`.claude/` in sync. See [[project_framework_extraction_state]] for the full v0.8.0 baseline + per-story
detail.
- **Track A:** #175/PR#182 (Nia) dispatcher blocks-unless-`FAIL_OPEN` · #174+#176/PR#183 (Tariq)
  per-behavior-file gate + refactor exception class.
- **Track B:** #102-P0/PR#185 (Paloma) promotion/genericization pipeline (ledger + silent feeder hook
  + deterministic `promotion-audit` skill + charter marker) · #179/PR#184 (Ibrahim) branch-freshness +
  roster-union donors.
- **Track C:** #180/PR#181 (Nia) Must-fix-vs-tech-debt charter norm · #177 rename cost-out report.

## Team / trust
- **The #164 durable review-catch ledger fired for real** (first contested wave): Tariq caught the
  #184 branch-freshness zero-tolerance-default footgun (would have blocked every downstream adopter's
  `gh pr create`); recorded into `wave_8_review_catches` at issue-time, **survived** the in-place
  `Request→Replied` amendment → `must_fix_caught=1` scored. ⚠️ NOTE: the ledger write is an
  uncommitted state.json mutation — a `git reset --hard` during branch-switching WILL discard it;
  record-catch, then commit before any reset (learned this wave, re-recorded once).
- **Trust (via `trust_signals score 8` + distribution discipline):** **Tariq 5→5** (must_fix_caught=1),
  **Nia 4→5** (composite tie-top, 2 PRs incl. #175 keystone — **2nd earned 5 in project history**),
  **Paloma 4→4** (clean flagship #185), **Ibrahim 4→4** (must_fix_received=1 + rework=1, caught+fixed).
  trust_matrix.md + feedback_log.md Wave 8 sections committed.

## Mechanical state
- Branch: **main** @ `0945b1c` (clean). Release **v0.8.0** live on both registries.
- Open PRs: none. Deployment + feature branches deleted; only main checkout (worktrees pruned).
- Open issues: **#102** (P2 tranche, next candidate) · installer debt **#162/#142/#148/#141/#155** ·
  **#110** (installer-as-skill). (#177 rename report done; owner-gated on name choice.)
- Lifecycle: `last_completed_wave=wave-8` (phase 6, wave-branch, pr=5, cr_cycles=1, concentration=40);
  `current_wave=wave-8`; `global_wave_seq=8`; **no wave reserved**; next allocate = **wave 9** (theme TBD).
