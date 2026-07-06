# Team Charter — 2real-team-framework

This is the governance charter for the simulated-team workflow on this repository.
It is split into focused modules so each rule set can be read (and evolved) on its
own. The modules below are the **single source of truth** for process rules — other
documents (CLAUDE.md, roster cards, skills) should link here rather than restate them.

## Modules

| Module | Governs |
|--------|---------|
| [agents.md](agents.md) | Agent naming, spawning, lifecycle, orchestration, verifying agent reports |
| [branching.md](branching.md) | Integration branches, feature branches, worktree discipline |
| [commits.md](commits.md) | Per-commit identity, `Co-Authored-By` trailers |
| [pull-requests.md](pull-requests.md) | PR creation, review workflow, merge gates, definition of done |
| [issues.md](issues.md) | Delegation, work gates, assignment labels, comment protocol |
| [hooks.md](hooks.md) | Which charter rules are enforced automatically, and how |
| [skills.md](skills.md) | Skill-writing conventions; the promotion-pipeline marker convention |

## Ground Rules (apply everywhere)

- **All work is executed through the team.** Every task maps to a roster member in
  `.claude/team/roster/`; every spawned agent maps to a roster member.
- **The configuration is authoritative.** Repo-specific values (owner, branch schemes,
  reviewer count, merge model) live in `.claude/framework.config.json`. The values
  baked into these documents were substituted from that config at install time — if
  the config changes, re-run the framework bootstrap with `--refresh-charter` to
  refresh them. Refresh re-renders only the modules you have not hand-edited;
  hand-evolved modules are preserved (use `--force` to overwrite those too).
- **Owner:** `parametrization` · **Default branch:** `main` ·
  **Merge model:** `wave-branch` (configured default; the effective model per
  wave is declared at kickoff via `lifecycle.py wave kickoff --merge-model …` and
  recorded in the state file) · **Reviews required per PR:** 1
- **User approval gates.** Merging to `main`, creating releases, and
  kicking off a new wave all require explicit approval from the project owner. No
  team member may bypass these gates.

## Feedback & Team Evolution

- Feedback flows up and down: any member may send feedback about a superior to that
  superior's boss; superiors give constructive feedback to reports. Feedback is
  tracked in `.claude/team/feedback_log.md`.
- Severity levels: **minor** (noted), **moderate** (documented, improvement expected),
  **severe** (member is replaced with a new persona).
- Directional trust scores (1–5, default 3) between members live in
  `.claude/team/trust_matrix.md`.
- The team evolves toward a steady state of minimal negative feedback; hire/fire
  decisions serve that goal.

## Precedence

If a module conflicts with a summary elsewhere (CLAUDE.md, a skill, a roster card),
the module wins. If two modules appear to conflict, the more specific rule wins;
escalate genuine conflicts to the project owner.
