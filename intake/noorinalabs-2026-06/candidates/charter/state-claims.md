# State Claims and Verification Discipline

This file documents the team's discipline for making claims about the state of artifacts (PRs, issues, branches, files, sha references) in coordination messages, review comments, and status updates.

<!-- Promoted from memory: feedback_refresh_before_status_claim.md (already encoded as the claim-direction discipline below; marker reconciliation via /promotion-audit 2026-06-19) -->

## Refresh State Before Claim (Mandatory) <!-- promotion-target: skill -->

Before any state-claim — phrases like `X/Y cleared`, `comprehensive coverage`, `all items addressed`, `merged at sha Y`, `PR head is Z`, `verified at head_sha=W`, or any assertion about the current state of an artifact you are NOT actively writing to — perform a fresh verification call (`gh api`, `git show <ref>`, or equivalent) within the same tool-block as the claim, with manual eyeball-check that the verification confirms the claim.

### Sub-rule: pre-write checklist

Before any SendMessage, PR comment, or issue body containing a state-claim, the agent must have at least one verification tool-call (matching the artifact being claimed) in the same response or one of the immediately preceding responses since the claim's scope was last touched. The discipline is:

1. Identify the load-bearing state-claim in the message you are about to send.
2. Identify the artifact whose state is being claimed (PR head, issue state, comment count, sha, etc.).
3. Call the appropriate verification tool (`gh pr view --json state,mergedAt,headRefOid,...`, `gh issue view --json state,closedAt`, `git rev-parse origin/<branch>`, etc.) with **fresh fetch** for git data.
4. Manually eyeball-check the tool output confirms the claim.
5. THEN send the message.

If the verification disconfirms the claim, revise the message — do not send the original claim with caveats appended ("I think X but haven't checked"). The discipline is to assert only what verification confirms.

### Sub-rule: Manager class is NOT exempt

The manager-pass review and orchestrator coordination roles are most exposed to this failure mode because:

