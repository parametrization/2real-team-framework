# Generic Charter: Work Delegation & Issue Management

## Purpose

A template for how a multi-repo team turns requirements into tracked,
reviewed, assigned issues — and how it keeps those issues honest (verified
against real code state, on a single authoritative board) before any
implementation starts.

## Delegation flow

1. **The senior coordinator decomposes cross-repo requirements** and delegates
   each to the appropriate manager based on domain.
2. **The assigned member creates issues** in the appropriate repository with
   clear acceptance criteria.
3. For cross-repo work, the coordinator creates a **meta-issue** in the parent
   repo that links to the per-repo issues.

## Issue review process

Every newly created cross-repo issue gets a review pass from each relevant role
(dependency/timeline, release/deployment, standards/conventions). **If a
reviewer has nothing significant to add, they add nothing** — no boilerplate.
The goal is early visibility, not gatekeeping.

## Work gate: issues before implementation

No member may begin (or delegate) implementation until ALL issues for the
current initiative have been:

1. **Created** — the full set covering the initiative's requirements exists.
2. **Reviewed** — every issue passed the review process (each reviewer either
   commented or passed).

Only then does the coordinator signal that implementation may begin. This
ensures the whole initiative is planned, visible, and vetted before any work.

## Premise verification at origin HEAD

**Any issue whose body cites a gap, bug, or missing feature in code MUST have
that premise verified against the target repo's default-branch HEAD at filing
time** — not against a sibling issue's body, a meta-issue snapshot, another
repo's description of the gap, or memory of the codebase.

Verification means at least one of:
- A contents-API read confirming the cited file/code state at HEAD.
- A code search confirming the claimed-missing symbol genuinely absent at HEAD.
- A `git log <path>` confirming no later commit already addressed the gap.

**Why:** a "new" gap filed from a stale snapshot whose work already merged costs
a phantom scope row, an implementer reassignment, and a board repair. This is
the issue-filing counterpart of the implementer "investigate before implement"
rule and the reviewer "origin over local" rule: **every role class that asserts
repository state verifies it at origin first.** Applies to all filing surfaces:
the coordinator, members, file-bug skills, and any auto-filing skill.

## Wave/iteration planning — the board is authoritative

Planning MUST begin with the **full project board** as the candidate pool, not
the subset of issues carrying an iteration label or listed in a meta-issue body.

1. **Source of truth:** the project board. Every open issue across all repos
   should appear there.
2. **Labels are post-scoping tags**, not pre-scoping filters. In-scope issues
   get labeled when planned; labels document decisions, they don't bound what
   could have been considered.
3. **Meta-issue bodies document declared scope** but do not replace a board
   audit.

**Pre-planning drift audit:** before a scoping pass, verify every repo's open
issues are on the board. An auto-add hook catches issues created in-session, but
externally created issues (manual UI, bots, cross-repo dispatch) slip past.
Compute the set difference between "all open issues across all repos" and "all
board item URLs" and add any orphans before scoping.

**Why:** running this check once revealed a large fraction (tens of percent) of
open issues missing from the board — invisible to any planning pass that read
labels or meta-issue bodies alone. A board-audit skill should automate both the
orphan-detection and the label → board-field sync, wired into kickoff, retro,
and session-start so the board stays current at every boundary.

## Multi-step meta-issue freshness re-audit

A meta-issue's enumerated scope is a snapshot of HEAD at filing time, not a
standing claim. Parallel work lands between filing and implementation, so the
longer the gap the more the body drifts.

**Trigger:** a multi-step meta-issue (scope enumerated as a list of files,
repos, or per-step criteria) that is **older than ~48h at implementation** needs
a HEAD audit, per repo named, **before any Edit/Write.** Single-step issues are
exempt (covered by the per-file existence verify).

**Audit deliverable** (before the first implementer is spawned):
1. **Per-repo HEAD-state summary** — `file:line` refs read at HEAD via the
   contents API, not the working tree.
2. **Comparison against the enumerated scope** — element by element.
3. **Per-element verdict** — `STILL TODO` / `ALREADY DONE` / `SCOPE CHANGED` /
   `NEW ITEM SURFACED`.
4. **Posted as a COMMENT on the meta-issue, not a body edit.** Editing the body
   erases the record that scope shrank; the comment preserves the audit trail.

Brief only the non-`ALREADY DONE` elements; recompute the spawn count against
the audited scope, never the body's original enumeration.

## Assignment & hygiene

- **Assignment:** issues are assigned via a per-member label; each member works
  only on issues labeled with their name. **No branch without an existing
  ticket** — the branch name references the issue number.
- **Reassignment on departure:** remove the departing member's label from open
  issues; the coordinator reassigns each and applies the new assignee's label.
- **Manual issues:** work requiring a human (configure a dashboard, sign up for
  a service, upload credentials) gets a `[MANUAL]`-prefixed title. It needs no
  PR and is closed when the human confirms via comment. Agents may create
  `[MANUAL]` issues for work they cannot perform.
- **Hygiene:** keep status current; use comments for questions, progress, and
  decisions; close **only** when the work is complete and verified.

## End-state criterion: delivered vs applied-and-verified

A rollout/enforcement criterion is **MET only when the mechanism is APPLIED and
verified at origin — not when the spec/script/hook that would apply it is merely
delivered.** "Delivered" (the artifact exists) and "applied" (the live system
enforces it) are distinct states. A criterion-tracking issue distinguishes them
and stays OPEN as the rollout tracker until applied-and-verified is true for
every target.

Verify the enforcing state at origin with the authoritative API for that
mechanism, and cite the verification — e.g. read back a branch-protection
ruleset on **every** target branch, confirm a CI gate is green in the latest
default-branch run, confirm a real deploy run exists in history. While
delivered-but-not-fully-applied, the delivering PR references the issue with
`Refs #N` (not `Closes #N`) and the issue stays open.

## Comment format

All issue comments follow a structured trailer:

```
Requestor: Firstname.Lastname
Requestee: Firstname.Lastname
RequestOrReplied: Request | Replied

<comment body>
```

- **Requestor** = the comment author.
- **Requestee** = the person being asked or referenced (`N/A` for general status
  updates with no specific ask).
- **RequestOrReplied** = `Request` for an initial ask, `Replied` for a response.

## Reply protocol

When tagged as **Requestee** on a `Request`, respond with a new comment on the
same issue with the names **swapped** (replier becomes Requestor, original
Requestor becomes Requestee) and `RequestOrReplied: Replied`. Then directly
notify the original Requestor that a reply was posted and that they should read
it and update the issue description if the reply warrants changes.

## Ticket update rules by ownership

The **ticket owner** is the member whose assignment label is on the issue.
- **Requestor is the owner:** the owner gathers the needed info from the
  Requestee, then updates the issue description with the result.
- **Requestee is the owner:** the Requestor is providing input; the owner folds
  the feedback into the description, no back-and-forth unless clarification is
  needed.

## Adaptation notes

- The structured comment trailer pairs with a verdict/review format on PRs and
  is what review-counting hooks parse — keep the field names stable if you
  automate enforcement.
- The board-as-authoritative and HEAD-verification rules are the load-bearing,
  portable parts; the label/assignment mechanics are easy to re-skin per tool.
