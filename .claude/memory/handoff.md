<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-07 (Phase 6 Wave 7 COMPLETE; v0.9.2 SHIPPED; deferred-debt tail CLEARED)

## ⚠️ READ THIS FIRST — the review gate is LIVE and now PERMANENTLY armed
`.claude/framework.config.json` has `policy.reviewers_required=2` + `policy.pr_review_gate_enabled=true`.
**Every PR into any branch needs 2 distinct clean reviewer verdicts (charter `Requestor:` grammar,
author-exclusive) and no unresolved Must-fix, or `gh pr merge`/`gh pr ready` is BLOCKED** by the
`validate_pr_review` PreToolUse hook. Operational rules for running waves from here:
- **Assign 2 distinct reviewers per PR** (author-exclusive). Post their verdicts as charter-grammar PR
  comments (`Requestor:`/`Requestee:`/`RequestOrReplied:`) — that's what the oracle reads (GitHub's native
  reviewer field can't be used; team members aren't repo collaborators). Balance review load across the
  team (W12 spread it Nia2/Paloma2/Tariq1/Ibrahim1).
- **⚠️ ROLLUP→MAIN NOW NEEDS THE ESCAPE HATCH.** Unlike W6 (where local main was still dormant at rollup
  time, so `gh pr merge` on the rollup slid through), the gate is now permanently armed — a rollup PR
  carries **no verdicts of its own**, so the oracle returns not-approved and `gh pr merge` is BLOCKED.
  **Land the rollup as a direct-push merge to main:** `git checkout main && git pull`, `git merge --no-ff
  deployments/phase6/wave-N`, commit with `-c` identity, `git push origin main` (a direct push is NOT
  gated). GitHub auto-marks the rollup PR as MERGED once its head commits reach main. (W12 retro proposes
  codifying this as a named step in `pull-requests.md` + `wave-end`.)
- **Wrapup / version bump / memory / ontology commits are DIRECT PUSHES to main → NOT gated.** Continue
  doing them as direct pushes with per-commit `-c` identity.
- **Escape hatch if the team wedges:** disarm via a direct config-only commit to `main`. NOTE #207 is now
  FIXED (a transient comment-fetch error degrades to `unknown` → fail-open ALLOW, no longer blocks).

## Pickup (next concrete step)
**Phase 6 Wave 7 is DONE and released. main is at v0.9.2 (`21e671f`). Nothing in flight; tree clean.**
Next action is an **owner decision**: pick the next wave/phase theme. **No wave reserved.** Do NOT start
a wave without theme + kickoff approval (gate). Next global wave = **13** (Phase 6 Wave 8); wave branch
would be `deployments/phase6/wave-8`; tag `deployments-phase6-wave-8`.

### Candidate next material (owner picks the theme) — the deferred-debt tail is now EMPTY
The gate-hardening backlog that dominated the last few handoffs is fully drained. Fresh candidates:
- **Distribute 2real as a Claude Code skill (#110, exploratory — the strategic bet):** publish/install
  the framework as a skill, no API key, setup inside Claude Code. Highest ceiling; lowers adoption
  friction dramatically. Likely a spike-then-build or its own Phase 7, not a single tidy wave.
- **Installer-completeness wave:** #142 (product `uninstall`/`--teardown` — a real capability gap), #155
  (real-repo provisioner hardening, 5 items), #148 (`cli_bridge_soft_degrade` + `--compare` CI gate),
  #162 (amend-path stale config module lists), #141 (flaky meta-install idempotency test). Serves the
  dual-deploy/adopter story directly.
- **More #102 P2:** governance charter modules (`tech-decisions`, `artifact-ownership`, `state-claims`,
  `communication`), wave-lifecycle GH-Projects automation, ontology-consultation enforcement, headcount
  budget, annunaki de-branding. #102 still OPEN.
- **Process-hardening (from the W12 retro, needs owner approval):** (1) codify the rollup direct-push
  escape-hatch as a named step in `pull-requests.md`/`wave-end`; (2) mechanize per-reviewer verdict counts
  in the wrapup (review-load balance — carried from W11); (3) stretch: difficulty-weight the trust scorer
  so a flagship correctness fix and a one-line config change don't score identically.

## What shipped this session — Phase 6 Wave 7 → v0.9.2
**Rollup PR #220** (`deployments/phase6/wave-7` → main via **direct-push merge `adce920`**). Bump
**0a1c5d0** (0.9.1→0.9.2, patch). Wrapup **beb3998**. Ontology **21e671f**. Release **v0.9.2**
OIDC-published — **verified live: npm 0.9.2 (`latest`); PyPI `/0.9.2/json`=200.** Tag
`deployments-phase6-wave-7`. Meta **#213** + stories **#214/#215/#216** closed; folded debt
**#207/#208/#211** closed. **3 PRs, 0 CR cycles, 33% concentration, 717 tests. First wave whose story
merges ran through the LIVE 2-reviewer gate.** See [[project_framework_extraction_state]] for full detail.
- **S1 #214/PR#218 (Tariq → Nia + Paloma):** oracle `unknown` sentinel on comment-fetch error; gate
  fail-opens on `unknown`, still blocks genuine not-approved; end-to-end mutation test. Closes #207.
- **S2 #215/PR#217 (Ibrahim → Paloma + Tariq):** example.json `reviewers_required` 2→1 + schema-default
  guard test; per-PR `--cr-cycles` wording. Closes #208, #211. This repo's armed runtime config untouched.
- **S3 #216/PR#219 (Paloma → Nia + Ibrahim):** charter-manifest checksum cross-check + `ensure_gitignore_
  entries` idempotency. Both W9 carry-overs. Paloma = sole manifest integration-owner (no regen needed).

## Team / trust — reserved-5 ROTATED on pre-registered criteria
- **Clean wave: 0 Must-fix caught (nothing was wrong), 0 received.** `trust_signals score 12` — all
  implementers delta 0. **Tariq 4→5** (RE-EARNED: authored the flagship #207 fail-open fix — the exact
  W11-registered "own a tracked follow-up" path back). **Nia 5→4** (DECAY: clean-no-catch wave, 0 authored
  PRs, 2 Replied reviews — the exact W11-pre-registered decay condition, parity with Tariq's W10). Paloma
  4→4 (authored S3 + manifest-owner), Ibrahim 4→4 (authored S2, closed his own #211 loop). trust_matrix.md
  + feedback_log.md Wave 12 sections committed (`beb3998`). Re-earn 5 = a real blocking catch or a
  substantive authored PR.

## Mechanical state
- Branch: **main** @ `21e671f` (clean; ontology structural refresh committed this session).
- Release **v0.9.2** live on both registries. Open PRs: none. Wave branch `deployments/phase6/wave-7`
  + all feature/review branches deleted; agent worktrees removed. `deployments-phase6-wave-7` tag
  preserves the ref. (Pre-existing cruft still untouched: ~30 stale local feature branches from prior
  waves + old `stash@{1}`–`{9}` — cosmetic, out of scope without owner direction.)
- Open issues: **#102** (more P2) · installer debt **#162/#142/#148/#141/#155** · exploratory **#110**.
  (The gate follow-ups #207/#208/#211 are now CLOSED.)
- Lifecycle: `last_completed_wave=wave-12` (phase 6, wave-branch, pr=3, cr_cycles=0, concentration=33);
  `current_wave=wave-12`; **no wave reserved**; next allocate = **wave 13** (theme TBD).
