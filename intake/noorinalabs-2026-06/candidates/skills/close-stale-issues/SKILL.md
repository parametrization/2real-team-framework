---
name: close-stale-issues
description: Audit and close issues resolved by merged PRs
args: repo (optional, defaults to current repo)
---

Audit all open GitHub issues against merged PRs and close orphans that were resolved but not auto-closed.

## Instructions

### 1. List all open issues

```bash
gh issue list --state open --limit 500 --json number,title,labels,body,createdAt
```

### 2. List all merged PRs (last 90 days)

```bash
gh pr list --state merged --limit 500 --json number,title,body,headRefName,mergedAt
```

### 3. Build the resolution map

For each merged PR, extract issue references from the body:
- `Closes #N`, `Fixes #N`, `Resolves #N` (case-insensitive)
- Also match branch name patterns: `{FirstInitial}.{LastName}/{ISSUE_NUMBER}-*`

Build a map: `{issue_number → [{pr_number, pr_title, mergedAt}]}`.

### 4. Cross-reference open issues

For each open issue, check:
- **Directly referenced:** A merged PR body contains `Closes #N` / `Fixes #N` / `Resolves #N` for this issue
- **Branch-matched:** A merged PR branch name starts with `*/{ISSUE_NUMBER}-`
- **Label-matched:** The issue has a wave label (`p*-wave-*` or `wave-*`) and the corresponding deployment branch has been merged to main

Classify each open issue as:
| Category | Criteria | Action |
|----------|----------|--------|
| **Resolved (direct)** | Referenced by merged PR body | Close with comment |
| **Resolved (branch)** | Matched by branch name | Close with comment (note: inferred match) |
| **Stale tracker** | All sub-issues/checkboxes are closed | Close with comment |
| **No match** | No implementing PR found | Keep open |

### 5. Check tech-debt tracker issues

For issues labeled `tech-debt` that contain a task list (checkboxes), check if all referenced sub-issues are closed:

```bash
gh issue view {NUMBER} --json body
```

Parse `- [x] #N` and `- [ ] #N` patterns. If all checkboxes are checked or all referenced issues are closed, mark the tracker as a candidate for closure.

### 6. Present findings for approval

**Do NOT close any issues until the user confirms.** Present:

```
**Stale Issue Audit**

| Issue | Title | Category | Implementing PR | Proposed Action |
|-------|-------|----------|-----------------|-----------------|
| #123  | ...   | Resolved (direct) | PR #456 (merged 2026-04-01) | Close |
| #789  | ...   | Resolved (branch) | PR #790 (branch matched) | Close |
| #100  | ...   | Stale tracker | All 3/3 sub-issues closed | Close |
| #200  | ...   | No match | — | Keep open |

**Summary:** {resolved_count} issues to close, {no_match_count} issues to keep open
```

Wait for user approval before proceeding.

### 7. Close confirmed issues

For each approved closure:

```bash
gh issue close {NUMBER} --comment "$(cat <<'COMMENT'
Closed by stale-issue audit. Resolved by PR #{PR_NUMBER} ({PR_TITLE}), merged {MERGED_DATE}.

If this issue is not actually resolved, please reopen it.
COMMENT
)"
```

For tracker issues:

```bash
gh issue close {NUMBER} --comment "$(cat <<'COMMENT'
Closed by stale-issue audit. All tracked sub-issues have been resolved.
COMMENT
)"
```

### 8. Report summary

```
**Audit complete:**
- Issues closed: {count}
- Issues remaining open (no implementing PR): {count}
- Tracker issues closed: {count}
- Total open issues after audit: {count}
```

## Differences from wave-audit

- **wave-audit** operates on a specific wave's deployment branch and uses wave labels
- **close-stale-issues** operates repo-wide across all open issues regardless of wave
- Use `wave-audit` during wave wrapup; use `close-stale-issues` for periodic repo hygiene

## What remains manual

- User must approve all closures before they execute
- Issues with no implementing PR require manual triage
- The skill does not verify that a PR actually implemented the issue — it relies on references and branch naming
