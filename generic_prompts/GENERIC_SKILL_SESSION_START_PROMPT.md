# Generic Skill: Session-Start Protocol

## Purpose

The **mandatory first action in every session**. It establishes situational
awareness — worktree hygiene, team model, prior-session handoff, knowledge-base
freshness, error-monitor state, iteration/phase orientation, and process-doc
freshness — before any real work begins. It begins no implementation work, files
no issues, modifies no process docs; it only orients.

> Invoke this BEFORE reading the user's message or running any other tool. The
> user's actual request is handled AFTER it completes. Present results in a single
> concise status table at the end. Steps that are independent SHOULD run in
> parallel.

> **Repo-root anchoring (load-bearing):** anchor the repo root to the **parent/org
> repo** deterministically — use the parent of `git rev-parse --git-common-dir`
> (NOT `--show-toplevel`, which resolves to a worktree when invoked from one) and
> verify it against a known parent marker file. Each step's shell block re-derives
> it, since skill blocks run as independent shells.

## Workflow (steps may run in parallel where independent)

### Step 0 — Worktree + child-checkout hygiene

Worktrees accumulate in the parent AND every child repo. Iterate parent + all
child repos with a **verify-merged-then-remove guard**:
- **Auto-remove** a worktree only when its HEAD is an ancestor of that repo's
  `origin/main` (fully merged — safe to drop).
- **FLAG (list, do not remove)** any unmerged or **locked** worktree — surface for
  a manual call; never auto-remove unmerged work.

Also fast-forward the parent and embedded child checkouts toward `origin/main`
**only when clean and strictly-behind** (`--ff-only`, never force/discard); FLAG
any dirty/diverged/feature-parked checkout. A child sitting many commits behind is
a root cause of stale on-disk config and wrong-conclusion reads.

**Shell-safety notes that recur throughout:** iterate **literal word-lists** or
`while read` over newline lists (an unquoted scalar is not word-split in some
shells, e.g. zsh, collapsing the loop); feed loops from a **temp file**, not
process substitution / here-strings, where the permission engine requires
statically-analyzable syntax and where a `| while` subshell would drop accumulated
arrays.

### Step 1 — Team orientation

If the harness provides a single implicit team per session (no team
create/delete tools), there's nothing to tear down — confirm the model and move
on. Spawning is done by the orchestrator only; spawned agents join the implicit
team and cannot themselves spawn (hub-and-spoke).

### Step 2 — Handoff check

Read the session-handoff file from project memory. Extract: what was done last
session, what's next, current branch / open PRs / open issues, any user notes.
Summarize in 2–3 sentences (or "no handoff" if absent).

### Step 3 — Knowledge-base (ontology) freshness — both layers

**3a. Semantic overlay:** run the resolver (`/ontology-rebuild`); if 0 dirty
files, report current, else process + commit.
**3b. Structural index:** compare the commit that last generated the index against
source files changed since; if stale, regenerate (run the generator + aggregator)
and commit. **Non-fatal** — a generator failure must NOT block session-start;
report and move on (the index stays at its last committed state).

### Step 4 — Error-monitor check

Run the error-monitor status viewer. Report hook active/inactive, error count, new
errors since last session. If 5+ unprocessed errors, flag for the attack/triage
skill.

### Step 5 — Iteration / phase orientation

Read the central status file + open issues. Report: active iteration + phase,
whether the status file is stale, open issue count + blockers, open PRs. If the
board view and open-issue counts diverge (labeled issues missing from the board,
or field out of sync with labels), invoke the board-drift audit to detect and
(with confirmation) repair.

### Step 5a — Red default-branch workflow detection

Surface any **publish/deploy/release-class workflow whose latest default-branch
run FAILED**, across all repos (a red publish on `main` rots silently — unlike a
red lint at PR time). For each red run, best-effort **classify the cause** by
inspecting the failed log for base-image-CVE signals (tag those as "base-image
drift — fix-forward the base image, not a code regression"). Non-fatal: a log-fetch
failure degrades to an unclassified tag, never a false all-green. Resolve the repo
set from the canonical `current_iteration` pointer (NOT a max over iteration
numbers — retained prior-phase scopes would mis-select).

### Step 5b — Iteration-merged-but-unwrapped nudge

Surface an iteration whose PRs **merged to main but was never formally wrapped**
(active flag still true, no wrap marker, AND 0 open iteration PRs) — scoped to the
**current** iteration only (iteration keys may not be phase-namespaced, so an
"any active+unwrapped" scan false-fires on stale prior-phase ghosts). Non-fatal:
degrade to a benign verdict on missing keys / failed probe.

### Step 5c — Iteration-branch reachability / merge-model check

Surface mid-iteration any iteration-branch commit not reachable from
`origin/main`, classified against the iteration's declared **merge model**: a
`direct-to-main` iteration with commits on its branch is a hard VIOLATION; a
`branch` iteration ahead-with-open-integration-PR is OK; ahead-with-no-PR is an
ADVISORY stranding-risk. Non-fatal.

### Step 6 — Process-doc (charter) freshness

Read the tail of the feedback log. Check for: unapplied retro proposals, new
hooks/skills since the last process-doc update, pending personnel actions. Report
findings or "current."

## Output format

A single status block with one row per step (worktree, child checkouts, team,
handoff, ontology [semantic + structural], error monitor, iteration, red runs,
wrap state, reachability, process-doc), THEN address the user's actual request.

## What this skill does NOT do

- No implementation work, no issues/PRs, no process-doc/roster edits — orientation
  only.

## Adaptation Notes

- The **deterministic parent-repo anchoring** is critical in a parent/child
  multi-repo layout; drop it for a single repo.
- Every detection step is **non-fatal and degrades to a benign verdict** — a
  session-start step must never hard-block the session.
- Steps 5a–5c are accreted from real silent-failure modes (rotted publish on main,
  unwrapped-but-merged iteration, stranded iteration branch); keep only those your
  workflow can actually hit.
