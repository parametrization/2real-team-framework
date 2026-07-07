<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-07 (Phase 6 Wave 9 COMPLETE; v0.10.1 SHIPPED; gate & scorer hardened)

## ⚠️ READ THIS FIRST — the review gate is LIVE and permanently armed
`.claude/framework.config.json` has `policy.reviewers_required=2` + `policy.pr_review_gate_enabled=true`.
**Every PR needs 2 distinct clean reviewer verdicts (charter `Requestor:` grammar, author-exclusive) and
no unresolved Must-fix, or `gh pr merge`/`gh pr ready` is BLOCKED** by `validate_pr_review`. Operational
rules for running waves:
- **Assign 2 distinct reviewers per PR** (author-exclusive); post verdicts as charter-grammar PR comments.
  Balance review load. `wave-end` now emits per-reviewer verdict counts (W9 S3).
- **⚠️ CLEARING A `Request` NEEDS AMEND-IN-PLACE** (now a named step in `pull-requests.md`). The reviewer
  EDITS their original `Request` comment to `Replied`/`Must-fix: None` (`gh api -X PATCH .../issues/comments/
  <id>`), NOT a new comment — else the oracle stays `changes_requested`. As of W9, `trust_signals` credits
  the resolved catch from comment EDIT-HISTORY, so amend-in-place no longer erases `must_fix_caught`/
  `must_fix_received` (the W13 bug is fixed) — but the gate still needs the in-place edit to clear.
- **⚠️ CI-GREEN IS NOW ENFORCED AT MERGE (W9 S2, live on main).** `validate_pr_ci_status` blocks a
  pending/`--auto` `gh pr merge` when the base branch has no branch-protection enforcement (pending ≠ green
  when nothing holds it). Still: the ORCHESTRATOR should verify `gh pr checks <pr>` conclusions are green
  before merging, and RE-RUN a suspected flake rather than merge through it (W9 hit a `framework (3.12)`
  infra flake — zero-failed-steps signature — and a merge slipped past it before the hook was on main).
