---
name: handoff
description: "Write a session handoff note to project memory — git state, open PRs/issues, lifecycle/wave status, and the conversational context the next session needs to pick up."
---

# Handoff

Capture enough state that the **next session resumes without re-deriving context**. `/handoff`
writes `<paths.memory>/handoff.md`; `/session-start` Step 3 reads it back. Run it before ending
a working session, or any time you want a durable checkpoint.

The mechanical state (git/PR/lifecycle) is gathered automatically; the **conversational
context** (what was discussed, decided, and what to do next) is the part only you can write —
fill those sections from the session, don't leave them as placeholders.

> Config-driven + fail-open: reads `paths.*` from `.claude/framework.config.json`; sections for
> absent subsystems are omitted, not errored.

## Instructions

### Step 1 — Resolve config + gather mechanical state

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CFG="$REPO_ROOT/.claude/framework.config.json"
get() { jq -r "$1 // empty" "$CFG" 2>/dev/null; }
MEM_DIR="$REPO_ROOT/$(get '.paths.memory' || echo .claude/memory)"
STATE_FILE="$REPO_ROOT/$(get '.paths.state_file' || echo .claude/state.json)"
mkdir -p "$MEM_DIR"

BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
DIRTY="$(git -C "$REPO_ROOT" status --porcelain | wc -l | tr -d ' ')"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

OPEN_PRS=""; OPEN_ISSUES=""
if command -v gh >/dev/null 2>&1; then
  OPEN_PRS="$(gh pr list --state open --json number,title --jq '.[] | "- #\(.number) \(.title)"' 2>/dev/null)"
  OPEN_ISSUES="$(gh issue list --state open --limit 20 --json number,title --jq '.[] | "- #\(.number) \(.title)"' 2>/dev/null)"
fi

LIFECYCLE=""
[ -f "$STATE_FILE" ] && [ -f "$REPO_ROOT/.claude/lib/lifecycle.py" ] && \
  LIFECYCLE="$(python3 "$REPO_ROOT/.claude/lib/lifecycle.py" state show 2>/dev/null)"
```

### Step 2 — Compose the handoff (mechanical + conversational)

Write `$MEM_DIR/handoff.md`. The `## Pickup` / `## Decisions` / `## Open threads` sections are
**yours to fill** from the conversation — be specific (issue/PR numbers, file paths, the next
concrete command). The shell only seeds the mechanical block; replace the bracketed prompts.

```bash
cat > "$MEM_DIR/handoff.md" <<MD
# Session Handoff — $NOW

## Pickup (next concrete step)
[The single next action, with the exact command or file. e.g. "run X", "review PR #N".]

## Decisions made this session
[Bullet the decisions + their rationale, so they aren't re-litigated.]

## Open threads / blockers
[What's in flight, what's waiting, what's risky.]

## Mechanical state
- Branch: $BRANCH ($([ "$DIRTY" -gt 0 ] && echo "$DIRTY uncommitted" || echo clean))
- Open PRs:
${OPEN_PRS:-  (none / gh unavailable)}
- Open issues:
${OPEN_ISSUES:-  (none / gh unavailable)}
- Lifecycle:
${LIFECYCLE:-  (no wave state)}
MD
echo "Wrote $MEM_DIR/handoff.md"
```

### Step 3 — Index pointer

Ensure `MEMORY.md` points at the handoff so `/session-start` surfaces it:

```bash
INDEX="$MEM_DIR/MEMORY.md"
if [ -f "$INDEX" ] && ! grep -q "handoff.md" "$INDEX"; then
  printf -- '- [Session handoff](handoff.md) — latest pickup point; read first at session start.\n' >> "$INDEX"
fi
```

### Step 4 — Persist

`handoff.md` is durable session state. Decide per project whether to commit it (shareable across
machines, like the rest of `.claude/memory/`) or gitignore it (per-session, machine-local
churn). Default: **commit it** unless the project gitignores `handoff.md` deliberately. Use the
project's commit identity; never force-push.

### Step 5 — Report

Print the path written and a one-line summary of the Pickup section so the user confirms it
captures where things stand.
