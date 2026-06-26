# Generic Skill: Phase Review (Track-Check Before Scoping)

## Purpose

A **phase-level track check**, mandatory before scoping the next iteration. It
surfaces what's done, remaining, and blocked across a phase's end-state criteria,
plus the tech-debt ratio — so the owner chooses the next iteration's theme
**deliberately, not reactively**. A "phase" is a grouping of iterations
(cadence units) toward a set of end-state criteria.

> This is NOT a per-iteration retrospective, NOT the scope-reconciliation step,
> and NOT phase creation. It does not pick the next theme (owner's call) and does
> not modify the phase plan without owner confirmation.

## When to use

- **Before every scope-reconciliation pass.** The scope skill should block until
  phase-review has run in the same session.
- On demand, to check phase health.

## Workflow

### 0. Inputs

- `{P}` — phase number/identifier.

### 1. Load the phase plan

Read the phase plan doc. If missing, STOP and direct the owner to the
phase-planning skill first (the phase plan doc is hand-authored — without it,
phase-review has nothing to check against).

### 2. Pull current state of each tracking issue

Extract tracking-issue references from the phase plan and pull live state for
each. Categorize each criterion:
- **Done** — tracking issue closed.
- **In flight** — open + has linked open PRs.
- **Open / not started** — open + no linked PRs.
- **Blocked** — open + has a blocker label or commented blocker.

### 3. Tech-debt ratio (phase exit gate)

Compute two ratios from issues filed since the phase started:
- **New filed this phase**: tech-debt issues / total new issues.
- **Cumulative open**: open tech-debt issues / total open issues.

If either exceeds the phase's threshold (e.g. 10%), flag — phase exit gate not yet
met, regardless of per-criterion checkboxes. Run the same query across all repos
for a cross-repo view and aggregate.

### 4. Surface to owner

Present a single status block: a criterion table (#, criterion, tracker, state,
notes), the tech-debt ratios vs the gate, and an overall **phase exit gate:
MET / NOT MET** line.

### 5. Allow phase-plan revision

Ask the owner: has the track drifted (criteria thought-done but actually open, or
new urgent items)? Should the phase plan be revised before scoping? If yes, edit
the phase plan doc with the owner's input and commit (orchestrator identity).

### 6. Hand off to scope-reconciliation

Print "phase review complete — ready to scope the next iteration." The scope skill
checks that phase-review ran in this session and proceeds.

## Adaptation Notes

- The **mandatory-before-scoping** gate is the point: it forces a deliberate
  phase-health read before theme selection, preventing reactive "whatever hurt
  most in retro" theme drift.
- The **tech-debt exit gate** is a concrete, queryable phase-health signal; tune
  the threshold to your project.
- Keep it read-and-propose: it never picks the theme or rewrites the plan without
  owner confirmation.
