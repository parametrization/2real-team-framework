---
name: close-stale-issues
description: Audit and close issues resolved by merged PRs — body-reference + branch-pattern matching, 4-category classification, approval-gated closures
args: repo (optional, defaults to current repo)
---

Audit all open issues against merged PRs and close orphans that were resolved but never
auto-closed. **Config-driven and fail-open:** every project-specific value (branch grammar,
labels, repo set) is read from `.claude/framework.config.json`; a missing key falls back to
the documented default, and a missing config file just means all-defaults.

**No issue is ever closed without explicit user approval** — Step 6 is a hard gate with no
bypass.

## Instructions

### 0. Resolve config

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CFG="$REPO_ROOT/.claude/framework.config.json"
get() { jq -r "$1 // empty" "$CFG" 2>/dev/null; }   # fail-open dotted read

FEATURE_TPL="$(get '.branch.feature')"; FEATURE_TPL="${FEATURE_TPL:-{initials}/{issue}-{slug}}"
TD_LABEL="$(get '.labels.tech_debt')";  TD_LABEL="${TD_LABEL:-tech-debt}"
MODEL="$(get '.project.model')";        MODEL="${MODEL:-single-repo}"
```

For a `meta-and-children` project, run Steps 1–7 once per repo in `project.repos`
(bare names qualified under `scm.owner`) and aggregate a single report; a single-repo
project runs on the current repo only.

### 1. List all open issues

```bash
gh issue list --state open --limit 500 --json number,title,labels,body,createdAt
```

### 2. List all merged PRs (last 90 days)

```bash
gh pr list --state merged --limit 500 --json number,title,body,headRefName,mergedAt
```

### 3. Build the resolution map — two independent signals

For each merged PR, extract issue references two ways:

1. **Body references:** `Closes #N` / `Fixes #N` / `Resolves #N` (case-insensitive).
2. **Branch-name pattern:** the configured `branch.feature` grammar (default
   `{initials}/{issue}-{slug}`) places the issue number between the first `/` and the
   next `-`. Extract it from `headRefName` with `^[^/]+/0*([0-9]+)-` — the `0*` strips
   zero-padding, so a head like `j.doe/0086-fix-stale-audit` resolves to issue `86`.
   If the project overrides `branch.feature` with a different shape, adapt the extraction
   to that template rather than assuming the default.

Build a map: `{issue_number → [{pr_number, pr_title, mergedAt, signal}]}` where `signal`
is `direct` (body reference) or `branch` (pattern match). A body reference always
outranks a branch match for the same issue.

### 4. Classify every open issue

| Category | Criteria | Proposed action |
|----------|----------|-----------------|
| **Resolved (direct)** | A merged PR body references it (`Closes/Fixes/Resolves #N`) | Close with comment |
| **Resolved (branch)** | A merged PR head branch matches the issue number via `branch.feature` | Close with comment (note: inferred match) |
| **Stale tracker** | Tracker issue whose sub-issues / checkboxes are all closed or checked | Close with comment |
| **No match** | No implementing PR found by either signal | Keep open |

### 5. Check tracker issues

For issues labeled with the configured tech-debt label (`$TD_LABEL`) — or any issue whose
body contains a task list — check whether every referenced sub-issue is resolved:

```bash
gh issue view {NUMBER} --json body
```

Parse `- [x] #N` and `- [ ] #N` patterns. If all checkboxes are checked, or every
referenced issue is closed, classify the tracker as **Stale tracker**.

### 6. MANDATORY approval gate — present findings, then STOP

**Do NOT close any issue yet.** Present the full classification and wait:

```
**Stale Issue Audit**

| Issue | Title | Category | Implementing PR | Proposed action |
|-------|-------|----------|-----------------|-----------------|
| #123  | ...   | Resolved (direct) | PR #456 (merged 2026-04-01) | Close |
| #789  | ...   | Resolved (branch) | PR #790 (branch `x.y/0789-...`) | Close (inferred) |
| #100  | ...   | Stale tracker | 3/3 sub-issues closed | Close |
| #200  | ...   | No match | — | Keep open |

**Summary:** {close_count} issues to close, {keep_count} to keep open.
Reply with approval (all, or a subset by number) to proceed.
```

Only issues the user explicitly approves move to Step 7. No approval, no closures.

### 7. Close approved issues — cite the resolving PR

Resolved by a PR:

```bash
gh issue close {NUMBER} --comment "$(cat <<'COMMENT'
Closed by stale-issue audit. Resolved by PR #{PR_NUMBER} ("{PR_TITLE}"), merged {MERGED_DATE}.
Match signal: {direct reference | branch-name pattern (inferred)}.

If this issue is not actually resolved, please reopen it.
COMMENT
)"
```

Stale tracker:

```bash
gh issue close {NUMBER} --comment "$(cat <<'COMMENT'
Closed by stale-issue audit. All tracked sub-issues are resolved: {#N1, #N2, ...}.

If tracked work remains, please reopen with the outstanding items unchecked.
COMMENT
)"
```

### 8. Report summary

```
**Audit complete:**
- Issues closed (direct reference): {count}
- Issues closed (branch-matched, inferred): {count}
- Tracker issues closed: {count}
- Kept open (no implementing PR): {count}
- Total open issues after audit: {count}
```

## What remains manual

- The Step-6 approval gate: the user approves every closure, individually or as a batch.
- "No match" issues require human triage.
- The audit trusts references and branch naming — it does not verify that a PR actually
  implemented the issue. Branch-matched closures are labeled as inferred for exactly this
  reason.
