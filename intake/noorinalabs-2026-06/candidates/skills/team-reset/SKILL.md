---
name: team-reset
description: Transparent agent reset — shut down unresponsive agents and re-orient the implicit team, reporting roster changes
args: team_name
---

Handle the agent reset lifecycle for the `{team_name}` team.

> **Harness note (2026-06-16):** the current Claude Code harness has **no `TeamCreate`/`TeamDelete` tools**. The session runs on a **single implicit team** — there is nothing to delete or recreate. "Team reset" in this harness therefore means **shutting down running agents and re-orienting**, not tearing a team config down and rebuilding it. The steps below have been updated accordingly; the old TeamDelete/TeamCreate/config-file steps no longer apply.

## Instructions

### 1. Report current team state

Read the current team roster from `.claude/team/roster/` and report to the user:

```
**Current team: {team_name}**
| Role | Name | Status |
|------|------|--------|
| Manager | Fatima Okonkwo | Active |
| ... | ... | ... |
```

List all active roster members with their roles and status.

### 2. Send shutdown requests

Send a `shutdown_request` message via `SendMessage` to ALL agents you spawned this session:

```json
{"type": "shutdown_request", "reason": "Team reset initiated"}
```

Send one message per agent (structured messages cannot be broadcast). Wait ~5–30 seconds for agents to acknowledge and terminate.

### 3. Handle unresponsive agents

There is no `TeamDelete` to force in this harness, so a stuck agent cannot be cleared by deleting a team config. If an agent does not acknowledge its shutdown request:

1. Report to user: "{N} agent(s) unresponsive: {names}."
2. Re-send the `shutdown_request` once more.
3. If it still does not terminate, surface it to the user — a lingering agent is a UI/resource annoyance, not a blocker; spawning fresh agents is unaffected because the team is implicit. Do NOT attempt to edit or delete any `~/.claude/teams/...` config (that mechanism is gone).

### 4. Re-orient (no recreate needed)

The implicit `{team_name}` team persists for the session — there is nothing to recreate. Re-read the roster files in `.claude/team/roster/` so you have the current roster in context for the next round of spawns.

Report to user:

```
**Implicit team re-oriented:** {team_name}
| Role | Name | Status |
|------|------|--------|
| Manager | Fatima Okonkwo | Active |
| ... | ... | ... |
```

### 5. Highlight roster changes

If there are differences between the prior roster and the current roster files (hires, departures, role changes), explicitly report them:

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
Team `{team_name}` is ready ({N} roster members). Spawn agents via the Agent tool
(team_name: {team_name}) when ready — the orchestrator is the sole spawner.
```

## What remains manual

- The orchestrating Claude instance must still spawn individual agents via the `Agent` tool (agents cannot self-spawn)
- Roster file changes (hires/fires) must be committed separately
