# Work Delegation & Issue Management

## Delegation Flow

1. **The Manager decomposes requirements** and delegates each piece to the
   appropriate direct report based on domain.
2. **The assigned member creates GitHub Issues** covering the delegated work, with
   clear acceptance criteria.
3. Disputes about ownership are negotiated with the relevant lead and the Manager;
   the Manager makes the final call.

## Wave Planning: Shared Artifacts & Frozen Contracts

Two planning rules the Manager/lead apply when decomposing a wave into parallel
stories. Both pre-empt a *predictable*, foreseeable-at-planning failure rather than
resolving it after the fact.

### Single Integration-Owner for Shared Registries

When two or more stories in the same wave will touch the **same shared config list,
registry, or module** — e.g. `hooks.pre_bash`, a `_DEFAULTS` / `_MANAGED_TREES` list,
the golden install manifest, or a single charter module (`pull-requests.md`) — the
Manager **designates exactly ONE story as the integration-owner** for that artifact at
wave kickoff (or explicitly **serializes** those specific edits so they never land in
parallel). Every other story routes the change it needs into that artifact **through the
owner** (via the lead's relay) instead of editing the shared artifact itself.

Rationale: two stories editing one append-only list — or one prose module — produce a
**predictable** merge conflict that is foreseeable at planning, not an accident to
resolve after the fact (Phase 6 Wave 5, #201: the S2↔S3 `hooks.pre_bash` conflict
surfaced as a CONFLICTING PR and cost a resolution round-trip that kickoff could have
pre-empted). Designating one owner removes the round-trip; serializing the edits is the
fallback when no single owner is natural. The designation is recorded in the wave
kickoff brief alongside reviewer assignment.

If this rule ever becomes worth mechanically enforcing (e.g. a gate that flags two
in-flight branches touching the same registry), file it as a follow-up issue — do not
build the gate inline.

### Pin Frozen Contracts Against Code, Not Prose

When a wave **freezes an inter-story contract** — a data shape, API signature, hook
grammar, or parsing vocabulary that a later story will build against — the frozen
contract must be **validated against the actual code layer at authoring time**: check
the real signature / grammar / parser it binds to, not only a narrative description of
it. The kickoff brief that pins the contract carries the concrete check (the exact
field name, token, or signature it must agree with), not prose alone.

Rationale: a contract authored in prose alone can read as internally consistent and
still be wrong against the code it names (Phase 6 Wave 5, #201: the frozen `ReviewState`
contract said "distinct requestees" where the charter's verdict grammar makes the
reviewer the `Requestor:` — so a 2-reviewer bar could never clear; caught downstream by
the implementer, far later than authoring). A one-line grammar/signature check against
the real code at freeze time moves that whole class of defect left of implementation.

## Issue Review Process

Every newly created issue gets a review pass from each lead and senior contributor.
**If a reviewer has nothing significant to contribute, they add nothing** — no
boilerplate comments. Reviews cover: architecture, infrastructure, data impact,
testing strategy, security, cross-team dependencies. The goal is early visibility,
not gatekeeping.

## Work Gate: Issues Before Implementation

No implementation work begins until ALL issues for the current phase have been:

1. **Created** — the full set covering the phase's requirements exists.
2. **Reviewed** — every issue has passed the review process above.

Only then does the Manager signal that implementation may begin — and wave kickoff
itself requires the project owner's approval (see
[charter.md § Ground Rules](charter.md)).

## Assignment

- Issues are assigned via a GitHub label: **`FIRSTNAME_LASTNAME`**.
- Each member works only on issues labeled with their name.
- **No branch without an issue.** The branch name must reference the issue number
  (scheme: `{initials}/{issue}-{slug}` — see [branching.md](branching.md)).
