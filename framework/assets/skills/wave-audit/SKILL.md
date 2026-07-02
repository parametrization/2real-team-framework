---
name: wave-audit
description: "Audit open wave issues against merged PRs — find and close orphaned issues with proper comments. Requires user confirmation before closing anything."
---

# Wave Audit

Audit open issues for a wave (`args`: phase number `{N}`, wave number `{M}`) and close any
that were resolved by a merged PR but not auto-closed.

> Config-driven + fail-open: reads `.claude/framework.config.json` via `jq`; missing keys fall
> back to the documented branch/label grammar. Nothing here mutates state until the user
> confirms closures in Step 5.

## Instructions

### 0. Resolve config + wave grammar

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CFG="$REPO_ROOT/.claude/framework.config.json"
get() { jq -r "$1 // empty" "$CFG" 2>/dev/null; }   # fail-open dotted read

N={phase}; M={wave}
# Branch + label grammar from config (tokens: {phase} {wave}); fall back to the defaults.
BRANCH_TMPL="$(get '.branch.integration')"; : "${BRANCH_TMPL:=deployments/phase{phase}/wave-{wave}}"
LABEL_TMPL="$(get '.labels.wave')";        : "${LABEL_TMPL:=phase{phase}-wave-{wave}}"
WAVE_BRANCH="$(printf '%s' "$BRANCH_TMPL" | sed "s/{phase}/$N/g; s/{wave}/$M/g")"
WAVE_LABEL="$(printf '%s' "$LABEL_TMPL"   | sed "s/{phase}/$N/g; s/{wave}/$M/g; s/{id}/$M/g")"
echo "Auditing branch $WAVE_BRANCH / label $WAVE_LABEL"
```

### 1. List merged PRs for the wave

```bash
gh pr list --state merged --base "$WAVE_BRANCH" --json number,title,body,headRefName --limit 100
```

### 2. Extract issue references from PRs

For each merged PR, parse the body for:

- `Closes #N`
- `Fixes #N`
- `Resolves #N`

Build a map: `{issue_number → [PR_number, PR_title]}`.

### 3. List open issues for the wave

```bash
gh issue list --state open --label "$WAVE_LABEL" --json number,title,labels --limit 100
```

If the project carries additional wave-label spellings (legacy conventions), query each and
union the results — `gh` ANDs multiple `--label` flags, so run them as separate queries.

### 4. Identify orphans

An orphan is an open issue that:

- Is labeled with the wave label (`$WAVE_LABEL`)
- Was referenced by a merged PR's `Closes`/`Fixes`/`Resolves` but was not auto-closed
  (auto-close only fires on merges to the default branch, so wave-branch merges routinely
  strand their issues)

Cross-reference the two lists. Also check for issues that were implemented but whose PR forgot
the `Closes` reference — match by feature-branch name (config `branch.feature`, default
`{FirstInitial}.{LastName}/{IIII}-{slug}`): a merged PR whose `headRefName` contains
`/{ISSUE_NUMBER}-` implements that issue.

### 5. Report findings to user — MANDATORY confirmation gate

Present a table before taking action:

```
**Wave Audit: Phase {N} Wave {M}** (branch `$WAVE_BRANCH`, label `$WAVE_LABEL`)

| Issue | Title | Status | Implementing PR | Action |
|-------|-------|--------|-----------------|--------|
| #123  | ...   | Open   | PR #456         | Close  |
| #789  | ...   | Open   | (none found)    | Keep   |

**Orphans found:** {count}
**Issues with no implementing PR:** {count}
```

**Do NOT close any issues until the user confirms.** Present the list and wait for explicit
approval. This gate is mandatory — there is no batch/auto mode.

### 6. Close confirmed orphans

For each confirmed orphan, close with a comment (message via a file/heredoc, never inline `-m`
piping):

```bash
gh issue close {NUMBER} --comment "$(cat <<EOF
Closed by wave audit. This issue was resolved by PR #{PR_NUMBER} ({PR_TITLE}) which merged to \`$WAVE_BRANCH\`.
EOF
)"
```

Optionally tag the closure wave (create the label first if missing):

```bash
gh label create "fixed-in-$WAVE_LABEL" --description "Resolved in $WAVE_LABEL" --color "8B5CF6" 2>/dev/null || true
gh issue edit {NUMBER} --add-label "fixed-in-$WAVE_LABEL"
```

### 7. Report summary

```
**Audit complete:**
- Issues closed: {count}
- Issues remaining open: {count} (no implementing PR found)
- Issues already closed: {count} (correctly auto-closed)
```

## What remains manual

- User must approve all closures before they execute
- Issues with no implementing PR require manual triage (defer, reassign, or close as won't-fix)
- The skill does not verify that the PR actually implemented the issue — it relies on
  `Closes #N` references and the branch-naming convention
