---
name: review-pr
description: Review a PR using charter format
args: PR number
---

Review a pull request for this repository following the team charter's
Comment-Based Reviews convention. Your verdict comment is machine-parsed
(`trust_signals.py`, #98) and gated at write time (`validate_review_comment_format`
+ `block_gh_pr_review`), so it MUST follow the grammar below exactly or it will be
blocked.

## Before you start
- **You cannot review your own PR.** `block_gh_pr_review` blocks a verdict whose
  `Requestor:` (you, the reviewer) equals its `Requestee:` (the PR author). If you
  authored the PR, hand the review to another team member.
- **Never use `gh pr review`.** All agents share one GitHub user, so an API
  `--approve` always fails ("cannot approve your own pull request"); the hook
  blocks it. Post a verdict COMMENT (`gh pr comment`) instead.
- **How many approvals the merge needs is config-driven:** `policy.reviewers_required`
  in `.claude/framework.config.json` is the N-reviewer gate. Read it — a PR needs
  that many DISTINCT approving reviewers before it can merge, so your approval may
  be only one of several required.

## Instructions
1. Fetch PR diff: `gh pr diff {number}`
2. Check CI status: `gh pr checks {number}` — report if failing
3. Review for: correctness, error handling, test coverage, lint compliance
4. Post ONE verdict comment with `gh pr comment {number} --body "..."` using the
   charter format below.
5. For each Tech-debt item, create a GitHub Issue (label: tech-debt + next phase + author).
6. Report: findings, CI status, and merge readiness against `policy.reviewers_required`
   (how many more approvals the PR still needs).

## Verdict grammar (gate-compatible)

Header — all three lines required (bare or `**bold**` form both accepted):

    Requestor: Firstname.Lastname     # YOU, the reviewer (comment author)
    Requestee: Firstname.Lastname     # the PR author being addressed
    RequestOrReplied: Request | Replied

Severity lives in the **body**, never in the verdict token (do NOT write
`RequestOrReplied: Approved` / `ChangesRequested`):

    Must-fix: <enumerated items, or None>   # >=1 item => changes requested (blocks merge)
    Tech-debt: <items, or None>             # non-blocking — never holds the merge

- Use `RequestOrReplied: Request` when you enumerate >=1 `Must-fix:` item (you are
  asking for changes).
- Use `RequestOrReplied: Replied` when you approve with `Must-fix: None`. (An
  approval filed as `Request` with no Must-fix is flagged by the semantic-warn tier.)
- **Tech-debt items do NOT block approval.** Anything you would not hold the merge
  for — nits, follow-ups, "accept as-is" notes — goes under `Tech-debt:`, and you
  still approve. Only `Must-fix:` items block the merge.
- Use roster-canonical `Firstname.Lastname` in both header fields — trust scoring
  keys reviewer identity off the `Requestor:` field, so a nickname or role suffix
  (`Tariq (QA)`) misattributes the signal.

### Template — changes requested

    Requestor: {Your.Name}
    Requestee: {PR.Author}
    RequestOrReplied: Request

    **Review: changes requested**
    Must-fix:
    1. {blocking finding that must be resolved before merge}
    Tech-debt: {list, or None}

### Template — approval

    Requestor: {Your.Name}
    Requestee: {PR.Author}
    RequestOrReplied: Replied

    **Review: LGTM**
    Must-fix: None
    Tech-debt: {list, or None}
