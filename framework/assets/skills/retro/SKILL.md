---
name: retro
description: Lightweight mid-wave health check — quick pulse on progress, blockers, and process friction; diagnostic only. Use /wave-retro for the full end-of-wave scoring engine.
---

Run a lightweight **mid-wave health check**. This is a quick pulse, not the end-of-wave
retrospective — `/wave-retro` owns trust scoring, the feedback-log entry, and process
proposals; `/wave-end` owns the mechanical finalize (merges, counters, cleanup).

## When to use

- Mid-wave checkpoint to surface blockers early
- After a significant incident or unexpected delay
- When you want a quick pulse without the overhead of a full retro

## Instructions

### 0. Resolve config + wave state

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CFG="$REPO_ROOT/.claude/framework.config.json"
get() { jq -r "$1 // empty" "$CFG" 2>/dev/null; }   # fail-open dotted read

DEFAULT_BRANCH="$(get '.scm.default_branch')"; DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"
WAVE_TPL="$(get '.labels.wave')";              WAVE_TPL="${WAVE_TPL:-wave-{id}}"

# The lifecycle state machine knows the current wave + merge model (fail-open if absent).
LIB="$REPO_ROOT/.claude/lib"
[ -f "$LIB/lifecycle.py" ] || LIB="$REPO_ROOT/framework/assets/lib"   # framework source repo
[ -f "$LIB/lifecycle.py" ] && python3 "$LIB/lifecycle.py" state show 2>/dev/null || true
```

Read `current_wave` (call it `{W}`) from the state output, or ask the user. The wave label
is `labels.wave` with `{id}` → `{W}`. The PR base branch is `branch.integration` (with
`{wave}` → `{W}`) when the wave's merge model is `wave-branch`, otherwise the default
branch.

### 1. Collect progress data

```bash
# PRs merged so far this wave (BASE resolved in Step 0)
gh pr list --state merged --base "{BASE}" --json number,title,author,mergedAt --limit 50

# PRs still open
gh pr list --state open --json number,title,author,createdAt,isDraft --limit 50

# Issues closed / still open this wave
gh issue list --state closed --label "{WAVE_LABEL}" --json number,title,closedAt
gh issue list --state open --label "{WAVE_LABEL}" --json number,title,labels,assignees
```

For a `meta-and-children` project, repeat per repo in `project.repos` and aggregate.

### 2. Collect CI health

```bash
gh run list --limit 20 --json conclusion,name,createdAt,headBranch
```

Count the pass/fail ratio. Flag any branch with repeated failures.

### 3. Identify blockers and friction

- **Stale PRs:** open PRs older than 2 days without review activity
- **Blocked issues:** wave issues with no PR and no recent activity
- **CI failures:** branches with 2+ consecutive failures
- **Review bottlenecks:** PRs waiting for review with no reviewer assigned

### 4. Present the health check (inline only — nothing is written)

```
**Mid-Wave Health Check — wave {W}**

**Progress:**
- Issues closed: {N} / {total} ({pct}%)
- PRs merged: {N}
- PRs open: {N} ({draft_count} drafts)

**CI Health:** {pass}/{total} passing ({pct}%)

**Blockers:** {list, or "None identified"}
**Friction:** {stale PRs, review bottlenecks, or "None identified"}

**Recommendation:** {continue as planned | adjust priorities | escalate}
```

### 5. Suggest actions (if needed)

If blockers or friction are found, suggest specific actions: reassign stale PRs, pair on
blocked issues, fix CI before continuing feature work, escalate cross-repo dependencies.

**Do NOT take any action without user approval.** This is a diagnostic, not an
intervention — nothing here mutates repo state, files, or the feedback log.

## Differences from /wave-retro

| Aspect | `/retro` (this skill) | `/wave-retro` |
|--------|----------------------|---------------|
| Timing | Mid-wave | End of wave (after `/wave-end`) |
| Trust matrix | Not touched | Mechanically updated |
| Per-engineer assessment | None | Evidence-anchored scoring via `trust_signals.py` |
| Feedback log | Not touched | Appended |
| Process proposals | None | Proposed (approval-gated) |
| Output | Inline display only | Files + inline summary |
| Scope | Quick pulse | Comprehensive engine |

## What remains manual

- The user decides whether to act on the recommendations.
- If the pulse reveals severe issues, the user may choose to run `/wave-retro` early.
