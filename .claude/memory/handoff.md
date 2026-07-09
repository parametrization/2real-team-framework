<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-08 (Phase 7 Wave 1 / global wave 22 — EXECUTION COMPLETE, HOLDING AT OWNER ROLLUP GATE)

## ✅ READ FIRST — Wave 22 is fully built and gated; NOTHING is on main yet
All **3 stories are merged to the integration branch `deployments/phase7/wave-1`** and each cleared
the 2-reviewer gate. The wave is **NOT rolled up** — it is paused at the **owner approval gate** for
`rollup → main + release v0.12.0`. The owner said they were near their weekly limit and asked to stop.
**Do NOT merge to main or tag a release without explicit owner go-ahead** (that approval was still
pending when the session ended).

Open question the owner has NOT yet answered (ask on resume):
- **Version number:** `0.12.0` (proposed — new author-exclusion behavior across two surfaces reads as
  a minor bump) vs `0.11.2` (the gate fix alone is arguably a patch). I recommended `0.12.0`.
- **Explicit go-ahead** to `merge → main` + cut the release.

## What Wave 22 shipped (Phase 7 opener — "Mine the siblings, close the gate-parity debt")
3 file-disjoint stories · 3 PRs · 1 CR cycle · 33% concentration. Meta issue **#289**.

- **S1 #264 / PR #290** (Nia → Paloma + Tariq, 2 clean): sibling-repo mining audit note
  `intake/2026-07/MINING-FINDINGS.md`. Re-ranked top ports after both reviewers independently
  proved the audit's #1 "P0" (#881) was a **no-op** (our `parse_verdicts` already has both #881 guards
  + a stricter third) → I closed the spun-off #291 as no-op. Top net-new ports carried forward:
  #864 `verify_deployable_merge`, #424 reviewer-load kickoff gate, #907/#895.
