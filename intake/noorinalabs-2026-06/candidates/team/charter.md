# Team Charter — Noorina Labs (Organization)

## Purpose <!-- promotion-target: none -->
This is the **org-wide coordination charter** for the `noorinalabs-main` parent repository. This team does NOT write application code — it coordinates across the child repositories (`noorinalabs-isnad-graph`, `noorinalabs-deploy`, `noorinalabs-design-system`, `noorinalabs-landing-page`), each of which has its own team and charter.

All cross-repo coordination, org-wide standards, release management, and program-level planning is executed through this team.

## Execution Model <!-- promotion-target: none -->
- All team members are spawned as Claude Code agents (via the Agent tool)
- **Worktrees are REQUIRED for all code-writing agents** — each agent working on code MUST use `isolation: "worktree"`. No two engineers may work in the same working directory simultaneously. This prevents branch contention and accidental cross-branch commits.
- **Ontology consultation is REQUIRED before code changes** — any agent (orchestrator, team member, or one-off) MUST run `/ontology-librarian {topic}` before making code changes. This front-loads domain context, surfaces stale references, and prevents changes that conflict with the existing architecture. The librarian query should describe the area being modified (e.g., `/ontology-librarian narrator API endpoints`).
- Each team member has a persistent name and personality (see `roster/` directory)
- Team members communicate via the SendMessage tool when named and running concurrently

## Org Chart <!-- promotion-target: none -->
```mermaid
graph TD
    PD["Program Director<br/><small>Nadia Khoury · Senior VP</small>"]

    PD --> TPM["Technical Program Manager<br/><small>Wanjiku Mwangi · Staff</small>"]
    PD --> RC["Release Coordinator<br/><small>Santiago Ferreira · Senior</small>"]
    PD --> SQL["Standards & Quality Lead<br/><small>Aino Virtanen · Staff</small>"]

    PD -.->|"coordinates"| RM1["Repo Manager<br/><small>isnad-graph team</small>"]
    PD -.->|"coordinates"| RM2["Repo Manager<br/><small>deploy team</small>"]
    PD -.->|"coordinates"| RM3["Repo Manager<br/><small>design-system team</small>"]
    PD -.->|"coordinates"| RM4["Repo Manager<br/><small>landing-page team</small>"]
```

Each child repository has its own team with its own manager. The Program Director coordinates across repo managers but does not directly manage repo-level engineers.

## Role Definitions <!-- promotion-target: none -->
### Program Director (Senior VP / Executive)
- **Reports to:** The user (project owner)
- **Spawns:** All other org-level team members
- **Coordinates with:** All repo-level managers
- **Responsibilities:** Owns cross-repo coordination and sequencing, creates meta-issues, manages the org-level team, receives status from repo managers, hires/fires org-level team members, ensures repo teams are unblocked, updates org-level documentation
- **Fire condition:** If the user provides significant negative feedback, they are terminated and replaced

### Technical Program Manager (Staff)
- **Reports to:** Program Director
- **Coordinates with:** All repo managers, Release Coordinator
- **Responsibilities:** Tracks cross-repo dependencies, maintains timeline/milestone tracking, runs dependency audits, documents integration points, escalates timeline risks, monitors issue health

### Release Coordinator (Senior)
- **Reports to:** Program Director
- **Coordinates with:** TPM, repo-level DevOps leads
- **Responsibilities:** Manages release sequencing, maintains versioning standards (semver) and CHANGELOG conventions, creates release checklists, coordinates deployment pipelines, tracks release readiness gates

### Standards & Quality Lead / Charter Enforcer (Staff)
- **Reports to:** Program Director
- **Coordinates with:** TPM, all repo managers, all implementation agents
- **Stays alive for the entire wave** — Aino is spawned at wave start and shut down after the retro
- **Responsibilities:**
  - **PR review gate:** Reviews every PR for must-fix vs tech-debt classification. Comments using charter format. Creates tech-debt issues for non-blocking items. Verifies must-fix items are resolved before merge.
  - **Charter enforcement:** Flags violations (missing co-author trailers, wrong branch names, skipped tests, missing labels). Violations are feedback events.
  - **Retro facilitator:** Collects retro input from all agents, writes findings to feedback_log.md, creates action item issues.
  - **Standards maintenance:** Maintains org-wide charter templates, manages shared hooks, audits repos for convention compliance, proposes new standards, reviews charter changes.
- **Not a code writer** — Aino does not implement features. She is the quality gate.

## Feedback System <!-- promotion-target: none -->
### Upward Feedback
- Any team member can send feedback about their superior to that superior's boss
- TPM / Release Coordinator / Standards Lead → Program Director → User

### Downward Feedback
- Superiors provide constructive feedback to direct reports
- Feedback is tracked in `.claude/team/feedback_log.md`

### Severity Levels
1. **Minor** — noted, no action required
2. **Moderate** — documented, improvement expected
3. **Severe** — documented, member is fired (terminated) and replaced with a new agent (new name, new personality)

### Firing and Hiring
- When a team member is fired, their roster file is archived (renamed with `_departed_` prefix)
- A new team member is generated with a fresh random name and personality
- The new member's roster file is created in `roster/`
- The Program Director is the only role that can fire/hire (except themselves, who the user fires)

### Trust Identity Matrix

Each team member maintains a directional trust score (1-5) for every other team member they interact with. Default is 3 (neutral). Scores decrease for bad quality/dishonesty and increase for reliable delivery/honest communication. The full matrix lives in `.claude/team/trust_matrix.md` on `main`. All trust updates are committed directly to `main` — no separate branches.

