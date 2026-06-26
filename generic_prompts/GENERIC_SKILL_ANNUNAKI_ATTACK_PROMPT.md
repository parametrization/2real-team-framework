# Generic Skill: Error-Log Attack / Triage

## Purpose

The **action** counterpart to the error-monitor status viewer
(`GENERIC_SKILL_ANNUNAKI_PROMPT.md`). It processes the captured error log:
deduplicates, classifies each unique error, proposes the most-automated
preventative fix, files tracking issues, implements the fixes, and clears the
processed errors.

The governing principle is an **enforcement hierarchy**: prefer the most
deterministic, automated remedy — **hook > skill > process-doc update**.

> Adapt: root all paths at your repo top-level. "Issue", "label", and "PR" map to
> whatever tracker/VCS-review system you use.

## When to run

- **Preferred:** during the iteration retrospective, so findings feed the retro's
  process-change proposals.
- **Fallback:** during iteration wrap-up. Guard both surfaces with a shared
  run-marker (e.g. `iteration_<id>_attack_ran_at`) so the attack runs at most
  once per iteration; whichever surface runs first wins.
- Manually, when the log has accumulated enough entries to be worth processing.

## Workflow

### 1. Read and deduplicate the error log

Read **only genuine errors** via the shared trace-filtering reader (skip
blank/corrupt lines AND benign dispatch/diagnostic traces). If the genuine-error
count is 0, report "No errors to process" and exit. Do NOT process the benign
trace log — it ages out on its own.

Deduplicate:
- Group errors by **normalized command prefix** (first ~2 tokens, e.g. `git commit`).
- Within each group, dedupe by **error pattern** (the matched-pattern field).
- Keep the most recent occurrence of each unique error plus an occurrence count.
- Back up the original log before rewriting the deduplicated version.

### 2. Classify each unique error

| Classification | Criteria | Proposed fix |
|---|---|---|
| **Hook candidate** | Preventable by validating input before the command runs (missing flags, wrong branch, bad args) | Pre-exec hook |
| **Skill candidate** | Occurs during a repeatable multi-step workflow that could be codified | A skill |
| **Process update** | Stems from a process gap or unclear convention | Update the relevant process doc / charter |
| **One-off / noise** | Transient, environmental, not actionable (network timeout, typo) | Skip — remove from log |

Preference order: **Hook > Skill > Process update.** Always prefer the most
automated option.

### 3. Determine the target iteration/label

Find the active iteration label (open issues carrying it); if none is active,
derive the next label from the most recently closed iteration. Store it for
issue creation.

### 4. File a tracking issue per non-noise error

Create an issue per classification with: the error pattern, occurrence count,
most-recent timestamp, the command, an error excerpt, the proposed fix type +
description, and acceptance criteria (fix implemented + tested; pattern no longer
triggers; hook registered / skill authored / process doc updated as applicable).
Apply the iteration label + a monitor tag + the fix-type tag. Let the
board-auto-add hook (if any) place it on the project board.

### 5. Implement fixes immediately

- **Hooks:** create the hook script, register it in settings under the right
  event, test by simulating the error condition.
- **Skills:** create the skill directory + workflow doc, verify it appears.
- **Process updates:** edit the relevant doc and add a rationale.

Follow your team's branch/identity/review conventions (feature branch, per-commit
identity, link the PR to the issue, required reviewers).

### 6. Clear processed errors

After issues are filed and fixes implemented, clear the processed entries (keep
only anything explicitly classified as noise, which ages out naturally).

### 7. Report

Print a summary: total processed, deduplicated count, noise removed, and a table
of `# | error pattern | classification | issue | PR | status`.

## Integration with retro / wrap-up

When called from either lifecycle surface: use the current iteration label
(already in context); if no errors, report "no errors captured this iteration",
**still write the run-marker**, and continue. Fold any created fixes into the
iteration totals and the retro's process-change proposals. On completion, write
the run-marker timestamp to the central status file.

## What remains manual

- Owner approval before merging fix PRs.
- Cross-team fixes need coordination.
- If a proposed hook/skill conflicts with existing automation, flag for review.

## Adaptation Notes

- The **run-marker** is what makes the dual-surface (retro + wrap-up) safe —
  without it the attack double-runs.
- The **enforcement hierarchy** (hook > skill > doc) is the load-bearing reusable
  judgment: codify deterministically wherever possible.
- Keep the genuine-error/benign-trace split from the status-viewer skill — never
  classify a dispatch trace as an error.
