# Work Delegation & Issue Management

## Delegation Flow

1. **The Manager decomposes requirements** and delegates each piece to the
   appropriate direct report based on domain.
2. **The assigned member creates GitHub Issues** covering the delegated work, with
   clear acceptance criteria.
3. Disputes about ownership are negotiated with the relevant lead and the Manager;
   the Manager makes the final call.

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
  (scheme: `{{feature_branch_scheme}}` — see [branching.md](branching.md)).
- Tech-debt issues carry the `{{tech_debt_label}}` label and are initially
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
