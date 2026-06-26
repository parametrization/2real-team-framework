# Generic Skill: Iteration Wrap-Up (Merge, Verify, Close)

## Purpose

Finalize an iteration (cadence unit / "wave"): review open PRs, merge in
dependency order, close resolved issues, merge each repo's integration branch to
`main` with reachability + deployable-merge + staging gates, refresh the
knowledge base, and hand off to the retrospective. It is the **exit gate** before
retro. Arguments: team name + phase + iteration identifiers.

## Workflow

### 1. Inventory open PRs

List PRs targeting the iteration's integration branch, AND any main-targeting PRs
that belong to this iteration (by label / branch pattern).

### 2. Check CI per PR + classify

Ready (green + reviewed) / needs-review / CI-failing / draft / blocked
(unmerged dependency).

### 3. Determine merge order

Build a dependency graph (parse `Depends on #N` / `After #N`; detect
same-file-modifying PRs for conflict risk). Present the proposed sequence. **Merge
nothing until the user approves.**

### 4. Review each ready PR

Review in the standard format; file a tech-debt issue per tech-debt item (labeled
tech-debt + next iteration). If must-fix items are found, do NOT merge — report and
wait for fixes.

### 5. Merge approved PRs

After approval, merge in order; after each, verify CI on the target branch and no
new conflicts. If a merge reddens CI, stop and report.

### 6. Close resolved issues

Close issues referenced by merged PRs (close-keywords + branch-naming), with audit
comments (reuse the close-orphans audit logic).

### 7. Verify completeness

List remaining open iteration issues; for each, move to next iteration (deferred),
document remaining work (partial), or report.

### 8. Clean up worktrees (mandatory)

Remove all iteration worktrees (clean ones); report dirty ones (do NOT force-remove
without approval). Delete merged feature/worktree remote branches — **NEVER delete
an integration branch** (those are retained permanently as a rollback anchor).

### 9. Update documentation + 9.5. retro PR body-vs-diff check

Flag merged changes affecting API docs / config / architecture / process docs. If a
retro PR for this iteration is already open, every process-doc/skill/trust-matrix
file claimed in its body MUST appear in its diff — abort to Step 10 emission until
fixed (mirrors the retro skill's own check; direct-to-main for ratified retro
outputs is forbidden).

### 10. Final iteration report

PRs (merged/deferred/CI-failing); issues (closed/remaining); tech-debt created;
staging promotion result; docs; worktrees cleaned; next step (run retro).

### 10.5. Write canonical counter keys

> **High-volume remote-merge checkpoint:** if this iteration merged ≥ ~10 PRs via
> API against remote branches, the local checkout may be far behind origin —
> re-sync (`fetch` + relocate any local edits first, then reset to origin)
> **before** the first local bookkeeping commit, else it lands on a stale tree and
> needs a lossy recovery. Origin > local clone for all wrap-time state.

Write the top-level counter keys the retro verifies (`final_pr_count`,
`changes_requested_cycles`, `top_concentration_pct`) via the targeted upsert helper
(preserve compact-inline shape). **Compute them mechanically** from the merged-PR
set (a deterministic helper, not hand-rolled bash — a `for R in $SCALAR` loop
doesn't word-split under zsh and silently passes the whole repo list as one bogus
arg → 0 PRs → division-by-zero). Apply a **cross-window filter** (merged-at ≥
iteration kickoff time) when an integration branch was reused across split events,
plus an `--expect <count>` cross-check that loud-fails on mismatch. Read-back-verify.
Write literal `0` for an uncomputable key (the retro distinguishes "0" from
"missing").

### 10.6. Per-engineer trust signals

Extract the countable per-engineer signals from the merged-PR set
(`prs_merged`, `must_fix_received`, `must_fix_caught`, `ci_red_merges`,
`rework_cycles`, `review_false_positives`) and persist as one top-level key, so the
retro applies mechanical deltas instead of re-deriving by hand. Read-back-verify;
the retro re-extracts if absent (idempotent over the same PR set).

### 11. Merge each integration branch to `main` (every iteration)

Every iteration's wrap-up merges its integration branch to main (keeps main
continuously current — the next iteration bases off main). Each in-scope repo has
its OWN integration branch needing its OWN PR. Open per-repo integration→main PRs;
present a per-repo table; **wait for user approval**; merge each independently.
**Retain the integration branch — do NOT `--delete-branch`** (caveat: if the repo
auto-deletes head branches, restore it immediately after merge).

### 11.5. Reachability gate — branch propagation to main

