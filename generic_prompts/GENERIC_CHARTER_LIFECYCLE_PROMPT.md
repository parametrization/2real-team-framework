# Generic Charter: Skill Lifecycle — Canonical Order and Preconditions

## Purpose

A single source of truth for the **order, preconditions, and state effects** of
the lifecycle skills that bracket a **phase**, an **iteration/wave**, and a
**session**. When several skills write and verify shared status keys, drift
between "what the doc says runs next" and "what the skill actually checks"
causes skipped steps and double-writes. This template captures the pattern;
derive every cell by reading the corresponding `SKILL.md` at HEAD — where this
doc and a `SKILL.md` disagree, the `SKILL.md` is authoritative until the
discrepancy is filed and resolved.

## How to use this doc

- **New session, unsure what's next?** Find the row whose side effects you
  already have, and run the row below it.
- **Onboarding?** The diagrams show the canonical flow.
- **Adding or rearranging a lifecycle skill?** Update this file in the same PR.

## Conventions used in the tables

- **Precondition** names the status-file keys (or transcript signals) a skill
  checks before proceeding. `(none)` = no machine-checked precondition.
- **State written** lists the status-file keys a skill upserts. `(none)` = no
  state change; `(side-effect only)` = mutates external state (issues, PRs,
  branches) without writing status.
- **Counter ownership.** When a counter is written by one skill and verified by
  another (e.g. wrapup → retro), the writer is authoritative and the verifier
  loud-fails on mismatch. Call this out in an "Owner" column.

## Phase lifecycle

```
plan-phase ─▶ phase-review ─▶ (iteration lifecycle) ─▶ phase-review ─▶ …
```

| Step | Skill | Precondition | Side effects + state written | Next |
|------|-------|--------------|------------------------------|------|
| P0 | `/plan-phase {P}` | Board reflects current open-issue state across all repos; pre-phase drift audit STOPs if any open issue is missing from the board. | Reads board as authoritative backlog. Creates per-issue tickets with phase/assignee/category labels. Posts review comments per issue. Presents a proposed iteration structure for owner approval. (The phase plan doc is hand-authored from the approved structure.) | `/phase-review {P}` |
| P1 | `/phase-review {P}` | Phase plan doc exists (STOPs and directs to `/plan-phase` if missing). | Read-only diagnostic. Surfaces the tech-debt ratio against the exit gate. May edit the plan doc with owner confirmation. | `/wave-scope {P} {M}` (mandatory next; gates the iteration lifecycle) |

**Phase close-out:** no explicit close-out skill. A phase ends when every
tracking issue is closed and the tech-debt ratio is under the exit gate. A
subsequent `/plan-phase` marks the next phase.

**`/phase-review` cadence:** mandatory before every `/wave-scope` (gated by a
transcript check for a same-session invocation against the phase). May also run
on demand.

## Iteration / wave lifecycle

```
Start:  wave-scope ─▶ wave-start ─▶ board-audit ─▶ wave-kickoff
Mid:    retro, promotion-audit, watch-deploy, live-app pass   (on demand)
End:    wave-wrapup ─▶ wave-retro ─▶ promotion-audit ─▶ error-audit ─▶ wave-scope(next)
```

### Start-of-iteration

| Step | Skill | Precondition | State written | Owner | Next |
|------|-------|--------------|---------------|-------|------|
| W1 | `/wave-scope {P} {M}` | **Gate A:** `/phase-review` ran in this transcript. **Gate B:** owner-set theme written to status + meta-issue body has a `## Theme` heading. | Meta-issue body refreshed. Label churn applied. Upserts scope keys (reconciled-at, repos-in-scope, meta-issue, scope). | `/wave-scope` | `/wave-start` |
| W2 | `/wave-start {P} {M}` | Parks on clean default branch; STOPs on non-regenerable dirty state or unmerged local commits. | Parks the checkout on a fresh default branch. Prunes stale worktrees. Ensures the iteration label. Stamps active-iteration fields onto status. | `/wave-start` | `/board-audit` |
| W3 | `/board-audit` | Runs against the board and all repos; optional board-field options must exist for label sync. | Side-effect only: bulk-adds orphan issues to the board, bulk-syncs the iteration field from labels. Confirmation gate before any mutation. | `/board-audit` | `/wave-kickoff` |
| W4 | `/wave-kickoff {P} {M}` | `/board-audit` should have run. Scope reconciled-at must exist and post-date the prior iteration's completion. Repos-in-scope must be non-empty. A pre-flight check set (branch exists per repo, child-repo implementer rule, scope correctness, reviewer slate, agent naming, spawn-brief ordering). | Creates the iteration branch in every in-scope repo. Writes per-repo branch SHA + status. Labels issues, posts per-issue kickoff comments, posts an all-hands kickoff on the meta-issue. Status commit lands on the default branch. | `/wave-kickoff` | Implementation work; mid-iteration skills on demand. |

### Mid-iteration (on demand)

