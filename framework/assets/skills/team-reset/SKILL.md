---
name: team-reset
description: "Transparent agent reset — shut down unresponsive session agents and re-orient the implicit team, reporting roster changes."
---

# Team Reset

Handle the agent reset lifecycle for the session's team.

> **Harness note:** the Claude Code harness has **no `TeamCreate`/`TeamDelete` tools**. The
> session runs on a **single implicit team** — there is nothing to delete or recreate. "Team
> reset" therefore means **shutting down running agents and re-orienting**, not tearing a team
> config down and rebuilding it.

> Config-driven + fail-open: reads `paths.*` from `.claude/framework.config.json`; missing
> config or roster files degrade to sensible defaults, never errors.

## Instructions

### 0. Resolve config + roster paths

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CFG="$REPO_ROOT/.claude/framework.config.json"
get() { jq -r "$1 // empty" "$CFG" 2>/dev/null; }   # fail-open dotted read
TEAM_DIR="$REPO_ROOT/$(get '.paths.team' || echo .claude/team)"
[ -d "$TEAM_DIR" ] || TEAM_DIR="$REPO_ROOT/.claude/team"
```

The roster lives in two shapes, both under `$TEAM_DIR`:

- `roster/` — one markdown card per member (`## Identity` name/role/level/status,
  `## Agent Identity` agent name + spawn/message commands, `## Git Identity`)
- `roster.json` — flat `{"Name": "email"}` map (the commit-identity source)

### 1. Report current team state

Read the roster cards and the name→email map, then report:

```bash
ls "$TEAM_DIR/roster/" 2>/dev/null || echo "No roster cards."
[ -f "$TEAM_DIR/roster.json" ] && jq -r 'to_entries[] | "  \(.key) — \(.value)"' "$TEAM_DIR/roster.json" 2>/dev/null
```

```
**Current team**
| Role | Name | Status |
|------|------|--------|
| {role} | {name} | {status} |
| ... | ... | ... |
```

List all roster members with their roles and status (from each card's `## Identity` block).

### 2. Send shutdown requests

Send a `shutdown_request` message via `SendMessage` to ALL agents you spawned this session:

```json
{"type": "shutdown_request", "reason": "Team reset initiated"}
```

Send one message per agent (structured messages cannot be broadcast). Wait ~5–30 seconds for
agents to acknowledge and terminate.

### 3. Handle unresponsive agents

There is no `TeamDelete` to force in this harness, so a stuck agent cannot be cleared by
deleting a team config. If an agent does not acknowledge its shutdown request:

1. Report to user: "{N} agent(s) unresponsive: {names}."
2. Re-send the `shutdown_request` once more.
3. If it still does not terminate, surface it to the user — a lingering agent is a UI/resource
   annoyance, not a blocker; spawning fresh agents is unaffected because the team is implicit.
   Do NOT attempt to edit or delete any harness-level team config file.

### 4. Re-orient (no recreate needed)

The implicit team persists for the session — there is nothing to recreate. Re-read the roster
cards in `$TEAM_DIR/roster/` (and `roster.json` for commit identities) so you have the current
roster in context for the next round of spawns.

Report to user:

```
**Implicit team re-oriented**
| Role | Name | Status |
|------|------|--------|
| {role} | {name} | {status} |
| ... | ... | ... |
```

### 5. Highlight roster changes

If there are differences between the prior roster (as loaded earlier in the session) and the
current roster files (hires, departures, role changes), explicitly report them:

```
**Roster changes:**
- DEPARTED: {name} ({role}) — {reason}
- HIRED: {name} ({role}) — replacing {departed name}
- ROLE CHANGE: {name} — {old role} → {new role}
```

If no changes: "Roster unchanged from previous round."

### 6. Ready confirmation

Confirm the team is ready for work:

```
Team is ready ({N} roster members). Spawn agents via the Agent tool using each
card's `## Agent Identity` spawn command — the orchestrator is the sole spawner.
```

## What remains manual

- The orchestrating Claude instance must still spawn individual agents via the `Agent` tool
  (agents cannot self-spawn)
- Roster file changes (hires/fires) must be committed separately — keep `roster/` cards and
  `roster.json` in sync
