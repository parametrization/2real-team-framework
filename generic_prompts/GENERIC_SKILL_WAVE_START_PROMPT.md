# Generic Skill: Iteration Start (Infrastructure Setup)

## Purpose

Initialize infrastructure for a new iteration (cadence unit / "wave"): park the
orchestrator's checkout on a clean, up-to-date `main`, clean up stale worktrees,
and ensure the iteration label. It is the **setup** step. Full planning — the
integration-branch creation and issue assignment — belongs to the kickoff skill
that runs after this.

The arguments are team name + phase + iteration identifiers.

## Workflow

### 1. Clean stale worktrees

Prune leftover worktrees and list remaining ones. Report what was pruned; if
active worktrees remain, list them and confirm with the user before proceeding
(they may belong to in-progress work).

### 2. Park the orchestrator's checkout on fresh `main`

Get the checkout onto a clean, up-to-date `main` **before** any branch/status
work — otherwise an iteration can run on a stale, already-merged feature branch,
and any local commit lands against a stale base.

**Guard, don't auto-discard** — only regenerable session churn may be set aside:
- **Guard A:** non-regenerable uncommitted changes → **STOP** (list them, do not
  discard).
- **Guard B:** current branch ahead of `origin/main` (unmerged local work) →
  **STOP**.
- Otherwise: stash only the known regenerable churn (recoverable), `checkout main`,
  `pull --ff-only` (never a merge commit), and **assert** you're on a clean `main`
  before proceeding.

If either guard STOPs, surface the reason and wait — do not work around it. (Avoid
shell-specific idioms so the block runs identically across shells.)

### 3. Determine base branch

Base is `main` (each iteration merges to main at its own wrap-up, so the prior
iteration is already integrated). The prior iteration branch is **retained, not
deleted**, and serves only as a safety-net reference. If the prior iteration
branch exists but is unmerged, warn the user — but still cut from `main`.

### 4. Branch creation — delegated to kickoff

Do NOT create the integration branch here. Branch creation for **every** repo in
scope is owned by the kickoff skill (cut via API from `origin/main` HEAD,
idempotent, race-safe, no clean local checkout required). Stay on `main`.

### 5. Create the iteration label + standard category labels

Ensure the canonical iteration label exists (create if missing). Also ensure
standard category labels exist (tech-debt, feature, bug, security, infra, process).

### 5a. Per-phase key reset — RETIRED (use global monotonic ids)

There is no per-phase reset. If iteration ids are a single **global monotonic
counter** that never resets, two same-ordinal iterations in different phases get
distinct keys by construction — the collision class is gone, so there is nothing
to reset. Phase becomes a **derived display attribute** (`iteration_phase` +
`iteration_phase_ordinal`), written alongside scope, never part of the key.

### 6. Update the central status file — via atomic API write on `main`

Set the active-iteration fields. This is a **main-targeting** status write, so use
the **atomic API put-contents** recipe (fetch current sha + content, set fields,
re-encode, put with author/committer, read-back-verify) — do NOT local
commit-then-push (that re-introduces the orphan / stale-tree hazard and races the
remote).

### 7. Run a mid-iteration health-check retro (if not the first iteration)

Capture a quick health check from the prior iteration so carry-over items surface.

### 8. Report

Checkout parked on clean `main` @ sha; integration branch (created by kickoff, not
here); base; label (created/existed); worktrees pruned; status file updated on
`main`.

## What remains manual

- User confirms whether active worktrees should be removed.
- The Step 2 guard STOPs (does not auto-discard) on non-regenerable dirty state or
  unmerged commits — user resolves before re-running.
- The skill does not create the branch, assign issues, or post kickoff comments.

## Adaptation Notes

- The **guard-don't-discard** park-on-main logic is the safety core: only
  regenerable churn is ever set aside; real work always STOPs.
- The **atomic put-contents** write for main-targeting status is what prevents the
  local-orphan / stale-tree failure mode.
- Global-monotonic iteration ids eliminate the per-phase reset entirely — prefer
  them over per-phase numbering.
