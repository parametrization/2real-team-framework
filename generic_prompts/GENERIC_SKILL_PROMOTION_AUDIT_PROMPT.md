# Generic Skill: Promotion-Pipeline Audit

## Purpose

A **deterministic audit** of the artifact-promotion pipeline. Rules migrate
upward along an **enforcement hierarchy** as evidence accumulates:

```
memory  →  process-doc/charter  →  skill  →  hook
```

The skill auto-promotes artifacts that have crossed thresholds and are safe to
auto-apply (AUTO tier), files draft issues for ones that need human decision
(DECIDE tier), and writes a per-iteration audit log. Every classification step is
backed by a **pure function** so the same input yields byte-identical output.

The optional argument is the iteration name (defaults to the current iteration
from the central status file).

## The promotion ladder

| From | To | Trigger |
|---|---|---|
| memory | process-doc | `promotion_target: doc` AND retro-citations ≥ threshold AND status active |
| process-doc | skill | a section promotion-target marker AND skill-invocation signal ≥ threshold |
| skill | hook | a hook promotion-target marker AND invocation signal ≥ threshold |

**Skill→hook ALWAYS produces a DECIDE-tier draft — never auto-applies** (hooks are
security-sensitive).

**Marker convention:** recognize a small fixed set of provenance marker shapes
(e.g. an HTML-comment "promoted from memory" marker and a "promotion provenance"
block). Any change to the recognized shapes must update the convention doc first,
then the parser, then this skill — in that order, one change-set.

## Workflow

### 1. Run the canonical driver (do NOT hand-roll the classify sequence)

Run the deterministic driver script (see `GENERIC_SKILL_PROMOTION_AUDIT_RUN_PROMPT.md`)
for the human-readable table, and again with a machine-readable flag for the
decisions that drive artifact emission. **Do not inline the classify call sequence**
— hand-rolling it once mis-derived an empty signal slug and produced dozens of
spurious AUTO decisions. The driver wires signal derivation, slug resolution, and
thresholds in exactly one place.

- **Iteration resolution:** with no arg, read the current iteration from the
  status file and emit the canonical form.
- **Audit date** is pinned to the iteration boundary timestamp (never the wall
  clock), so re-runs on unchanged state are byte-identical.
- The driver does ONLY classification + rendering — no external calls, no
  artifacts.

### 2. How the driver classifies (reference — do not re-implement)

The driver reads inputs (memories, process-doc sections, skills, the
already-promoted set) then routes each candidate to its tier-specific classifier.
There is no single `classify()` entry — each transition has a distinct signature
because the signal sources differ (retro-citations for memory→doc; skill-invocation
counts for doc→skill and skill→hook). Decision kinds:

- **AUTO** — thresholds met, target is doc/skill, NOT already promoted.
- **DECIDE** — target is hook (always), OR a `requires_decision` override, OR
  ambiguous signals.
- **KEPT** — promotion-target none / thresholds unmet / active with no intent.
  (A **stale-opt-out** sub-class: opted-out but the signal is well past threshold —
  stays KEPT but is rendered separately so operators can spot drift.)
- **SUPERSEDED** — status superseded/enforced-elsewhere with an explicit reference.
- **ALREADY-PROMOTED** — name appears in the already-promoted set.

### 3. Produce artifacts

Resolve the **current iteration label** once at the top; every artifact (AUTO PRs
AND DECIDE issues) MUST carry it so the board's iteration-field sync routes it to
the current column — missing the label lands artifacts off-board/off-iteration.

**AUTO artifacts:**
- memory → doc: apply the doc-section template, append to the right doc, mark the
  memory superseded-by the doc section.
- doc → skill: apply the skill-scaffold template, write the new skill, add a
  back-reference marker after the section's promotion marker.
- Commit under the standards/quality role identity (per-commit identity flags;
  pass the message via file, not heredoc). Branch, push, open a PR following the
  PR template + required labels (process/enhancement/iteration). **Validate the
  labels stuck** (label-apply can silently no-op). Add to the board with
  read-back verification. Assign required reviewers via your spawn mechanism (not
  a self-approve API call). AUTO artifacts land via PR (review gate), not direct
  commit.

**DECIDE artifacts:** apply the hook-draft template to generate an issue
title+body, create the issue with the same label set + board treatment + read-back
verification.

### 4. Render the audit table

The driver's default stdout IS the table (AUTO-PROMOTED / REQUIRES-DECISION /
KEPT [+ stale-opt-out sub-list] / SUPERSEDED+ALREADY-PROMOTED) followed by a
summary line. Capture that stdout rather than re-rendering by hand.

### 5. Write outputs (both)

1. **Append to the feedback log** — under the current retro entry if running
   inside a retro, else a fresh dated entry at the top.
2. **Standalone log** — always write to a per-iteration audit-log file
   (overwrite if re-run).

### 6. Report

Two-line summary: counts per decision category + a link to the standalone log.

## Determinism

The audit MUST produce byte-identical output on unchanged state. The driver
guarantees this: sort every list by a stable key; pin dates to the iteration
boundary (never `now()`); never count invocations for an empty/blank slug; never
read transcripts; never call nondeterministic external tools (the only external
calls are issue/PR creation in Step 3, isolated from classification).

## What this skill does NOT do

- Never auto-promotes skill → hook (always DECIDE).
- Never mutates memory bodies except a `superseded_by` update on auto-promotion.
- Never scans conversation transcripts — signals are docs, feedback log, and git
  history only.

## Adaptation Notes

- The **pure-function classification + thin nondeterministic artifact shell** is
  the reusable architecture: determinism lives in the driver, side effects in the
  skill prose.
- The **empty-slug footgun** (a blank skill slug matching ~every commit via
  `--grep=/`) is the canonical regression — guard it at the root.
- Tune the promotion threshold and the marker shapes to your project; keep
  skill→hook DECIDE-only for security.