- **⚠️ ROLLUP→MAIN NEEDS THE ESCAPE HATCH** (now a named step in `pull-requests.md`). A verdict-less rollup
  PR can't clear the armed gate → land it via `git checkout main && git pull`, `git merge --no-ff
  deployments/phase6/wave-N`, commit with `-c` identity, `git push origin main` (a direct push is ungated).
  Wrapup/bump/memory/ontology commits are also direct pushes (ungated).
- **⚠️ SPAWNING WAVE AGENTS: use DISTINCT names + explicit `isolation: worktree`.** W9 hit a worktree
  collision: re-spawning agents with the SAME names (Nia/Tariq/Ibrahim) while the prior wave's namesakes were
  still terminating routed the new agents into the ORCHESTRATOR's shared worktree → branch tangling. Always
  pass the `isolation: "worktree"` Agent-tool param AND names distinct from any still-terminating agent.

## Pickup (next concrete step)
**Phase 6 Wave 9 is DONE and released. main is at v0.10.1 (`9368687`). Nothing in flight; tree clean.**
Next action is an **owner decision**: pick the next wave/phase theme. **No wave reserved.** Do NOT start a
wave without theme + kickoff approval (gate). Next global wave = **15** (Phase 6 Wave 10); wave branch would
be `deployments/phase6/wave-10`; tag `deployments-phase6-wave-10`.

### Candidate next material (owner picks the theme)
- **Installer-hardening (the deferred W8 follow-on — highest-readiness):** #162 (amend path leaves stale
  config module lists — reconcile not union), #155 (5 provisioner-hardening items). Both were deliberately
  deferred to keep W8 file-disjoint. Tightly scoped, high-certainty. *(This was the agreed "Wave 10" in the
  two-wave plan the owner approved — process-hardening first [W9, done], installer-hardening second.)*
- **Small hardening follow-ups surfaced by W9:** #234 (node RNG seed + name-dedupe root fix, then remove the
  S2 `vitest --retry` quarantine); the **rulesets-vs-classic branch-protection probe** (the W9 CI-gate uses
  the classic protection endpoint; repos using rulesets read as unenforced → safe-side over-block); the
  three W14-retro process proposals (codify safe re-spawning; gate manual merges on confirmed-green CI;
  reserved-5-vs-difficulty-ties refinement).
- **#110 distribute 2real as a Claude Code skill** (exploratory, strategic adoption bet; likely its own
  Phase 7). **More #102 P2** (governance charter modules, GH-Projects automation).

## What shipped this session — Phase 6 Wave 9 → v0.10.1
Rollup direct-push merge **`7ee2bdb`**; bump **`9e8b2fa`** (0.10.0→0.10.1, PATCH — internal machinery);
wrapup **`1495b46`**; ontology **`9368687`**. Release **v0.10.1** OIDC-published. Tag
`deployments-phase6-wave-9`. Meta **#228** + stories **#229/#230/#231** closed. **3 PRs, 0 CR cycles, 33%
concentration, ~797 tests, all 6 verdicts clean first-pass.** See [[project_framework_extraction_state]].
- **S1 #229/PR#233 (Nia → Paloma + Tariq):** trust scorer credits resolved catches from comment edit-history
  (fixes the W13 amend-in-place erasure) + difficulty weight. Fail-open, oracle untouched.
- **S2 #230/PR#235 (Tariq → Ibrahim + Nia):** CI-green merge precondition in `validate_pr_ci_status` — block
  a pending merge when the base has no branch-protection enforcement; `--admin` preserved+tested; node
  quarantine. Premise corrected by Tariq's investigation (reconcile-don't-duplicate). Node RNG fix → #234.
- **S3 #231/PR#232 (Ibrahim → Paloma + Tariq):** amend-in-place + rollup escape-hatch charter steps;
  wave-end review-load counts.

## Team / trust — reserved-5 HELD (Tariq); Nia 5-ready
- `score 14` (first run of the new edit-history + difficulty scorer): all three authors difficulty=3, delta
  0; edit-history credited nothing (clean wave, no amend-in-place catches). **Tariq 5→5** (HELD — standout S2
  root-cause that corrected a mis-scoped story). **Nia 4→4** (authored the flagship S1 scorer fix — her
  registered re-earn path — 5-READY but blocked by the single reserved-5; Tariq didn't decay). **Ibrahim
  4→4** (S3 + clean self-recovery of his wrong-branch commit during the incident). **Paloma 4→4** (2 clean
  mutation-checked reviews). trust_matrix.md + feedback_log.md Wave 14 sections committed (`1495b46`).
- **Two orchestration incidents (mine): the worktree collision + merging S1 on a red-flake check.** Both
  recovered; engineers handled adversity well. The CI-green hook W9 shipped is now live on main.

## Mechanical state
- Branch: **main** @ `9368687` (clean; ontology refresh committed).
- Release **v0.10.1** live (verify: `gh release view v0.10.1`; npm `latest`; PyPI `/0.10.1/json`). Open PRs:
  none. Wave branch `deployments/phase6/wave-9` + all feature branches merged; the W9 agent worktrees
  (`agent-*`, `tariq-0230-s2`, and the detached `nia-review-s2`) may still be listed — prune with `git
  worktree prune` / `git worktree remove` at leisure. `deployments-phase6-wave-9` tag preserves the ref.
- Open issues: **#102** (more P2) · installer-hardening **#162/#155** (deferred W8 follow-on = the planned
  Wave 10) · **#234** (node RNG) · exploratory **#110**.
- Lifecycle: `last_completed_wave=wave-14` (phase 6, wave-branch, pr=3, cr_cycles=0, concentration=33);
  `current_wave=wave-14`; **no wave reserved**; next allocate = **wave 15** (theme TBD).