| Skill | Precondition | Side effects | When to run |
|-------|--------------|--------------|-------------|
| `/retro` | Active iteration (read from status). | Inline diagnostic only. No trust/feedback writes. | Mid-iteration checkpoint, after an incident, or for a quick pulse without full-retro overhead. |
| `/promotion-audit` | Resolves current iteration from status if not given. | Appends to the feedback log; writes a per-iteration audit log. May open auto-tier promotion PRs and file decide-tier issues. | Auto-invoked from `/wave-retro`. Standalone if drift is suspected. |
| `/watch-deploy {stg\|prod}` | A merge triggered (staging) or the owner approved (prod) a deploy. | Polls the deploy to terminal, classifies failures, attempts one bounded fix-forward on **staging only**, escalates otherwise. Never auto-remediates prod. | After any merge that triggers a staging deploy; for prod only after owner approval. |
| Exploratory / E2E live-app pass | Active iteration; a deployed app/service reachable. Browser-driving uses the operator's already-authenticated session (never enter credentials / drive SSO). | Drive the live app, exercise primary flows, file each finding per the bug→issue→PR workflow. Verify each finding at source before filing. | **At least once per iteration that touches a deployable surface** — catches live-env defects the CI/harness loop never exercises. |

### End-of-iteration

| Step | Skill | Precondition | State written | Owner | Next |
|------|-------|--------------|---------------|-------|------|
| W5 | `/wave-wrapup {P} {M}` | Repos-in-scope exists. Open PRs targeting the iteration branch exist or are resolved. | Merges approved PRs. Closes resolved issues. Cleans worktrees. Reconciles the knowledge base. Upserts the canonical counter keys (final PR count, changes-requested cycles, top concentration). Final-iteration-of-phase: opens the iteration→default-branch PR per repo and runs the reachability gate. May run the error-audit + memory-to-automation audit as fallback, guarded by run-markers to avoid double-execution. | `/wave-wrapup` for all counters (authoritative); `/wave-retro` verifies, never writes. | `/wave-retro` |
| W6 | `/wave-retro {P} {M}` | The counter keys exist (verified against PR-level recomputation; drift beyond a small tolerance blocks the retro until reconciled). Runs the librarian and board-audit before assessments. | Updates the trust matrix directly on the retro branch. Appends to the feedback log. Invokes `/promotion-audit`; invokes the error-audit + memory audit if run-markers absent. Auto-invokes `/wave-scope {P} {M+1}` if the next meta-issue exists; else surfaces a kickoff blocker. | `/wave-retro` for corrections + run-markers. Counters stay owned by `/wave-wrapup`. | `/wave-scope {P} {M+1}` |

### Drift surfaces this doc closes

- **`/board-audit` is an explicit `/wave-kickoff` precondition, not inferred.**
  Skipping it on the assumption that scope already synced the board left many
  issues with their board-field unset.
- **Counter-write ownership lives in `/wave-wrapup`, not `/wave-retro`.** The
  wrapup is the authoritative writer; the retro is the verifier and loud-fails
  on drift.
- **`/wave-retro` auto-invokes the next `/wave-scope`.** Make that edge visible
  from the lifecycle view, not buried in one skill.
- **Error-audit + memory audit run retro-side**, with wrapup as fallback; both
  guard with run-markers so the audit runs at most once per iteration.

## Session lifecycle

```
session-start ─▶ (session work) ─▶ handoff ┄writes handoff file┄▶ next session-start
```

| Step | Skill | Precondition | Side effects | Next |
|------|-------|--------------|--------------|------|
| S1 | `/session-start` | MANDATORY first action in every session. | Prunes worktrees; team orientation; reads the handoff file; reconciles the knowledge base for dirty files; runs the error-status check; reads status + may invoke `/board-audit` on observed drift; reads the feedback log for unapplied proposals. | Whatever the user asks for. |
| S2 | `/handoff [notes]` | Run before ending a session for richer context than the automatic stop-hook. | Writes the handoff file (auto-loaded next session); updates the memory index; echoes the handoff for cross-machine paste. | (end of session) |

A stop hook auto-writes a handoff after every response (throttled). The next
`/session-start` reads whichever handoff is freshest; manual `/handoff` adds
conversational context (decisions, discussion) the automatic hook cannot infer.

## Maintenance

- Hand-maintained. Any new lifecycle skill MUST add a table row and a flow node
  in the same PR.
- Any reordering (new precondition gate, moved run-marker) MUST update the table
  BEFORE the SKILL.md change lands.
- If a SKILL.md and this doc disagree, the SKILL.md is authoritative until the
  discrepancy is filed and resolved.

## Adaptation notes

- Rename "phase / wave / iteration" to your cadence; keep the three-bracket
  structure (phase, iteration, session) and the writer-owns / verifier-checks
  counter discipline.
- The status file is the backbone — pick one machine-readable file and route all
  cross-skill preconditions and counters through it.
