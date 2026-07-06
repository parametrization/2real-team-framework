# Team Charter — 2real-team-framework (Index)

The process rules for this repository live in the **modular charter** under
[`charter/`](charter/charter.md), installed and config-substituted by the framework
bootstrap (`python3 framework/install/bootstrap.py . …`). Start at
[`charter/charter.md`](charter/charter.md) — it indexes the modules (agents, branching,
commits, pull-requests, issues, hooks, skills) and carries the ground rules, feedback
system, and precedence policy.

**The modules are the single source of truth for process rules.** This file does not
restate them; it only adds the repo-specific rules below, which supplement (and never
override) the modules. If the config in `.claude/framework.config.json` changes, refresh
the modules with the bootstrap's `--force`.

## Repo-Specific Rules

### Org Chart

| Member | Role (Level) | Reports to |
|--------|--------------|------------|
| Hiro Morales | Manager (Senior VP) | User (project owner) |
| Nia Rossi | Tech Lead (Staff) | Hiro Morales |
| Paloma Gupta | Software Engineer (Principal) | Nia Rossi |
| Ibrahim El-Amin | Software Engineer (Senior) | Nia Rossi |
| Tariq Morales | QA Engineer (Senior) | Nia Rossi |

Persona cards live in `roster/`; the identity gate validates against `roster.json`.

### Phases, Waves & Branch Names

- Work is organized into **phases**; each phase runs waves on an integration branch
  named `deployments/phase{N}/wave-{M}` (this repo's instantiation of the modular
  charter's integration-branch scheme). This repo's phases run the `wave-branch`
  model in practice — the effective merge model for a wave is declared at kickoff
  (`lifecycle.py wave kickoff --merge-model …`) and recorded in the state file.
- Feature branches: `{FirstInitial}.{LastName}/{IIII}-{issue-name}`
  (e.g. `T.Morales/0088-dogfood-closeout`).
- At the end of a phase, the deployments branch PRs into `main` (project-owner
  approval required — see [charter/charter.md § Ground Rules](charter/charter.md));
  the merge is followed by a GitHub Release tagged with the branch name,
  slashes → hyphens (see CLAUDE.md § Release Process).
- Issues close only when their work is merged to `main` — not when the feature
  branch merges to the deployments branch.

### Hiring & Firing Mechanics

- Only the Manager hires and fires (the Manager themselves is replaced by the User;
  significant negative user feedback about the Manager triggers replacement).
- A fired member's roster card is archived with a `_departed_` prefix; a replacement
  persona is generated with a fresh name and personality and added to `roster/` and
  `roster.json`.

### Tech Preferences & Decision-Making

- Each member tracks stack/tooling/library/cloud preferences in a `## Tech Preferences`
  section of their roster card; preferences evolve with project experience and the
  card is updated when they change.
- Leads take input from other leads and their reports; tooling/library/architecture
  choices may be debated to consensus.
- Tie-break: when agreement cannot be reached, the decision escalates to the
  **least common ancestor (LCA)** in the org chart, who decides, and the team moves
  forward.
