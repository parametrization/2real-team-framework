# Generic Skill: Iteration Issue Audit (Close Orphaned Issues)

## Purpose

Audit the open issues for an iteration (cadence unit / "wave") against its merged
PRs, and close any that were resolved but never auto-closed. Catches issues whose
implementing PR forgot the `Closes #N` reference, or whose iteration-branch merge
didn't trigger auto-close.

The arguments are the phase + iteration identifiers.

## Workflow

### 1. List merged PRs for the iteration

List PRs merged to the iteration's integration branch (number, title, body, head
branch).

### 2. Extract issue references from PRs

For each merged PR, parse the body for `Closes #N` / `Fixes #N` / `Resolves #N`.
Build a map `{issue → [PR, PR-title]}`.

### 3. List open issues for the iteration

Query the iteration label (and any grandfathered legacy label form — union them,
running separate queries since multiple label flags AND together).

### 4. Identify orphans

An orphan is an open issue that is iteration-labeled AND was referenced by a
merged PR's close-keyword but not auto-closed. Cross-reference the two lists.
Also catch issues implemented but missing the `Closes` reference — match by the
branch-naming convention (`{initials}/{issue-number}-*`).

### 5. Report findings (before acting)

Present a table (issue, title, status, implementing PR, action) plus counts of
orphans found and issues with no implementing PR. **Do NOT close anything until
the user confirms.**

### 6. Close confirmed orphans

For each confirmed orphan, close with a comment naming the resolving PR and the
integration branch it merged to, and add a `fixed-in-<iteration>` label.

### 7. Report summary

Issues closed; remaining open (no implementing PR); already-closed (correctly
auto-closed).

## What remains manual

- User approves all closures before they execute.
- Issues with no implementing PR need manual triage (defer / reassign / won't-fix).
- The skill relies on close-keyword references + branch naming — it does not
  verify the PR actually implemented the issue.

## Adaptation Notes

- This is the **end-of-iteration cleanup** twin of the project-board drift audit:
  one reconciles board membership, this one reconciles issue closure vs merges.
- The **branch-naming fallback** (match `{initials}/{issue}-*`) catches the common
  "forgot the Closes line" case that close-keyword parsing alone misses.
- Iteration-branch merges often do NOT fire close-keywords (those typically only
  fire on default-branch merges), which is exactly why this audit is needed.
