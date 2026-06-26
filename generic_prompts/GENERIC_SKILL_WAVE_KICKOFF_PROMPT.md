# Generic Skill: Iteration Kickoff (Planning + Branch + Labels + Spawn)

## Purpose

Automate the kickoff of an iteration (cadence unit / "wave") for a team: create the
integration branch in every in-scope repo, manage labels, apply issue labels,
post kickoff comments, and produce an execution plan. Arguments: team name +
phase + iteration identifiers.

> All steps iterate the iteration's **in-scope repo list** from the central status
> file. Shell loops must be zsh-safe (`while read` over newline lists, not `for`
> over an unquoted scalar).

## Workflow

### 0. Board-drift audit (mandatory precondition)

Run the board-drift audit once so the project board reflects current open-issue
state and the iteration field is in sync. Without a current board, downstream
steps silently miss orphan issues. Labels are canonical; the field is derived.

### 0a. Verify scope was reconciled (mandatory precondition)

The status file MUST carry an `iteration_<id>_scope_reconciled_at` timestamp
written by the scope skill; if a prior-iteration retro timestamp exists, the scope
timestamp must post-date it. Absent scope timestamp → STOP. (Permissive fallback:
when no prior-iteration timestamp exists — first iteration of a phase / fresh
project — skip the staleness comparison.) Deterministic JSON read, no side effects.

### 0b. Derive in-scope repos (mandatory first step)

Read the in-scope repo list from the status file. Missing/empty → STOP (the
iteration is not properly scoped). Provide a path-resolution helper (the parent
repo IS the repo root; each child lives under it).

### 0c. Pre-flight checklist (Pattern-F mitigation)

Before any branch/label/spawn work, complete a checklist per in-scope repo:
integration branch exists, implementer roster confirmed (child-repo implementers
come from that child's own roster), every scoped issue's **actual change repo** is
correct (**RELOCATE if not** — see below), 2-reviewer slate drafted per PR, agent
naming pattern, spawn-brief ordering (reviewer-class identity ahead of
implementer-class). Any failure → STOP. Paste the checklist table into the
meta-issue kickoff comment as the audit trail.

### 0c-relocate. Mis-filed-issue relocation (standing rule)

A scoped issue whose code lands in a **different repo than it's filed in MUST be
relocated at kickoff** — noting it is not enough. For each: re-create in the actual
repo(s) with a faithful body + provenance line (one issue per repo if the work
splits); board + scope each; close the source with a relocation comment + remove
the iteration label + close as "not planned". Relocate BEFORE persisting the slate
and BEFORE any label-apply, so scope + kickoff comments reference the real repos.

### 1. Create the integration branch in every in-scope repo

For **every** in-scope repo, create the integration branch from `origin/main` via
**API** (no clean local checkout required — intentional). **Idempotent:**
distinguish exists-clean / exists-ancestor (main advanced — expected) /
exists-drift (someone pushed a non-main commit — surface, do NOT overwrite). Honor
a dry-run env flag (print the plan, skip the POST). Print a per-repo status table.

**Stop-the-line:** any error, or any exists-drift (without explicit sign-off).
Persist results to the status file under `iteration_<id>_branches` (the
branch-scoped write may use the local-jq pattern; **any write to `main` must use
put-contents**, Step 1a).

**Declare the merge model (mandatory — one model per iteration):** exactly ONE of
`branch` (per-issue PRs base on the integration branch; the integration→main PR
opens at wrap-up) or `direct-to-main`. Mixing them within an iteration is the
stranding bug. Record it so the session-start reachability check can enforce it.

### 1a. Status commits — atomic put-contents on `main`

Any main-targeting status write (kickoff active state, reconciliation, completion)
MUST use the atomic API put-contents flow (fetch sha+content → build new content →
re-encode → PUT with author/committer → read-back-verify), not local-commit-push
(that risks a local orphan that only surfaces at wrap-up). **Advance the
`current_iteration` pointer** in the kickoff write — downstream audits derive the
current iteration labels from it; a stale pointer blocks the next retro.

### 2. Create the iteration label + 2a. pre-create the board field option

Create the iteration label if missing. **Before label-apply,** pre-create the
board's iteration-field option (idempotent, read-back-verified) — otherwise the
field-sync hook fires an unresolvable "no option" capture for every labeled issue.
Stop-the-line if option creation fails (likely a missing project scope).

### 3. Pre-iteration auth/scope audit

Verify the token has the scopes this iteration needs (repo, org-read, project,
workflow). A missing scope mid-iteration wastes time chasing auth flows. Instruct
the user to refresh any missing scope before proceeding.

### 4. Pre-iteration CI triage

Verify CI health on `main` across in-scope repos. For any red repo, file a
"triage before iteration" issue and present a summary table so engineers aren't
confused by pre-existing failures.

### 5. Cross-reference issues against recent merges

Check whether any iteration issue was already resolved by a recent merged PR
(close-keyword references). Flag matches and wait for confirmation before
assigning; drop confirmed-resolved issues.

### 6. Collect issues + assignments

Prompt for issue numbers, assignee per issue, and peer-review pairings. Validate
all assignee labels exist; create missing ones.

### 7. Label all issues

Apply the iteration label + assignee label per issue. **The kickoff comment is
posted automatically** by a hook firing on the label-apply (reads the assignment
row from the scope structure; idempotent; skips the meta-issue; failure-tolerant).
Optional per-iteration orchestration scripts may automate bulk labeling/board-adds
(write them to a tracked, non-ephemeral location).

### 8. Post the meta-issue all-hands kickoff comment

A single all-hands comment on the iteration meta-issue summarizing theme,
participants, and tier breakdown. Skip if there's no meta-issue.

### 9. Ontology-librarian — both bakes required (mandatory)

Two independent hooks enforce this:
**(a)** the orchestrator **bakes** the librarian output into the spawn prompt under
a literal `## Ontology Context` heading — a hook blocks the spawn if absent
(required for implementer-class spawns; optional for coordinator-class).
**(b)** the spawn prompt instructs the agent to **run the librarian themselves** as
their FIRST action — a second hook scans the agent's own transcript and blocks
their edits until they do. Baked context alone is insufficient.

### 9a. Delegation pattern (hub-and-spoke)

Only the orchestrator spawns; managers request spawns via message with full
context. Single implicit team per session. **Every implementer spawn sets
worktree isolation.** Pull the manager's reviewer pairings / branch names /
ownership into each implementer prompt.

### 9b. Track each spawn with a task entry (mandatory)

Every implementer spawn gets a corresponding task entry (subject = issue ref +
slug, owner = implementer) at spawn time. The task list is the live ledger — a
zero-output stall (no branch/PR/commit) is invisible without it. Apply a liveness
threshold (after two idle notifications with zero artifact, auto-flag for takeover).

### 10–11. Execution plan + report

Generate a structured plan (priority ordering — hotfixes → security → bugs →
features; issue table; cross-PR dependencies; estimated parallelism). Present it;
do NOT begin implementation until the user approves.

## What remains manual

- User approves the execution plan and decides included issues.
- Cross-team dependency resolution needs lead coordination.

## Adaptation Notes

- The **pre-flight checklist + mis-filed-issue relocation** are the heart of the
  "plan correctly before spawning" discipline.
- The **both-bakes** librarian enforcement and the **task-ledger per spawn** are
  the two most transferable anti-stall mechanisms.
- One merge model per iteration, declared at kickoff, is what makes mid-iteration
  reachability enforcement possible.
