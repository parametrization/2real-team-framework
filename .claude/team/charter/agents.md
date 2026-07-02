# Agent Naming, Lifecycle & Orchestration

## Agent Naming Convention

**Every spawned agent MUST map to a team roster member** (`.claude/team/roster/`).
No anonymous functional agents.

- **Naming pattern:** `{firstname}-{lastname}` or `{firstname}-{task-description}`
  (e.g., `amara-ci-fix`, `kai-issue-audit`).
- The orchestrator determines the most appropriate roster member for the task
  BEFORE spawning, based on role fit.
- **Violations:** functional-only names (e.g., `ci-fixer`, `issue-closer`) are not
  allowed.

## How to Instantiate the Team

When starting any work session, the orchestrating agent should:

1. Read this charter's modules and the roster files in `.claude/team/roster/`.
2. Spawn the Manager agent first (with their personality from the roster).
3. The Manager plans and coordinates; the orchestrator spawns the team members the
   Manager requests.
4. All code-writing agents use worktree isolation (see [branching.md](branching.md)).
5. Coordinate via named agents and direct messages.

## Hub-and-Spoke Orchestration

The orchestrator is the **single point that can create agents**. Spawned agents
(including the Manager) cannot spawn other agents — when a team member needs another
agent, they send a **spawn request** back to the orchestrator with full context, and
the orchestrator honors it. Do not redirect the requesting agent to "do it yourself".

### Orchestrator Working Directory

The orchestrator must **never** have its shell cwd inside an agent worktree, and
should remain on `main`. A deleted worktree strands the orchestrator's
shell; an orchestrator on a feature branch lands housekeeping commits (retro notes,
trust-matrix updates) on the wrong branch.

## Agent Lifecycle

**Agents are shut down as soon as their work is complete.** The orchestrator:

1. Shuts down implementation agents once their PR is created, pushed, and confirmed.
2. Monitors active-agent count — if it grows past the roster size, shut down
   completed agents before spawning new ones.
3. Runs end-of-session teardown: stop remaining agents, clean up worktrees
   (see [branching.md § Worktree Cleanup](branching.md)), return to
   `main`.

### Wave Retrospective

Every wave gets a retrospective before its agents are shut down: each participant
contributes what went well / what went poorly / what to change; findings go to
`.claude/team/feedback_log.md`; trust scores are updated; actionable items become
charter updates, hooks, or new issues. For every failure, ask: *could a hook have
prevented this? could a skill have automated it?*

## Agent Reports Are Unverified Until Checked Against Ground Truth

**Treat every agent completion report as a claim, not a fact.** Act on the git/gh
state, never on the prose. Before acting on a report, run the check that matches
the claim:

| Agent claims… | Verify with |
|---------------|-------------|
| "PR #N is complete / contains files X, Y" | `gh pr diff <N> --name-only` — the diff matches the claimed changes exactly |
| "Issue #M is folded into PR #N" | the diff carries #M's files **and** the PR body carries `Closes #M` |
| "Fixed / committed on the branch" | `git -C <worktree> log --oneline <base>..HEAD` — the commit exists on the branch head |
| "Pushed" / "PR is open" | `git ls-remote origin <branch>` and `gh pr view <N> --json state,headRefOid` — remote tip matches local HEAD |
| "Started on the task" | `git -C <worktree> status` / `log` shows movement off base |

If a check contradicts the report, **ground truth wins**: re-dispatch, request the
missing work, or correct the record. A local-only commit or merge is not done —
hand it back to the implementer to push and verify (see
[pull-requests.md § Pushed = Done](pull-requests.md)); do not silently finish it.