- Tech-debt issues carry the `tech-debt` label and are initially
  self-assigned; the Tech Lead reallocates during planning (tech debt capped at
  ~20% of any member's capacity).
- When a member is replaced, their label is removed from open issues and each issue
  is reassigned.
- Issues that require a human MUST be title-prefixed `[MANUAL]`; they close when the
  human confirms via comment.

## Issue Hygiene

- **Status** kept current (open, in progress, blocked, done).
- **Comments** used for questions, clarifications, progress updates, decisions.
- **Close condition** — an issue closes only when its work is merged and verified,
  never preemptively on an unmerged branch.
- **Verify premises at origin.** An issue claiming a gap or bug in the code must
  have that premise checked against the current origin HEAD at filing time — not
  against memory or another issue's snapshot of the codebase.

## Comment Format

All issue comments MUST follow this format:

```
Requestor: Firstname.Lastname
Requestee: Firstname.Lastname
RequestOrReplied: Request

<actual comment body>
```

- **Requestor** = the person writing the comment.
- **Requestee** = the person being asked (`N/A` for general status updates).
- **RequestOrReplied** = `Request` when posting, `Replied` when responding.

### Verdict-Comment Grammar (machine-parsed — single source of truth)

PR **review verdicts** use the same three-line header, and additionally carry the
review outcome in the **body** via two severity markers:

```
Requestor: Firstname.Lastname
Requestee: Firstname.Lastname
RequestOrReplied: Request

**Review: <one-line summary>**
Must-fix: <enumerated items, or None>
Tech-debt: <items, or None>
```

This shape is a **machine grammar**, not just a convention — two tools read it and
must agree on the vocabulary:

- **`validate_review_comment_format`** (a PreToolUse hook) *enforces* it: a
  `gh pr comment` / `gh issue comment` whose body attempts the header but is
  malformed (a missing/mistyped field, an unknown verdict token) is blocked at
  write time.
- **`trust_signals.py`** *parses* it to score review quality (issue #98): the
  `Requestor:` line is the reviewer identity, `RequestOrReplied:` is the verdict
  state, and the body `Must-fix:` tally is the severity.

Canonical vocabulary (both tools bind to these exact tokens):

| Element | Label | Allowed values | Meaning |
|---------|-------|----------------|---------|
| Header | `Requestor:` | a name (bare or `**bold**`) | comment author / reviewer |
| Header | `Requestee:` | a name, or `N/A` | who is addressed / the PR author |
| Header | `RequestOrReplied:` | **`Request`** \| **`Replied`** | posting a verdict / replying |
| Body | `Must-fix:` | enumerated items, or `None` | enumerated ⇒ **changes requested** (blocks merge); `None` ⇒ clean |
| Body | `Tech-debt:` | items, or `None` | non-blocking; tracked as issues |

Severity lives in the **body** (`Must-fix:`), never in the verdict token — do not
write `RequestOrReplied: Approved` or `ChangesRequested`. Both the bare
(`Requestor: Name`) and bold (`**Requestor:** Name`) header forms are accepted.

Use roster-canonical `Firstname.Lastname` in the `Requestor:` / `Requestee:`
fields (the exact form the roster carries) — `trust_signals.py` keys reviewer
identity off that field, so a nickname or role suffix (`Tariq (QA)`) attributes
the signal to the wrong (or no) engineer.

### Request vs. Replied, Must-fix vs. Tech-debt (semantics)

The tokens carry meaning beyond their shape. `validate_review_comment_format`
enforces the **shape** (a malformed header is *blocked*) and — since #118 —
*warns* (fail-open, never blocks) when the **semantics** below are misused:

- **`RequestOrReplied: Request`** — a turn that **carries blocking findings**:
  the body's `Must-fix:` section enumerates ≥1 item that must be resolved before
  merge. Use `Request` when you are asking for changes.
- **`RequestOrReplied: Replied`** — a **response or approval** turn: a reply to a
  `Request`, or a review that clears the PR with no blocking items. An approving
  review whose `Must-fix:` is `None` should be `Replied`, **not** `Request`.
- **`Must-fix:` is blocking-only** — every item under it is counted by
  `trust_signals.py` as a blocking `must_fix_received` signal against the author.
  Put **only** items that must hold the merge here.
- **`Tech-debt:` for everything non-blocking** — nits, follow-ups, "accept
  as-is" notes, reviewer-name corrections, anything you would *not* hold the
  merge for. Tracked as issues; never scored as blocking.
- **A finding that defeats a shipping feature's core guarantee is a
  `Must-fix:`, not `Tech-debt:`** — even when the surrounding code otherwise
  works and the PR is "done." Ask: *if this finding stands unresolved, does
  the guarantee this PR ships still hold?* If no, it blocks the merge; filing
  it as tech-debt lets the broken guarantee ship anyway, and the mechanical
  scorer gives the reviewer **zero credit** for catching it (`Tech-debt:`
  items are never counted toward `must_fix_received`/`must_fix_caught`).

**Worked example (Phase 6 Wave 2, #175):** review of the fail-closed
load-bearing-test hook (#167) found that `dispatcher.py` swallows an uncaught
hook exception as `ALLOW` — the dispatcher fails **open**. That defeats
#167's entire premise (a *fail-closed* gate). The finding was filed as
`Tech-debt:` because the surrounding code "worked" outside that edge case; the
scorer credited it nothing and it did not hold the merge, so a fail-closed
guarantee shipped sitting on a fail-open dispatcher. Under this norm the same
finding is filed `Must-fix:` — it defeats #167's core guarantee, full stop.
(Charter norm adopted via #180.)

Two Phase-4-Wave-1 misuses the warn tier now flags (each surfaced a phantom
blocking signal that flattened the trust matrix):

| Misuse | Why it's wrong | Fix |
|--------|----------------|-----|
| Approval filed as `Request` with `Must-fix: None` | `Request` implies blocking findings; there are none | use `Replied` |
| A non-blocking note under `Must-fix:` ("non-blocking", "do not hold", "accept as-is") | scored as a blocking `must_fix_received` | move it to `Tech-debt:` |

Examples — an approval and a changes-requested review:

```
Requestor: Nia.Rossi
Requestee: Ibrahim.El-Amin
RequestOrReplied: Replied          # approval, no blocking items → Replied

**Review: LGTM — ships as-is**
Must-fix: None
Tech-debt: None
```

```
Requestor: Tariq.Morales
Requestee: Paloma.Gupta
RequestOrReplied: Request          # carries a blocking item → Request

**Review: one must-fix**
Must-fix:
1. Rebase — the branch is CONFLICTING against the moved base.
Tech-debt:
1. Reviewer-name string reads "Tariq (QA)"; prefer canonical `Tariq.Morales` (non-blocking).
```

## Reply Protocol

When tagged as **Requestee** on a `Request` comment, respond on the same issue with
the names **swapped** (replier becomes Requestor) and `RequestOrReplied: Replied`,
then directly notify the original Requestor that a reply is posted and the issue
description may need updating.

## Ticket Ownership

The **ticket owner** is the member whose `FIRSTNAME_LASTNAME` label is on the issue.

- **Owner is the Requestor:** the owner gathers the needed information from the
  Requestee, then updates the issue description with the result.
- **Owner is the Requestee:** the Requestor is providing input; the owner folds the
  feedback into the issue description.

## Escalation

When a ticket needs input from another member: post a `Request` comment (format
above), notify your superior if needed, and reference **both** the issue number and
the specific comment needing attention.
