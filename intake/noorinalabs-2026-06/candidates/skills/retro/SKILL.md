---
name: retro
description: Lightweight mid-wave health check — quick pulse on progress, blockers, and process friction without full assessments or trust updates
args: team_name
---

Run a lightweight retrospective for the `{team_name}` team. This is a **mid-wave health check**, not a full end-of-wave retrospective. Use `/wave-retro` for the comprehensive end-of-wave engine with trust matrix updates and charter proposals.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Wave Lifecycle for the canonical skill order and preconditions.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## When to use

- Mid-wave checkpoint to surface blockers early
- After a significant incident or unexpected delay
- When the team lead wants a quick pulse without the overhead of a full retro

## Instructions

### 1. Gather current wave state

Determine the active wave from `cross-repo-status.json` or ask the user:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
cat "$REPO_ROOT/cross-repo-status.json" 2>/dev/null
```

### 2. Collect progress data

```bash
# PRs merged so far in this wave
gh pr list --state merged --base main --json number,title,author,mergedAt --limit 50

# PRs still open
gh pr list --state open --json number,title,author,createdAt,isDraft --limit 50

# Issues closed this wave
gh issue list --state closed --label "{wave-label}" --json number,title,closedAt

# Issues still open this wave
gh issue list --state open --label "{wave-label}" --json number,title,labels,assignees
```

### 3. Collect CI health

```bash
# Recent workflow runs
gh run list --limit 20 --json conclusion,name,createdAt,headBranch
```

Count pass/fail ratio. Flag any branches with repeated failures.

### 4. Identify blockers and friction

Check for:
- **Stale PRs:** Open PRs older than 2 days without review activity
- **Blocked issues:** Issues with no PR and no recent activity
- **CI failures:** Branches with 2+ consecutive failures
- **Review bottlenecks:** PRs waiting for review with no reviewer assigned

### 5. Present health check

Output a concise report (not written to a file — displayed inline):

```
**Mid-Wave Health Check: {team_name}**

**Progress:**
- Issues closed: {N} / {total} ({percentage}%)
- PRs merged: {N}
- PRs open: {N} ({draft_count} drafts)

**CI Health:** {pass_count}/{total_runs} passing ({percentage}%)

**Blockers:**
- {description of blocker, or "None identified"}

**Friction Points:**
- {stale PRs, review bottlenecks, or "None identified"}

**Recommendation:** {continue as planned | adjust priorities | escalate}
```

### 6. Suggest actions (if needed)

If blockers or friction are found, suggest specific actions:
- Reassign stale PRs
- Pair on blocked issues
- Fix CI before continuing feature work
- Escalate cross-repo dependencies

**Do NOT take any action without user approval.** This is a diagnostic, not an intervention.

## Differences from wave-retro

| Aspect | `/retro` (this skill) | `/wave-retro` |
|--------|----------------------|---------------|
| Timing | Mid-wave | End of wave |
| Trust matrix | Not updated | Updated |
| Per-engineer assessments | Not included | Full assessments |
| Charter proposals | Not included | Proposed |
| Feedback log | Not updated | Appended |
| Output | Inline display only | Written to feedback_log.md |
| Scope | Quick pulse | Comprehensive analysis |

## What remains manual

- User decides whether to act on recommendations
- Blocker resolution requires team coordination
- If the health check reveals severe issues, the user may choose to run a full `/wave-retro` early