After Step 11 merges (or declares not-needed), verify each integration branch is
**reachable from `origin/main`** (compare ahead-by/status at origin, not the local
clone). Any ahead/diverged branch with no merged integration→main PR is
**STRANDED** → BLOCK the wrap-up. Fix-forward: open/merge the integration→main PR,
or — if stranding is **intentional** — set a required, logged override rationale
(persisted to the status file).

### 11.5a. Deployable-merge verification gate

A integration→main merge is a **deployable merge**: it triggers push-to-main
workflows (publish/security-scan/schema/etc.) that **never ran on the per-issue
PRs**, so a clean PR can still redden `main` post-merge. Poll the Actions runs for
the exact merge SHA via a deterministic oracle: a failed run — or a required
workflow that produced **no run at all** — is a hard not-verified (empty-is-not-ready
discipline). `gh pr merge` returns 0 the instant the merge commit exists, long
before these run — so the merge's exit status proves nothing. Block on
not-verified; the **only** override case is a documented external red (newly-published
advisory, no-fix base-image CVE under an active ignore) and it MUST name a tracking
issue. A red caused by the iteration's own change is fixed forward, never overridden.

### 11.6 + 11.6a. Staging-promotion gate + per-merge deploy/publish watch

A iteration is not closeable until merged code is **promoted to staging green**
(inspect the canonical staging deploy run; block on red; **defer** — don't fail —
when staging doesn't exist yet; explicit rationale overrides). Then **actively
follow the deploy each integration→main merge triggered** (not just the latest run
— a later green run masks an earlier red). Also inspect the latest **publish** run
on each fan-in repo's default branch (a base-image CVE reddens publish *upstream*
of the deploy and the deploy watch misses it) and classify the cause
(base-image-drift vs code/other). A red fan-in deploy or publish blocks
closeability. **Production deploys are owner-approval-gated** — the wrap-up must NOT
approve/trigger them.

### 12. Knowledge-base update — both layers

**12a. Semantic overlay:** run the resolver for hand-curated files changed this
iteration. **12b. Structural index:** regenerate the index + cross-repo aggregator
(the iteration may have added hooks/skills/modules), commit if changed. Report both
in the Step 10 report. (The structural layer is always-current-by-regeneration —
the resolver never touches it; the generator IS its resolve path.)

### 12.5. Generic-prompt genericize checkpoint

Once per iteration, enumerate the iteration's new/changed framework artifacts that
**lack a counterpart** generic prompt **and aren't already decided**, and make ONE
deliberate genericize-or-skip pass per candidate, recording each decision in a
**version-controlled ledger** (the dedup memory) so the same artifact never
re-surfaces. (This is the batched replacement for a per-edit nudge hook that was
never actioned — a non-binding mid-task suggestion with no state decays.) Augment
the volatile pending set with a git-diff sweep of the iteration window in case it
was wiped. Commit the ledger; the pending file is gitignored.

### 13. Error-log attack + 14. memory-to-automation audit

Both are **preferentially run at retro** (their natural surface) — wrap-up retains
them as the canonical procedure body + a fallback, guarded by shared run-markers so
they execute at most once per iteration. Error attack: convert captured errors into
preventative automation before close (run before the memory audit so new automation
is visible). Memory audit: classify each memory file as hook / skill / process-doc /
keep; for each non-keep, file an issue, assign the best-fit owner, verify, then
delete/update the memory once captured.

## Reconciliation passes (run BEFORE the merge ceremony)

- **Scope-drop:** for each in-scope repo, if 0 PRs merged to its integration
  branch, resolve the drop EXPLICITLY — de-scoped (move to a descoped array with a
  reason) or carry-forward (file/update issues + next-iteration label). Silent drops
  not allowed.
- **Implementer-substitution:** for each merged PR, if the actual author ≠ declared
  implementer, record the swap EXPLICITLY (declared, actual, swapped-at, rationale).
  Silent swaps not allowed (the trust matrix would credit the wrong engineer).

## What remains manual

- User approves the merge sequence and the integration→main merges.
- Must-fix items require engineer action before merge.
- Deferred issues need a next-iteration placement decision.
- Memory-audit classifications are proposed — owner can override.

## Adaptation Notes

- The **layered merge gates** (reachability → deployable-merge → staging → per-merge
  deploy/publish watch) are the transferable core: a green PR is not proof of a
  deployable merge, because post-merge workflows never ran pre-merge.
- **Mechanical counter + per-engineer signal extraction** at wrap-up feeds the
  retro's mechanical trust deltas — keep them deterministic (helper, not bash) and
  apply the cross-window filter when a branch is reused.
- The **explicit scope-drop / substitution reconciliation** before the merge
  ceremony is what keeps declared-vs-delivered scope honest across iterations.
- Retain integration branches; gate production on owner approval.
