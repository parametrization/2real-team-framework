# 2real-team-framework

A drop-in AI agent team framework for [Claude Code](https://claude.ai/code) projects. Bootstrap a simulated team of specialized agents with persistent identities, trust matrices, feedback loops, and structured workflows — all driven by Claude Code's agent tooling.

## What is this?

When working with Claude Code on complex software projects, a single AI agent can struggle with coordination, context management, and quality control. **2real-team-framework** solves this by scaffolding a complete simulated team structure:

- **Manager** who decomposes work, creates GitHub Issues, and coordinates
- **Architects** who design systems and review for compliance
- **Engineers** who implement in isolated worktrees
- **QA, Security, and Data specialists** for quality gates

Each team member has a persistent name, personality, git identity, communication style, and trust relationships with other members. They commit under their own names, review each other's work, give feedback, and can be "fired and replaced" when performance drops.

## Installation

### Python (pip)

```bash
pip install 2real-team-framework
```

### Node.js (npm)

```bash
npm install -g 2real-team-framework
```

## Quick Start

```bash
# Bootstrap a new project with interactive prompts
2real-team init

# Or specify everything up front
2real-team init --preset fullstack-monorepo --team-size 10 --project-name my-app

# Use a preset for data-heavy projects
2real-team init --preset data-pipeline --project-name my-etl
```

This creates the following in your project:

```
.claude/
  team/
    charter.md           # Team rules, org chart, workflows
    trust_matrix.md      # Directional trust scores between members
    feedback_log.md      # Feedback history
    roster/
      manager_*.md       # One card per team member
      tech_lead_*.md
      ...
  skills/
    retro.md             # Wave retrospective skill
    wave-start.md        # Initialize a new wave
    wave-end.md          # Finalize a wave
    review-pr.md         # PR review using charter format
    plan-phase.md        # Phase planning skill
    close-stale-issues.md
  CLAUDE.md              # Team section for your project's CLAUDE.md
```

## Commands

| Command | Description |
|---------|-------------|
| `2real-team init` | Bootstrap team framework in a project |
| `2real-team add-member` | Add a new team member to the roster |
| `2real-team remove-member <name>` | Archive a team member (prefix with `_departed_`) |
| `2real-team update-member <name>` | Update role, level, or other fields |
| `2real-team randomize-member <name>` | Fire and replace with a new random identity |
| `2real-team validate` | Check charter, roster, and skills consistency |
| `2real-team status` | Show team composition and project status |

### `init` options

| Option | Description |
|--------|-------------|
| `--preset <name>` | Project preset: `fullstack-monorepo`, `data-pipeline`, `library` |
| `--team-size <n>` | Override the preset's default team size |
| `--project-name <name>` | Project name (defaults to directory name) |
| `--config <path>` | Path to a YAML config file |
| `--target <dir>` | Target directory (defaults to `.`) |
| `--no-interactive` | Disable interactive prompts |
| `--git-email-prefix <prefix>` | Email prefix (e.g., `myorg` produces `myorg+First.Last@gmail.com`) |

## Presets

### `fullstack-monorepo` (default size: 10)
Full-stack application with frontend, backend, and data pipeline. Includes Manager, System Architect, DevOps, Tech Lead, Engineers, QA, and Security.

### `data-pipeline` (default size: 12)
Data engineering pipeline with ETL, graph/relational databases, and analytics. Adds DevOps Architect, Data Lead, Data Engineers, and Data Scientist roles.

### `library` (default size: 5)
Focused team for open-source libraries or SDKs. Lean structure: Manager, Tech Lead, Principal + Senior Engineer, QA.

## Skills

Skills are Claude Code slash commands installed in `.claude/skills/`. After bootstrapping:

- `/retro` — Run a wave retrospective (collect PRs, issues, CI failures, write report)
- `/wave-start` — Initialize a new deployments branch and clean worktrees
- `/wave-end` — Review, merge, and finalize all PRs for a wave
- `/review-pr <number>` — Review a PR using the charter's structured format
- `/plan-phase <number>` — Decompose a phase into issues with acceptance criteria
- `/close-stale-issues` — Audit and close issues resolved by merged PRs

## Case Study: isnad-graph

The framework was developed and battle-tested on [isnad-graph](https://github.com/parametrization/isnad-graph), a computational hadith analysis platform:

- **8 phases** of development (scaffolding through security/ops)
- **240+ pull requests** across the project lifecycle
- **14-member simulated team** with Manager, Architects, Engineers, QA, Security, and Data specialists
- Team members were fired and replaced based on performance feedback
- Trust matrix evolved organically based on actual delivery quality
- Wave-based deployment branches with structured peer review

The patterns, templates, and presets in this framework are directly extracted from that project's operational experience.

## How it works with Claude Code

1. **Bootstrap:** Run `2real-team init` in your project
2. **Start a session:** Claude Code reads `.claude/team/charter.md` and roster files
3. **Manager spawns team:** The Manager agent decomposes work and spawns specialists
4. **Isolated work:** Each engineer works in a git worktree via `isolation: "worktree"`
5. **Coordination:** Team members communicate via `SendMessage` tool
6. **Quality gates:** Peer review, tech debt tracking, trust scoring
7. **Feedback loops:** Retrospectives after each wave, firing underperformers

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes (both Python and Node implementations should stay in sync)
4. Run tests: `cd python && pytest` and `cd node && npm test`
5. Submit a PR

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
