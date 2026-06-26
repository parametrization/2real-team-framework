# Generic Skill: Iteration Retrospective

## Purpose

Run a retrospective for a completed iteration (cadence unit / "wave"): analyze
merged PRs, produce **mechanical, evidence-anchored** per-engineer assessments,
update the trust matrix, append a feedback-log entry, propose process-doc changes,
run the promotion + error + memory audits, and reconcile the next iteration's
scope. Arguments: team name + phase + iteration identifiers.

## Workflow

### 1. Knowledge-base + 1.5. board freshness checks

Run the read-only librarian to check ontology staleness (staleness here implies a
wrap-up process gap, since wrap-up should have rebuilt). Run the board-drift audit
so the board's view matches actual issue state — stale board state mis-frames retro
findings. Repair drift before analysis.

### 2. Gather merged PRs

List all PRs merged to the iteration's integration branch (number, title, author,
body, merged-at, reviews).

### 2.5. Status-counter verification

Before per-engineer assessment, **recompute** the numeric counters in the status
file from the PR data and surface drift (counters written at wrap-up tend to
drift). Handling: small mismatch → log the correction + rewrite the counter with a
`counter_corrections` record; large mismatch → retro-blocker, investigate the
wrap-up arithmetic. **Special case:** a changes-requested count recomputed from
*current* comment state under-counts when a changes-requested verdict was later
edited-in-place to approved — when the gap is fully explained by edit-in-place
verdicts, the **wrap-up-time value stands as authoritative-historic** (record the
measurement conflict, do not "correct" downward). Don't begin Step 3 until every
counter matches OR has a corrections record.

### 3. Gather review comments + CI data

Per merged PR: review comments (must-fix, tech-debt), CI pass/fail counts,
creation-to-merge time.

### 4. Per-engineer assessment (mechanical, evidence-anchored)

Trust scoring is mechanical — narrative self-grading is retired. Read (or
re-extract) the per-engineer **countable signals** the wrap-up wrote:
`prs_merged`, `must_fix_caught` (reviewer), `must_fix_received` (author),
`ci_red_merges`, `rework_cycles`, `review_false_positives`. Assess each engineer
from the numbers, not impressions.

**Forced negative-signal pass (bare "None" banned):** every active engineer MUST
get a specific evidence-backed gap OR an explicit `metrics clean: {numbers}` —
mechanically reject a bare None/N/A/- before continuing.

### 5. Update the trust matrix

The trust matrix lives **on `main`** — edit it directly on the retro branch so it
lands in the same retro PR as the feedback log (a separate side-branch orphans
updates off-main). Deltas are mechanical and each row cites the countable signal:
- bidirectional, clamped per iteration; CI-red merge / false-positive = −1; clean
  multi-PR delivery or strong reviewing = +1; a single clean PR is NOT a bump.
- **Decay:** no signal for N consecutive iterations drifts toward the midpoint.
- **Distribution discipline:** the top score is reserved for the iteration's top
  relative performer — never handed out for merely-clean work.
- **Retirement trigger:** if an engineer is bottom-tier or has CI-red merges across
  the last N iterations, surface a persona-archive recommendation for owner
  confirmation (do not auto-delete).

Append a dated trust-update section with a `Rated | Old | New | Reason` table
(Reason cites signal numbers) and a Done-Well / Needs-Improvement matrix (the
Needs-Improvement column is the forced negative-signal line).

### 6. Append to the feedback log

Append a retro entry: team performance, per-engineer assessments, top-3
going-well, top-3 pain points, proposed process changes (each with rationale).

### 6.5. Retro PR body-vs-diff sanity check

Any process-doc/skill/trust-matrix file **claimed** in the retro PR body MUST be
in the retro PR diff. Direct-to-main commits for ratified retro outputs are
forbidden (they bypass review + CI). If a claimed file is missing, commit it to
the retro branch — do NOT amend the body to drop the claim.

### 7. Propose process-doc changes

Present each as: what to change, which section, rationale (from retro findings).

### 7.5. Promotion audit

Invoke the promotion audit — it deterministically checks whether any memory,
process-doc section, or skill crossed a promotion threshold this iteration, opens
AUTO PRs / files DECIDE issues, and appends its table to this retro's feedback-log
entry + a standalone log.

### 7.6. Error-log attack + 7.7. memory-to-automation audit

Run the error-log attack (process monitor-captured errors into preventative
automation) and the memory-to-automation audit (codify soft memories into
hook/skill/process-doc). Both are **co-located** with the wrap-up's equivalents,
guarded by shared run-markers (whichever surface runs first wins). Run the error
attack **before** the memory audit so new automation is visible to it. Findings
feed Step 7 retroactively. (Retro is the preferred surface because the audits
otherwise get deferred at the long wrap-up.)

### 8. Present the full retro summary in conversation

Output the complete summary directly (not just to files): metrics, per-engineer
assessments, trust changes, top-3s, proposed process changes, personnel actions,
proposed process-doc changes. **Apply no process-doc changes without explicit
approval.**

### 9. Reconcile the next iteration's scope

Carry-forward state is freshest immediately after retro — the highest-value moment
to run the scope skill. Read the **next** iteration id from the monotonic counter
(NOT `{id}+1` — global ids are not sequential-per-phase). Find the next-iteration
meta-issue (anchored title match, assert exactly-one-hit). If none exists,
**auto-draft a stub** (title + carry-forward scaffold + candidate-scope pointer
are mechanical; only the THEME is an owner decision), board it, record the
meta-issue key, and surface "set the theme" — do NOT invoke the scope skill yet
(its theme gate requires an owner-set theme). If a themed meta-issue exists, invoke
the scope skill. This closes the retro→kickoff loop: every retro yields either a
reconciled scope or a ready-to-theme stub — never a bare "go create an issue."

## Wave-concentration metric

In Step 4, compute **top-implementer concentration** = max PRs by one implementer
/ total PRs. If ≥ 0.6, surface in the feedback log as either theme-fit
concentration (going-well + forward flag) or fragility concentration (pain point +
redistribution actions). The metric is **visibility, not policy** — the retro
forces the call.

## What remains manual

- User approves all process-doc changes.
- Severity calibration may need owner override.
- Trust-matrix changes are proposed — owner can veto specific adjustments.

## Adaptation Notes

- **Mechanical, signal-cited trust deltas** (no narrative self-grading) plus the
  **forced negative-signal pass** are the most transferable assessment ideas.
- The **counter-recompute + authoritative-historic** rule reconciles the conflict
  between "verdicts edited-in-place after fixes" and "recompute from current state."
- The **auto-draft-stub** retro→scope handoff removes the recurring "draft the
  meta-issue" blocker while preserving the owner's theme decision.
