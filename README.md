# 2real-team-framework

[![CI](https://github.com/parametrization/2real-team-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/parametrization/2real-team-framework/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/2real-team-framework)](https://pypi.org/project/2real-team-framework/)
[![npm](https://img.shields.io/npm/v/2real-team-framework)](https://www.npmjs.com/package/2real-team-framework)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

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

# With AI persona generation support
pip install '2real-team-framework[ai]'
```

### Node.js (npm)

```bash
npm install -g 2real-team-framework

# Or use without installing
npx 2real-team-framework init --preset library
```

## Quick Start

```bash
# 1. Bootstrap a new project with interactive prompts
2real-team init

# 2. Review the generated team structure
2real-team status

# 3. Validate everything is in place
2real-team validate
```

Or specify everything up front:

```bash
2real-team init --preset fullstack-monorepo --team-size 10 --project-name my-app
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
| `--config <path>` | Path to a YAML config file (see below) |
| `--target <dir>` | Target directory (defaults to `.`) |
| `--no-interactive` | Disable interactive prompts |
| `--git-email-prefix <prefix>` | Email prefix (e.g., `myorg` produces `myorg+First.Last@gmail.com`) |
| `--ai-personas` | Use Claude API to generate rich, diverse personas |
| `--seed <n>` | Seed for reproducible AI persona generation |

## Configuration File

Instead of command-line flags, you can use a YAML config file for repeatable, automated bootstrapping:

```yaml
# config.yaml
preset: library
project_name: my-library
team_size: 4
git_email_prefix: myorg
skills:
  - retro
  - wave-start
  - wave-end
members:
  - name: Alice Chen
    role: Tech Lead
    level: Staff
  - name: Bob Garcia
    role: Software Engineer
    level: Senior
```

```bash
2real-team init --config config.yaml
```

Config file fields:

| Field | Type | Description |
|-------|------|-------------|
| `preset` | string | **Required.** Preset name |
| `project_name` | string | Project name |
| `team_size` | integer | Team size override |
| `git_email_prefix` | string | Email prefix |
| `target` | string | Target directory |
| `skills` | list | Override preset's default skills list |
| `members` | list | Per-member overrides (name, role, level, personality) |

See `examples/` for sample configs for each preset.

## AI Persona Generation

Generate culturally diverse, role-appropriate personas using Claude:

```bash
# Requires ANTHROPIC_API_KEY in environment
export ANTHROPIC_API_KEY=sk-ant-...

# Generate AI personas
2real-team init --preset library --ai-personas

# Reproducible results with a seed
2real-team init --preset library --ai-personas --seed 42
```

Install the optional AI dependency:

```bash
# Python
pip install '2real-team-framework[ai]'

# Node
npm install @anthropic-ai/sdk
```

If the API key is missing or the SDK isn't installed, the CLI falls back to the built-in name pool with a warning.

## Presets

| Preset | Default Size | Required Roles | Description |
|--------|-------------|----------------|-------------|
| `fullstack-monorepo` | 10 | Manager, System Architect, DevOps Engineer, Tech Lead, Principal Engineer | Full-stack application with frontend, backend, and infrastructure |
| `data-pipeline` | 12 | Manager, System Architect, DevOps Architect, DevOps Engineer, Tech Lead, Data Engineer | Data engineering with ETL, databases, and analytics |
| `library` | 5 | Manager, Tech Lead, Principal Engineer | Lean team for open-source libraries or SDKs |

All presets include 6 skills: `retro`, `wave-start`, `wave-end`, `review-pr`, `plan-phase`, `close-stale-issues`.

## Skills

Skills are Claude Code slash commands installed in `.claude/skills/`. After bootstrapping:

- `/retro` — Run a wave retrospective (collect PRs, issues, CI failures, write report)
- `/wave-start` — Initialize a new deployments branch and clean worktrees
- `/wave-end` — Review, merge, and finalize all PRs for a wave
- `/review-pr <number>` — Review a PR using the charter's structured format
- `/plan-phase <number>` — Decompose a phase into issues with acceptance criteria
- `/close-stale-issues` — Audit and close issues resolved by merged PRs

## How it works with Claude Code

1. **Bootstrap:** Run `2real-team init` in your project
2. **Start a session:** Claude Code reads `.claude/team/charter.md` and roster files
3. **Manager spawns team:** The Manager agent decomposes work and spawns specialists
4. **Isolated work:** Each engineer works in a git worktree via `isolation: "worktree"`
5. **Coordination:** Team members communicate via `SendMessage` tool
6. **Quality gates:** Peer review, tech debt tracking, trust scoring
7. **Feedback loops:** Retrospectives after each wave, firing underperformers

## Dual CLI Architecture

The framework provides identical CLIs in both Python and Node.js. They share the same:

- **Templates** — Mustache templates in `templates/` (logic-less, works in both ecosystems)
- **Presets** — JSON preset definitions in `presets/`
- **Skills** — Skill templates in `skills/`

Neither implementation depends on the other. Use whichever fits your toolchain.

## Case Study: isnad-graph

The framework was developed and battle-tested on [isnad-graph](https://github.com/parametrization/isnad-graph), a computational hadith analysis platform:

- **8 phases** of development (scaffolding through security/ops)
- **240+ pull requests** across the project lifecycle
- **14-member simulated team** with Manager, Architects, Engineers, QA, Security, and Data specialists
- Team members were fired and replaced based on performance feedback
- Trust matrix evolved organically based on actual delivery quality
- Wave-based deployment branches with structured peer review

The patterns, templates, and presets in this framework are directly extracted from that project's operational experience.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and PR guidelines.

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