- **Information-volume** — managers/orchestrators track multiple PRs simultaneously; more state than any single role.
- **Comprehensive-claim posture** — managers default to "I've reviewed everything" framing; implementers default to "I touched X" framing. The first is more vulnerable to incomplete-coverage-claims.
- **Asymmetric verification incentives** — a missed implementer detail surfaces in PR-review (the implementer's diff at code-write-time is the natural verification gate); a missed manager detail propagates because the manager-pass IS the verification.

For these reasons, the manager-class agent must apply the discipline at LEAST as strictly as implementers — and arguably more strictly because manager-class state-claims propagate further. Manager-pass review-coverage claims that turn out to have gaps are moderate feedback events.

### Severity

- One-off slip (caught by self before propagating): minor, no feedback log entry needed.
- One-off slip (caught by another agent's correction): minor, optional feedback log entry.
- Repeated slips on the same memory (≥3 in a wave): moderate, feedback log entry required.
- Manager-class slip on load-bearing review-coverage claim: moderate (regardless of repetition).

### Worked examples (Phase 3 Wave 1)

11 in-wave instances logged. Most-illustrative:

- **Bereket's #210 v3 manager-pass:** claimed `all 5 original review items + the v3 runbook-drift fix... all present and correct`. Lucas's second-reviewer pass caught two more drift sites Bereket missed (runbook L161 + compose L614-621 still describing the pre-amendment runbook-step + 0775 model). Manager-pass was the gate-clearing review, so the missed drift would have propagated to merge if Lucas hadn't caught it.
- **Orchestrator's #208 "2/2 cleared" misclaim:** claimed gate clearance based on comment-count, not actual reviewer-count. The hook block at merge surfaced the gap. Resolved by reposting reviewer comments with corrected directionality.
- **Bereket's `main#233` charter-ambiguity framing:** asserted the charter had two textually-supportable readings for `Requestor`/`Requestee` directionality; later wire-artifact verification showed only Reading 1 was in actual use. The framing itself was a Pattern C instance — claimed without exhaustively reading wire artifacts.

### Why

Phase 3 Wave 1 produced 11 distinct instances across 3 people in one wave, despite each violator naming the failure mode each time it occurred and committing to corrected behavior each time. Recurrence-after-self-naming is the signal — charter language alone has not been sufficient to fix the discipline historically. The pre-write checklist sub-rule is the lightweight, agent-side discipline; structural safeguards (hook at SendMessage boundary OR independent verification routing for load-bearing manager-class claims) remain proposed for future wave-retro discussion if the recurrence pattern persists.

### Aspiration: post-publish audit (no enforcement)

The proactive variant — self-audit of own previously-published claims absent any external prompt — was demonstrated by no team member in Phase 3 Wave 1. Charter aspires to this discipline but does not mandate it. Easily becomes box-checking; the team's discipline portfolio is honestly named to include this gap.

<!-- Promoted from memory: feedback_pr_state_in_refresh.md (P3W9 #346 memory audit, 2026-05-10) -->

### Sub-rule: PR-state field set

The canonical pre-claim refresh field set for PR state is:

```bash
gh pr view <N> --repo <owner>/<repo> --json state,mergedAt,headRefOid,statusCheckRollup,reviews,comments,mergeable
```

`state` and `mergedAt` together distinguish three PR statuses that single-field queries collapse:

- `state=OPEN, mergedAt=null` — actively under review or blocked.
- `state=OPEN, mergeable=false` — open but blocked (red CI, conflicts, missing approvals); a "still at 1/2" claim is correct here, but a "ready to merge" claim is wrong.
- `state=MERGED, mergedAt=<timestamp>` — already merged; any "still OPEN / awaiting reviewer" claim is posthumous and must be retracted, not patched with caveats.

Posthumous review noise — posting a fresh review comment on a PR that merged before SendMessage delivery — is the recurring failure mode this field set guards against. **Six occurrences in 36 hours** across the noorinalabs-main#194 fan-out (Nazia/Tarek/Oyun/Keanu/Luciana posthumous on data-acquisition + design-system PRs, plus Linh OPEN-blocked-vs-mergeable on isnad-graph#845) made this the load-bearing pre-comment refresh discipline. Reviewers must include `state,mergedAt` in EVERY pre-post `gh pr view --json` call; if `state != OPEN`, escalate to the spawning agent with the resolved state instead of posting.

### Sub-rule: empty `statusCheckRollup` is hard not-ready (never green) <!-- promotion-target: none -->

<!-- Promoted from memory: feedback_statuscheckrollup_ci_clean.md (P6W1 retro, owner-approved 2026-06-21, main#802) -->

An **empty** `statusCheckRollup` (`[]` — "no checks reported") is a **hard not-ready** state. It is NOT the same as green. Any "CI is green" / "all checks passed" / "ready to merge" claim MUST assert the rollup is **non-empty AND all-success** — never empty. An empty rollup means *no check ever validated this commit*, which is the absence of a verdict, not a passing verdict.

**Origin:** design-system #129 (P6W1) had its GitHub `synchronize` event silently dropped — **zero** workflow runs were created, so `statusCheckRollup` was `[]`. A naive "no failing checks" merge-readiness test would have passed it as green. Recovered by close/reopen.

**How to apply (claim direction):** the canonical PR-state refresh query (§ Sub-rule: PR-state field set) already includes `statusCheckRollup`; before any readiness claim, additionally assert `len(statusCheckRollup) > 0` AND every entry's `conclusion ∈ {SUCCESS, SKIPPED}` (or `NEUTRAL` outside the pending-allowlist). An empty list is a STOP, not a pass.

**Code (preferring code over prose):** `.claude/lib/pr_ci_state.py <PR#> --repo <owner/repo>` is the deterministic merge-readiness oracle — it reuses the merge gate's own classifier (`validate_pr_ci_status.classify_rollup`) and exits **0 = ready** (non-empty, all-success), **1 = not-ready** (empty rollup, or any failing/pending check), **2 = undeterminable**. It treats empty as not-ready **unconditionally** — that is the query-time readiness assertion this sub-rule pins.

**Reconciliation with the two path-filtered repos:** `noorinalabs-main` and `noorinalabs-deploy` can legitimately produce zero check-runs for a docs-only PR (`pull-requests.md` § Two path-filtered repos require PR-before-merge only). "Hard not-ready" there does NOT mean "never mergeable" — it means *never assume green*: verify the empty is the legitimate path-filtered case (e.g. confirm no covering `on.pull_request` workflow without a `paths:` filter should have run — `noorinalabs-main`'s `commit-identity.yml` runs on every PR, so a truly-empty rollup there is anomalous) before merging. The **merge gate** (`validate_pr_ci_status`, the hard PreToolUse block) encodes exactly this: it BLOCKS an empty rollup when a covering unfiltered-`paths` workflow exists (the #129 / unconditional-CI case) and warn-allows it when the repo is fully path-filtered, so the gate enforces #802 without deadlocking the two path-filtered repos. The readiness oracle and state-claim discipline are the always-on layer; the gate is the merge-time enforcement.

Cross-references: `feedback_statuscheckrollup_ci_clean` (the local-tests-pass-but-CI-fails axis this extends), `validate_pr_ci_status` hook (the merge gate), `validate_workflow_paths_coverage` hook (workflow-orphan sibling), `pull-requests.md` § CI Must Be Green Before Merge.

### Sub-rule: Issue-state field set

The canonical pre-claim refresh field set for issue state is:

```bash
gh api 'repos/<owner>/<repo>/issues/<N>' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"state={d['state']} state_reason={d.get('state_reason')} closed_at={d.get('closed_at')}\")"
```

`gh issue view --json` does NOT expose `state_reason` directly as a top-level JSON field; the REST API path is the load-bearing primitive.

`state_reason` discriminates closure semantics:

- `state=closed, state_reason=completed` — fix-PR was merged (somewhere). Necessary but **not sufficient** to claim "fix is on main"; verify `merge_commit_sha` reachability (next sub-rule).
- `state=closed, state_reason=not_planned` — issue was recognized as resolved by other work or won't-fix. The closing comment is the audit trail; cited PRs/issues are the load-bearing precedents.
- `state=closed, state_reason=null` (or `duplicate`) — typically a duplicate; check for `Duplicate of #M` in body or comments and follow to canonical issue.
- `state=open` — claim of "tracked as #N" is valid; check if implementer is assigned.

A closed issue with `state_reason=completed` is **not proof a regression test was added**. Verify the linked PR's diff for test additions OR grep the parent test file for the bug's input shape — the fixture-with-fix discipline (`hooks.md § Hook Authorship Requirements § 5. Parser-Fixture Coverage Requirements`) requires both the fix AND the regression test, but the closure-as-completed marker captures only the former.

### Sub-rule: merge_commit_sha reachability for "fix landed" claims

When a memory or audit cites issue#N as resolved AND you intend to act on the resolution claim (e.g., not bundle a regression test, treat the bug as fixed, close a duplicate-of), `state_reason=completed` is necessary but not sufficient. Verify the merge_commit_sha is reachable from the destination ref:

```bash
gh api 'repos/<owner>/<repo>/pulls/<N>' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"base={d['base']['ref']} merge_commit_sha={d.get('merge_commit_sha')}\")"

# If base != main, verify the wave-branch propagation status:
gh api 'repos/<owner>/<repo>/compare/main...deployments/phase-3/wave-N' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"ahead_by={d['ahead_by']} behind_by={d['behind_by']} status={d['status']}\")"
```

If `base != main` AND no wave-N → main merge PR exists (`gh pr list --base main --head deployments/phase-3/wave-N --state all` returns 0), the fix is **stranded** on the wave branch. Do not act on the "resolved" claim without verifying via a NEW search for any cherry-pick onto main.

This catches the **stranded-on-wave-branch** trap: a PR honors fixture-with-fix discipline but its `base.ref` is a wave branch that never merged forward. Steps `state_reason=completed` and "linked-PR diff has regression test" without sha-reachable-from-main is the trap surfaced by main#339: PR#305 honored fixture-with-fix discipline, but base=`deployments/phase-3/wave-7` and the wave-7→main merge never happened, so the fix is stranded. wave-7 vs main = ahead_by=10, behind_by=15, diverged. Bug is still LIVE on main and wave-8.

The reachability discipline distinguishes "discipline violation" from "wave-orchestration propagation gap" — different issue class, different owner. Wave-branch-merge-propagation is governed separately by `feedback_wave_branch_issue_close.md` (open-state-after-wave-merge); this rule is about the inverse: closed-state that doesn't reflect main reachability.

<!-- Promoted from memory: feedback_refresh_before_acting.md (P3W9 #346 memory audit, 2026-05-10) -->

### Sub-rule: Ledger-artifact reconciliation before status-driven decisions

Before any implementer-status claim — "implementing", "blocked", "done" — drives an orchestrator decision (merge sequencing, issue closure, task reassignment, or takeover), the orchestrator MUST reconcile the claimed status against actual artifacts via `gh api`. The ledger (SendMessage inbox, TaskList status, team-member status reports) lags artifact reality in high-churn waves.

**Required verification before acting on a status claim:**

```bash
# Branch existence: has the implementer pushed code at all?
gh api repos/noorinalabs/{repo}/git/refs/heads/{branch} --jq '.object.sha' 2>/dev/null \
  || echo "branch not found — zero-artifact stall"

# PR existence: is there an open or merged PR for this issue?
gh pr list --repo noorinalabs/{repo} \
  --search "in:title #{issue}" --state all \
  --json number,state,headRefOid,mergedAt
```

If the ledger says "implementing" but `gh api` finds no branch and no PR, the claimed status is **unverified**. Treat the task as a zero-artifact stall (charter `agents.md § Agent Liveness Checkpoint, Part (b)`) — do NOT make a merge/close/reassign decision based on the unverified ledger claim.

This sub-rule is the **ledger-lag class** of the refresh-before-claim discipline: whereas the other sub-rules guard against stale API responses for artifacts that DO exist, this one guards against missing artifacts the ledger incorrectly implies exist.

**Why:** P5W3 retro § Proposed Process Change #2 surfaced two consecutive waves where implementer status reports diverged from artifact reality: P5W2 ig#1023 reported "implementing" while deploy#454 had already resolved it; P5W3 ig#1038 reported "implementing" while no branch existed. Both required manual artifact checks to unblock the correct orchestrator decision.

**Severity:** Acting on an unverified status claim without artifact check — merge/close/reassign based solely on an inbox report: **moderate** regardless of whether the decision is ultimately correct (the artifact check is cheap; skipping it is habitual rather than cost-justified).

## Refresh State Before Acting (Mandatory) <!-- promotion-target: skill -->

The § Refresh State Before Claim discipline above governs **assertions** about artifact state. This section extends the same primitive to **actions**: re-check artifact state immediately before taking parallel or competing action, not based on N-minute-old snapshots.

### Why

Stale snapshots cause duplicate work. The completion-SendMessage delivery path lags actual artifact mutation by several seconds; assuming "no completion message in my inbox = task not done" is a false inference when the inbox lags reality. Inbox state is a **secondary** signal; the artifact itself is **primary**.

### How to apply

1. **Before acting in parallel with a spawned agent**, re-check the artifact directly via `gh api` / file read / `git ls-remote` — not based on any snapshot older than ~30 seconds.
2. **For batch-reviewer scenarios** (orchestrator considering posting Approved comments on PRs that a spawned reviewer was assigned), the canonical recipe is:
   ```bash
   gh api repos/<owner>/<repo>/issues/<N>/comments --jq 'length'
   ```
   immediately before posting, not at task-assignment time.
3. **Manager-class state assertions** (sibling to § Refresh State Before Claim § Manager Class is NOT Exempt) get the same discipline — but the new direction is **action-class**: the manager was about to *do* something, not just *claim* something.
4. **idle_notification ≠ task-not-completed.** The agent's completion SendMessage may be in flight to your inbox for several seconds after they actually finished. When in doubt, refresh the artifact, not the inbox.

### Severity if violated

- One-off duplicate action with benign outcome (both writers said the same thing): **minor**, paper-trail noise but no behavior consequence.
- Duplicate action with conflicting outcomes (orchestrator's parallel post diverges from spawned-agent's intent): **moderate**, signal-collapse failure.
- Recurring across a wave: **moderate-to-severe** — the discipline is cheap to apply (one API call); recurrence signals a habit gap, not a one-off.

### Worked example

P3W4 wave-bootstrap merge ceremony, 2026-05-05. Orchestrator checked wave-bootstrap PR comment counts at 15:46 ("0 comments"), waited for spawned reviewer Nadia, observed Nadia idle-notify without a visible completion SendMessage, assumed throttle, posted own duplicate Approved comments at 15:51:15. But Nadia had actually posted her 5 Approved comments at 15:50:46-59 in the 5-minute gap. Result: 5 duplicate audit-trail entries (functionally harmless because both said "Approved" and reinforced each other, but noisy). The completion-SendMessage delivery lagged Nadia's actual posts by ~30 seconds; assuming "no completion message in my inbox = task not done" was the false inference. A `gh api .../comments --jq 'length'` call <30s before the parallel post would have shown count=5 and prevented the duplication.

### Cross-references

- § Refresh State Before Claim — claim-class umbrella; this rule is the action-class extension.
- `feedback_refresh_before_status_claim.md` — implementer/reviewer-side foundational primitive that the § Refresh State Before Claim section above already encodes for the claim direction. This rule is the action-direction analogue.
- `feedback_stale_inbox_manager.md` (memory) — manager-class inbox-staleness failure mode, distinct from artifact-staleness; the inbox lags reality, the artifact IS reality.

<!-- Promoted from memory: feedback_canonical_source_via_git_show.md (P3W5 retro 2026-05-06) -->

## Canonical Source via `git show <sha>:<path>` (Mandatory) <!-- promotion-target: skill -->

For any task that says "use the canonical version from commit X" or "sync from parent sha X", the worktree is **convenience**, not truth. Local `main` may not yet include `X` even if `origin/main` does. The git object database is the source of truth.

### How to apply

For any "sync from parent sha X" or "use the canonical version from commit X" task:

1. **Confirm the sha exists locally:**
   ```bash
   git log --oneline --all | grep <sha>
   ```
2. **Check whether local `main` actually contains it:**
   ```bash
   git branch --contains <sha>
   ```
3. **Pull the file via `git show` regardless of worktree state:**
   ```bash
   git show <sha>:<path> > /tmp/canonical.<filename>
   ```
   Copy FROM `/tmp/canonical.<filename>`, not from the worktree.

If steps 1 and 2 disagree (sha exists locally but `main` doesn't contain it), you have a stale local main. Either fetch + fast-forward first, OR use `git show <sha>:<path>` directly — never trust the worktree path for a "from sha X" sync.

### Severity if violated

Silently copying a worktree file when the task said "from sha X" is moderate when the divergence has no behavior change, severe when the divergence is a downgrade through a load-bearing merge (e.g., the noorinalabs-main#112 part-(b) PR-#186 sync that would have downgraded the validate_commit_identity hook past its `_load_merged_roster` design).

### Why

Worktree state can lag origin by arbitrary amounts (un-pulled merges, in-progress branches checked out, paused rebase). The cost of an extra `git show` invocation is negligible; the cost of silently downgrading a child repo past a load-bearing merge is moderate-to-severe. The discipline is asymmetric: never costly to apply, sometimes catastrophic to skip.

### Worked example

`noorinalabs-main#112` part (b): task description said PR #186 at sha `508b6cd` was on main. True for `origin/main`, but the local worktree was on an earlier commit (`615f4c8`) that did NOT include #186. Worktree's `validate_commit_identity.py` was the pre-#186 design (no `_load_merged_roster`); copying it forward to child repos would have silently downgraded them. `git show 508b6cd:.claude/hooks/validate_commit_identity.py` returned the correct 232-line post-#186 version.
