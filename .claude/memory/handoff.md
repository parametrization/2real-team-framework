<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-07 (Phase 6 Wave 6 COMPLETE; v0.9.1 SHIPPED; PR-REVIEW GATE NOW ARMED)

## ⚠️ READ THIS FIRST — the review gate is LIVE on this repo
`.claude/framework.config.json` now has `policy.reviewers_required=2` + `policy.pr_review_gate_enabled=true`.
**Every PR into any branch now needs 2 distinct clean reviewer verdicts (charter `Requestor:` grammar,
author-exclusive) and no unresolved Must-fix, or `gh pr merge`/`gh pr ready` is BLOCKED** by the
`validate_pr_review` PreToolUse hook. Operational rules for running waves from here:
- **Assign 2 distinct reviewers per PR** (author-exclusive). Post their verdicts as charter-grammar PR
  comments (`Requestor:`/`Requestee:`/`RequestOrReplied:`) — that's what the oracle reads (GitHub's native
  reviewer field can't be used; team members aren't repo collaborators).
- **Rollup→main merges:** the gate reads the config in your *local working tree*. Merge the rollup while
  local `main` is still dormant (it is, until the rollup lands), so the rollup merge itself is not gated —
  this works naturally. After it merges + you `git pull`, local main is armed.
- **Wrapup / version bump / memory commits are DIRECT PUSHES to main → NOT gated** (the gate only guards
  `gh pr ready`/`gh pr merge`). Continue doing them as direct pushes with per-commit `-c` identity.
- **Escape hatch if the team wedges:** disarm via a direct config-only commit to `main` (a direct push is
  not gated; the gate is also fail-open on an oracle *exception*). NOTE the known gap #207: a transient
  comment-fetch error degrades to `pending` and BLOCKS rather than fail-opening — the hatch covers it.

## Pickup (next concrete step)
**Phase 6 Wave 6 is DONE and released. main is at v0.9.1 (`734787a`). Nothing in flight; tree clean.**
Next action is an **owner decision**: pick the next wave/phase theme. **No wave reserved.** Do NOT start
a wave without theme + kickoff approval (gate). Next global wave = **12** (Phase 6 Wave 7); wave branch
would be `deployments/phase6/wave-7`; tag `deployments-phase6-wave-7`.

### Candidate next material (owner picks the theme)
- **Gate-activation hardening wave (STRONGEST candidate — now that the gate is live):** fold the 3
  follow-ups this activation created — **#207** (make the gate fail-open on oracle *fetch* error, not just
  exceptions), **#208** (example.json `reviewers_required`→1 so adopters don't inherit a silent 2-bar),
  **#211** (`wave-end/SKILL.md` `--cr-cycles` wording → per-PR to match `rework_cycles`) — PLUS the 2 W9
  carry-overs (**charter-manifest checksum cross-check** in `charter_drift.py`; **normalize
  `ensure_gitignore_entries`**). Makes the freshly-armed gate robust before it governs many PRs. The
  deferred-debt list is now 5 items across 3 waves — a hardening wave is warranted.
- **More #102 P2:** governance charter modules (`tech-decisions`, `artifact-ownership`, `state-claims`,
  `communication`), wave-lifecycle GH-Projects automation, ontology-consultation enforcement, headcount
  budget, annunaki de-branding. #102 still OPEN.
- **Installer-completeness wave:** #162 / #142 / #148 / #141 / #155.
- **New process proposal awaiting owner approval (W11 retro):** track per-reviewer verdict counts in the
  wrapup (review-load balance) — Tariq carried 3 of 6 verdicts this wave; visible-before-bottleneck.

## What shipped this session — Phase 6 Wave 6 → v0.9.1
**Rollup PR #212** (`deployments/phase6/wave-6` → main, merge **191918e**). Bump **911ccd6** (0.9.0→0.9.1,
patch). Wrapup **bcea7f6**. Ontology **734787a**. Release **v0.9.1** OIDC-published — **verified live: npm
0.9.1 (`latest`); PyPI `/0.9.1/json`=200.** Tag `deployments-phase6-wave-6` on the merge. Meta **#201** +
stories **#202/#203/#204** closed. **3 PRs, 0 CR cycles, 33% concentration, 706 tests. First wave under
the 2-reviewer regime — 6 clean verdicts across 3 PRs.** See [[project_framework_extraction_state]] for
full detail.
- **S1 #202/PR#206 (Paloma → Nia + Tariq):** armed the gate + proved it LIVE (throwaway PR #205 blocked
  0/2 → passed 2/2); integration test binds real repo config; charter merge-rule + escape hatch.
- **S3 #204/PR#209 (Nia → Ibrahim + Tariq):** folded both W5 proposals into `charter/issues.md` + N=2
  assignment rule into `charter/pull-requests.md`; both APPLIED. Nia = sole charter integration-owner
  (dogfooded proposal #1 the same wave it was codified).
- **S2 #203/PR#210 (Ibrahim → Paloma + Tariq):** proved oracle N-of-M on real 2-reviewer data +
  mutation-proved no 1-reviewer assumption survives in trust/lifecycle. Tests-only.

## Team / trust
- **Clean wave: 0 Must-fix caught (nothing was wrong), 0 received.** Every PR cleared its 2 reviewers
  first pass. **Trust (score 11 + distribution discipline): all implementers delta 0.** Paloma 4→4,
  Ibrahim 4→4 (single clean PRs, no bump). **Nia 5→5 HELD** (TL charter integration-owner + S1 review) —
  **3rd consecutive hold; a real scoring catch is now due, else it decays to 4 next clean-no-catch wave**
  (parity with Tariq's W10 decay). **Tariq 4→4** (3 excellent reviews, no catch; reserved-5 re-earnable on
  a blocking catch or a substantive authored PR — e.g. owning a hardening follow-up). trust_matrix.md +
  feedback_log.md Wave 11 sections committed (`bcea7f6`).

## Mechanical state
- Branch: **main** @ `734787a` (clean; ontology structural refresh committed this session).
- Release **v0.9.1** live on both registries. Open PRs: none. Wave branch `deployments/phase6/wave-6`
  deleted; all feature + review branches + agent worktrees cleaned. `deployments-phase6-wave-6` tag
  preserves the ref. (Pre-existing stash cruft `stash@{1}`–`{9}` from old sessions still untouched.)
- Open issues: **#102** (more P2) · hardening follow-ups **#207/#208/#211** · installer debt
  **#162/#142/#148/#141/#155** · **#110**.
- Lifecycle: `last_completed_wave=wave-11` (phase 6, wave-branch, pr=3, cr_cycles=0, concentration=33);
  `current_wave=wave-11`; **no wave reserved**; next allocate = **wave 12** (theme TBD).