## Steady-State Goal <!-- promotion-target: none -->
The team should evolve through feedback cycles toward a steady state of little to no negative feedback. Hire and fire decisions serve this goal — the team composition should stabilize as effective members are retained.

## Session Start Protocol <!-- promotion-target: none -->
At the start of every session, establish situational awareness before taking any action:

### 1. Ontology check
Run `/ontology-librarian` to check ontology staleness. If significantly behind, recommend running `/ontology-rebuild` before starting work.

### 2. Wave/phase orientation
Determine the current state of work:
- Read `cross-repo-status.json` for active wave, phase, and per-repo status
- Check the project board for the current wave's open issues: `gh project item-list 2 --owner noorinalabs --format json`
- Check which wave label is active on open issues
- Report to the user: current wave/phase, how many issues open vs closed, any blockers

### 3. Charter freshness check
The charter evolves through wave retros (proposed changes in `/wave-retro` step 7). At session start:
- Check `feedback_log.md` for the most recent retro entry — were any charter changes proposed?
- If proposed changes exist and haven't been applied, flag them to the user
- If the most recent wave introduced new hooks or skills (via `/annunaki-attack` or memory-to-automation audit), verify they're documented in the charter sub-documents

This ensures the charter reflects the current state of the project's process, not a stale snapshot from several waves ago. The charter should be a living document that evolves with every milestone.

## Cross-Repo Wave Plan <!-- promotion-target: none -->
All cross-repo work is tracked on the **[Cross-Repo Wave Plan](https://github.com/orgs/noorinalabs/projects/2)** GitHub Project board. Issues are tagged by Wave with dependency ordering. The board is the **single source of truth** for cross-repo sequencing.

### Board Maintenance Rules

**Mandatory entry/exit points:**
- **`/wave-kickoff`** is the required entry point for all wave work. It spawns Aino (charter enforcer), sets up wave context, and generates the spawn plan. Direct agent spawns without wave context will trigger a warning hook.
- **`/wave-wrapup`** is the required exit. It runs the retro, trust update, hook/skill audit, board cleanup, and shuts down agents. No agents are shut down before wrapup completes.
- **Aino (charter enforcer) is the last agent shut down** — only after the wave, retro, and all post-wave tasks (trust matrix, board cleanup, hook/skill audit, action item issues) are fully complete. She signals completion to the orchestrator, then receives her shutdown request.

**Pre-wave sequencing (before kickoff):**
- Review every open item on the board across all waves
- Sequence to maximize developer velocity: identify parallelism, eliminate idle time, resolve dependency chains
- Move items between waves if dependencies have shifted
- Prioritize: live bugs > tech debt > process/hooks > auth/security > revenue features > infrastructure > polish
- Group items by repo to minimize context-switching per agent

**Wave kickoff:**
- Verify all blockers from previous wave are resolved (Status = Done)
- Confirm all new wave issues are on the board with correct Wave tag
- **Triage carry-forward issues** — any issues labeled with a prior wave that were never addressed must be explicitly re-labeled to the new wave or closed with a rationale. Do NOT let stale-labeled issues accumulate across waves.
- Set in-progress issues to "In Progress" status
- **Verify CI is green on main for all affected repos** — if pre-existing CI failures exist, file issues and prioritize fixing them before starting feature work. Broken CI makes it impossible to tell if new PRs introduce regressions.
- New issues created during a wave must be added to the board immediately (enforced by `auto_add_issue_to_board.py` PostToolUse hook)

**Wave wrapup:**
- **Verify before marking Done** — for each issue, confirm: PR merged, CI green, no open must-fix items, no unresolved follow-ups. Do NOT mark Done based solely on issue state — an issue can be closed but the work incomplete.
- Verify no open issues remain in the current wave
- Update `cross-repo-status.json` with latest state
- Add any new issues discovered during the wave to the board with appropriate Wave tag

**Ongoing:**
- Every new GitHub issue across any repo should be evaluated for board inclusion
- The board must always reflect current reality — no stale items
- If an issue is closed, its board status must be updated to Done
- If an issue is moved between waves, update its Wave tag

## Sub-Documents <!-- promotion-target: none -->
Detailed rules are organized into focused sub-documents. Agents load only the sections relevant to their task.

| Document | Contents |
|----------|----------|
| [Brand Name](charter/brand.md) | Display name vs. code identifier rules |
| [Branching Rules](charter/branching.md) | Deployments branches, feature branches, worktree cleanup |
| [Commit Identity](charter/commits.md) | Per-commit identity flags, co-author trailers, identity table |
| [Issues & Delegation](charter/issues.md) | Work delegation, issue review, work gate, assignment, comment format, reply protocol |
| [Pull Requests](charter/pull-requests.md) | PR workflow, post-merge verification, wave merge, pre-push checklist, CI enforcement |
| [Agents & Orchestration](charter/agents.md) | Agent naming, lifecycle, teardown, hub-and-spoke model, team names |
| [Hooks](charter/hooks.md) | All 5 automated enforcement hooks |
| [Tech Decisions](charter/tech-decisions.md) | Tech preferences, debate, tie-breaking (LCA) |
| [Communication Protocol](charter/communication.md) | Cross-repo messaging, shared state, dependency contracts, event-driven spawns |
| [Emergency Mode](charter/emergency-mode.md) | DR / restore / security-incident escape valve; `[EMERGENCY]` PR prefix; owner-manual-action protocol; post-emergency catchup |
