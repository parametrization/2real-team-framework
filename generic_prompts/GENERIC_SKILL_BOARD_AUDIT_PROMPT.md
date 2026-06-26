# Generic Skill: Project-Board Drift Audit

## Purpose

A periodic drift check between a **project board** (a planning view) and the
**actual issue state** across all repos in the org. Two failure modes are gated:

1. **Orphan detection** — issues that exist but are NOT on the board (invisible to
   any planning pass that reads the board).
2. **Iteration-field drift** — issues whose iteration label disagrees with the
   board's iteration single-select field.

The governing decision: **labels are canonical for iteration assignment; the
board's iteration field is a derived projection.** This skill is the sync
mechanism (skill-tier enforcement; a daily cron is a deferred escalation if drift
recurs).

> Adapt: "iteration label" / "iteration field" map to whatever cadence unit you
> use. Paths and project identifiers are placeholders.

## Background / why it drifts

An auto-add hook only catches issues created via the CLI in active sessions —
bot-created, manual-UI-created, and pre-hook issues all drift off the board
silently. (In one real audit, 37% of open issues were missing from the board.)

## Invocation patterns

- **Manual** — run ad-hoc when drift is suspected.
- **Wired into iteration-kickoff** — once before label-application, so kickoff
  sees a current board.
- **Wired into the retrospective** — once before retro analysis.
- **Wired into session-start** — drift report shown during orientation.

## Pre-requisite — iteration-field options exist

The board's iteration single-select field MUST have an option for every active
iteration (a deterministic label→option-name grammar). If an option is missing
for a label encountered during sync, report it and skip those issues' field-sync
(do NOT block; orphan detection still runs). Option creation is a one-time
owner/admin action.

## Workflow

### 0. (Optional) consult the read-only knowledge reference

If your project has an ontology/librarian consult convention, run it first. This
skill edits no source, but it may surface findings worth filing.

### 1. Fetch all open issues (with labels) across all repos

Fetch `url` AND `labels` in one call per repo. Compute, per issue, the expected
iteration-field option from its highest-numbered iteration label (issues with no
iteration label are omitted from the label map). Collect every open-issue URL
into one set.

**Robustness:** wrap each external call in a `timeout` and skip-and-warn rather
than hanging the whole audit on one stalled call. Iterate a **literal repo word
list** (not an unquoted scalar — some shells, e.g. zsh, do not word-split a
scalar, collapsing the loop to one bogus iteration). Use a high `--limit` so the
default page size doesn't silently truncate.

### 2. Fetch all board items (PAGINATE — connections cap at 100)

The board's GraphQL `items(first:)` connection **caps at 100**. Requesting more
errors out and returns **0 nodes**, which downstream reads as "every issue is an
orphan." Page with `first: 100` + a `$endCursor` cursor var +
`pageInfo { hasNextPage endCursor }`, let the paginator walk pages, then merge
them. A board-item count of **0** is a red flag — never run apply steps off a
zero-item fetch.

### 3. Detect orphans

Orphans = open-issue URLs NOT present in the board URL set (`comm -23`).

### 4. Detect iteration-field drift (in memory — no per-item network calls)

Cross-reference two maps already on disk: the expected option per issue (Step 1)
vs the board's actual field value (Step 2), via a single hash-join. Bucket rows:
- **DRIFT** — actionable: a mutation will change board state (label/field
  disagree, or label-absent but field-populated → clear).
- **NOOP** — no label AND field already unset (already in desired state) — count
  separately, keep OUT of DRIFT so apply emits no redundant clears.

### 5. Confirmation gate (mandatory)

Print the drift report (orphans, actionable drift, no-op equivalents, missing
options) and PAUSE for explicit confirmation. Key the gate off **actionable**
drift + orphan counts only. Any answer but yes aborts with no mutations made.

### 6. Bulk-add orphans

Add each orphan to the board (`while read` over the newline list, not a `for` over
an unquoted scalar). The add operation may **silently no-op** on some platforms —
if the orphan count doesn't drop next run, fall back to the GraphQL add mutation.

### 7. Bulk-sync the iteration field via GraphQL

Fetch the field's option IDs once. Per drift row, run the field-update mutation
with the expected option's ID (or the clear mutation for label-absent rows). Warn
on any missing option.

### 8. Read-back verify

Re-fetch the board and recompute orphans + drift. Success = **actionable drift ==
0 AND orphans == 0**. The no-op bucket is expected non-zero on a healthy board and
MUST NOT fail the read-back. If actionable drift/orphans remain, surface it — the
mutations may have silently no-op'd.

### 9. Report

Orphans added, fields synced, no-op equivalents (informational), missing options,
read-back drift remaining.

## Skill-authoring notes — API access patterns (reusable)

Any skill querying a GraphQL/REST API over a growing collection should heed:
- **GraphQL connections cap at 100 — always paginate.** Never raise `first:` to
  "fit the dataset."
- **Derive in memory; don't loop network calls per row.** Use a bulk fetch +
  in-memory hash join, not an O(collection) per-item view loop.
- **Wrap each external call in a `timeout` and skip-and-warn.**

A cheap regression lint can flag `first: <n≥100>` inside GraphQL blocks across the
skills tree.

## Adaptation Notes

- The **labels-canonical / field-derived** decision is the heart of this skill;
  decide it explicitly for your tool.
- The confirmation gate and read-back verify make it safe to wire into automated
  lifecycle surfaces.
- Silent-no-op fallbacks (board add, field sync) matter on platforms deprecating
  classic-project CLI operations.