- **S2 #288 / PR #292** (Paloma → Ibrahim + Tariq, **1 CR** → 2 clean): author-exclusive **scorer**.
  New `is_author_self_review(requestor, author, canon)` in `trust_signals.py` (fail-open/total), applied
  in `_account_pr` + `review_load`; drops author self-verdicts before accounting. **CR was doc-only:**
  Tariq caught a false "mirrors the merge gate" claim (the gate did NOT yet author-exclude — that was
  exactly #293); fixed in `864fc46` + `81517b9`, which ALSO reconciled a pre-existing false line in
  `pull-requests.md`. 5 revert→red tests.
- **S3 #293 / PR #294** (Ibrahim → Paloma + Tariq, 2 clean): author-exclusive **merge gate** — closes a
  **LIVE self-approval bypass**. `pr_review_state.compute_state`/`review_state` now resolve the PR
  **head-commit author** (`_pr_head_author`, fail-open) + roster canon and drop author self-verdicts,
  reusing the S2 helper — ONE exclusion rule for gate + scorer. **Pinned `ReviewState` output shape
  unchanged** (#194/#193 — only keyword-only `author`/`canon` INPUTS added). Both reviewers proved the
  bypass closed end-to-end through the LIVE gate with a real `gh` author fetch:
  before `{approvals:2,approved}` → after `{approvals:1,pending}`. Self-verdicts dropped ENTIRELY
  (neither approvals nor unresolved_must_fix — an author can't approve OR block their own PR).

## The security fix in one line
The armed merge gate (this repo: `reviewers_required=2`, `pr_review_gate_enabled=true`) used to count an
author's own clean `Requestor:<self>` verdict toward the 2-approval bar, so a 1-real-reviewer PR could
self-approve. **W22 closed it on both the gate and the scorer.**

## Rollup runbook (run ONLY after owner approves — this is the pending next action)
1. `git checkout main && git pull --ff-only` ; `git fetch origin`
2. `git merge --no-ff origin/deployments/phase7/wave-1` — **owner identity** `-c user.name/-c user.email`,
   message via **`-F <file>`** (never inline heredoc).
3. **Content-probe main BEFORE bump** (code-less rollup = stop-and-investigate):
   `git show main:framework/assets/lib/pr_review_state.py | grep -c _pr_head_author` (expect ≥1) and
   `grep -c is_author_self_review framework/assets/lib/trust_signals.py`.
4. Bump `0.11.1 → 0.12.0` (or owner's chosen number), push bare (`; echo rc=$?`, never piped).
5. GitHub Release tag **`deployments-phase7-wave-1`** (charter: slashes→hyphens), notes = the 3-story
   summary above.
6. Dual-publish PyPI + npm. **npm CI durability:** `publish-npm.yml` is pinned to `npm@^11.5.1`
   (npm@12 dropped node-20) with a `workflow_dispatch` trigger — if the npm job fails, dispatch it on main.
   Carry-forward: bump the publish runner to node 22 to un-pin.
7. `/wave-end 22` — merges are done, so mainly: **close #264/#288/#293** (they did NOT auto-close —
   "Closes #293" only fires on merge to the DEFAULT branch, and these merged to the integration branch),
   record counters (`--pr-count 3 --cr-cycles 1 --concentration 33`), emit review-load, prune worktrees.
8. `/wave-retro 22` — **first retro under the new author-exclusive scorer.** Trust deltas are mechanical
   (`trust_signals.py score`). Watch: S2's fix means author self-verdicts no longer inflate reviewer
   signals; S3's `#H5`-style change means a self-approved merge would register as a `gate_bypass` (−1).
   Standing matrix entering the retro: **Paloma 5, Tariq 4, Nia 4, Ibrahim 3.** Then draft the wave-23 stub.

## `gh`/commit mechanics (unchanged, keep applying)
- Owner commits: `git -c user.name="Steven French" -c user.email="parametrization@gmail.com"` — never global config.
- Team commits: roster identity + TWO `Co-Authored-By` trailers (member + Claude).
- Commit messages via **`-F <file>`**. `gh api -X PATCH` comment bodies via **`-F body=@file`, NEVER `-f`**
  (`-f` sends the literal `@path` string — hit 3× historically).
- Verdicts are PR **comments** (`gh pr comment`, `gh pr review` is blocked). `Requestor:`=reviewer,
  `Requestee:`=author — never swap. An author's must-fix reply is a PLAIN comment, never verdict grammar.
- Merge gate oracle: `pr_review_state.review_state('parametrization/2real-team-framework', <pr>)` — pass
  the **owner/repo** string (bare repo name → gh error → fail-open `unknown`; that bit me as a diagnostic
  false-alarm this session, NOT a real gate problem).

## Open issues / debt after W22
- **#264, #288, #293** — resolved by merged PRs, **close them in `/wave-end`** (did not auto-close).
- **#295** (NEW, filed this session, label `bug`, low/hardening) — Tariq's 2 non-blocking S3 follow-ups:
  (a) log the silent `_pr_head_author→None` fail-open so a rare flake re-opening the hole is observable;
  (b) union-in `gh pr view --json author` login to close the commit-suggestion/rebase head-author vector.
- **#291** — CLOSED this session as a no-op (the audit's #881 "P0" false alarm).
- Carry-forward ports from the #264 audit: **#864** `verify_deployable_merge`, **#424** reviewer-load
  kickoff gate, **#907/#895**; plus **#110**, more #102 P2, npm-CI node-22 bump.
- Next wave = **23** (Phase 7). Stub not yet drafted — `/wave-retro` Step 9 drafts it after rollup.

## Mechanical state at session end
- Branch: `main` (NOT yet updated with W22 — rollup pending). `.claude/memory/handoff.md` modified (this file).
- Integration branch `deployments/phase7/wave-1` HEAD = `2e1b3e5` (Merge #294); contains all 3 stories
  (#290/f83c648, #292/423ba56, #294/2e1b3e5).
- Open PRs: none (all 3 merged to integration branch).
- Lifecycle: `current_wave=wave-22`, `wave_22_active=true`, kicked off, merge-model `wave-branch`,
  `wave_22_meta_issue=#289`. **`wave wrapup` NOT yet run** (that's `/wave-end`, post-rollup).
- Trust matrix: **Paloma 5, Tariq 4, Nia 4, Ibrahim 3** (unchanged since W21 — W22 deltas computed in retro).
- v0.11.1 is the live release on main/PyPI/npm; v0.12.0 is staged-but-not-cut.
- Local stale feature branches (all merged server-side) — harmless housekeeping.
