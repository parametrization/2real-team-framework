<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-07 (Phase 6 Wave 5 COMPLETE; v0.9.0 SHIPPED to main + both registries)

## Pickup (next concrete step)
**Phase 6 Wave 5 ("PR-review state machine, dormant") is DONE and released. main is at v0.9.0.** Nothing
is in flight; working tree is clean. The next action is an **owner decision**: pick the next wave/phase
theme. **No wave is reserved.** Do NOT start a wave without theme + kickoff approval (gate).

When the owner sets a theme + approves kickoff: scope via `lifecycle.py wave allocate/start/scope`
(next global wave = **11**), then `/wave-start` (approval-gated). Base = `main`. Lifecycle:
`framework/assets/lib/lifecycle.py` (this repo has NO `.claude/lib` — runs from assets; state file =
`.claude/state.json`). Trust scoring: `framework/assets/lib/trust_signals.py`.

### Candidate next material (owner picks the theme)
- **Activate the PR-review gate (natural follow-up to this wave):** flip `policy.pr_review_gate_enabled`
  → true on this repo AND raise `policy.reviewers_required` to 2 first (at 1 the gate is trivially met /
  self-locks). This is the deliberately-deferred activation of what W5 shipped dormant. Dogfood the
  enabled gate against a real not-approved PR before enabling anywhere downstream. The oracle's N-of-M
  path is currently proven only by unit tests (never run live at reviewers_required≥2).
- **More #102 P2 tranche** (mapping doc `framework/recipes/NOORINALABS_RECONCILE.md`): governance charter
  modules (`tech-decisions`, `artifact-ownership`, `state-claims`, `communication`), wave-lifecycle
  GH-Projects automation (board-field sync, wave-evidence gates), ontology-consultation enforcement hooks,
  headcount-budget check, annunaki de-branding. #102 is still OPEN (P0 + P1-ready + the review-gate slice
  of P2 now landed).
- **Installer-completeness wave:** #162 (stale config module lists) + #142 (uninstall/`--teardown`) +
  #148 (`cli_bridge_soft_degrade` + `--compare` CI gate) + #141 (flaky meta-install idempotency) +
  #155 (real-repo provisioner hardening).
- **Process debt (unapplied proposals in feedback_log, need owner approval):**
  1. **Single integration-owner for shared registries** (NEW, W5 retro) — when 2+ stories touch the same
     `pre_bash`/`_DEFAULTS`/golden-manifest, designate one integration owner (or serialize those edits) to
     pre-empt the predictable merge conflict. W5 hit exactly this (S2 vs S3). Low effort.
  2. **Pin contracts against code, not prose** (NEW, W5 retro) — validate a frozen inter-story contract
     against the actual grammar/parsing layer at authoring time. Would have caught the requestee/Requestor
     bug before it reached an implementer.
  3. **Charter-manifest checksum cross-check** in `charter_drift.py plan()` (W9 carry-over, Nia #190).
  4. **Normalize `ensure_gitignore_entries` matching** before compare (W9 carry-over, Tariq #191).
- **Exploratory:** #110 (installer-as-CC-skill); #177 rename (report in `RENAME_COSTOUT.md`, owner picks a
  name + approves before execution).

## What shipped this session — Phase 6 Wave 5 → v0.9.0
**Rollup PR #200** (`deployments/phase6/wave-5` → main, merge **12300f3**). Version bump **03dba99**
(0.8.1→0.9.0, minor). Wrapup commit **afbe386**. Ontology refresh **30e4f7e**. Release **v0.9.0** →
OIDC published. **Verified live: npm 0.9.0 (`latest`); PyPI `/0.9.0/json`=200.** GH Release `v0.9.0` +
lightweight tag `deployments-phase6-wave-5` on the merge commit. Meta **#193** + stories
**#194/#195/#196** closed. **3 PRs, 0 changes-requested cycles (all Replied first pass), 33%
concentration, 694 tests** (+33), ruff clean, all 3 dual-deploy `--check` gates exit 0.

The #102 **P2** review-gate flagship — a PR-review state machine, shipped dormant. See
[[project_framework_extraction_state]] for the full v0.9.0 baseline + per-story detail.
- **S1 #194/PR#197 (Paloma → Tariq):** `pr_review_state` oracle — pure `compute_state()` + fail-open
  `review_state()` over the existing `trust_signals` verdict layer (reconcile, not a port). Caught +
  escalated a real bug in the frozen contract (requestee vs `Requestor:`).
- **S3 #196/PR#198 (Nia → Tariq):** `block_gh_pr_review` PreToolUse guard (**live**, unflagged — only
  blocks always-wrong cases) reusing `validate_review_comment_format` + enriched `review-pr` skill.
- **S2 #195/PR#199 (Ibrahim → Nia):** `validate_pr_review` merge gate — **SHIPS DORMANT** behind new
  `policy.pr_review_gate_enabled=false` (flag check short-circuits before the oracle; `reviewers_required=1`
  would self-lock). Ibrahim also owned the predictable S2↔S3 `pre_bash`/manifest conflict himself.

## Team / trust
- **Clean wave: 0 Must-fix caught, 0 received.** All three implementers returned Replied first pass; both
  reviewers reproduced every load-bearing claim (both mutation bars re-run independently).
- **Trust (via `trust_signals score 10` + distribution discipline): all implementers delta 0.** Paloma
  4→4, Ibrahim 4→4, Nia 5→5 (**held** — anchored by fresh substantive S3 authorship + a to-the-bar S2
  review). **Tariq 5→4 — reserved-5 DECAYED to baseline:** 2nd consecutive wave (W9, W10) with no scoring
  catch and no authored PR; the reserved-5 rewards catches/exceptional signal, so it reverts to the
  strong-solid 4, re-earnable on a real blocking catch or a substantive authored PR. Reviews were
  exemplary — the decay is the mechanism having teeth, not a knock on the work. trust_matrix.md +
  feedback_log.md Wave 10 sections committed (`afbe386`).

## Mechanical state
- Branch: **main** @ `30e4f7e` (clean — ontology structural refresh committed this session, not stashed).
- Release **v0.9.0** live on both registries. Open PRs: none. Wave branch `deployments/phase6/wave-5`
  deleted; all 3 feature branches + agent worktrees cleaned. `deployments-phase6-wave-5` tag preserves the
  ref. (Pre-existing stash cruft `stash@{1}`–`{9}` from old sessions left untouched — not this wave's.)
- Open issues: **#102** (more P2 remains) · installer debt **#162/#142/#148/#141/#155** · **#110**.
- Lifecycle: `last_completed_wave=wave-10` (phase 6, wave-branch, pr=3, cr_cycles=0, concentration=33);
  `current_wave=wave-10`; **no wave reserved**; next allocate = **wave 11** (theme TBD).
