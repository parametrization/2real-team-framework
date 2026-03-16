# 2real-team-framework — Product Requirements Document

## 1. Product Overview

**2real-team-framework** is a drop-in AI agent team framework for Claude Code projects. It provides a structured, configurable simulated team of specialized agents that collaborate via Claude Code's agent spawning, worktree isolation, and messaging capabilities.

The framework codifies lessons learned from building the isnad-graph computational hadith analysis platform (github.com/parametrization/isnad-graph) across 8 phases, 240+ PRs, and 14 team members.

### Problem Statement
Setting up a productive AI agent team in Claude Code requires significant upfront work: defining team structure, roles, communication protocols, branching strategy, review processes, feedback loops, and tooling. This is repeated for every new project.

### Solution
A CLI tool (`2real-team init`) that bootstraps a complete team framework with sensible defaults, customizable presets, and AI-generated team member personas — ready to work in minutes.

## 2. Target Users

- **Solo developers** using Claude Code who want structured AI collaboration
- **Small teams** using Claude Code for pair/team programming
- **Organizations** standardizing their Claude Code workflow across projects
- **Open source maintainers** who want consistent AI contributor patterns

## 3. Core Features

### 3.1 CLI Commands

| Command | Description |
|---------|-------------|
| `2real-team init` | Bootstrap a new project with team framework |
| `2real-team add-member` | Add a team member to the roster |
| `2real-team remove-member` | Archive a team member (departed prefix) |
| `2real-team update-member` | Update member config (role, level, preferences) |
| `2real-team randomize-member` | Regenerate name, background, personality, style |
| `2real-team validate` | Verify charter/roster/skills consistency |
| `2real-team status` | Show team composition + project status |

### 3.2 Bootstrap Modes
- **Interactive** (default): wizard-style, one question at a time
- **Flags**: `2real-team init --preset fullstack --team-size 8`
- **Config file**: `2real-team init --config team.yaml`

### 3.3 Project Presets

| Preset | Team Size | Key Roles |
|--------|-----------|-----------|
| fullstack-monorepo | 10 | Manager, Architect, DevOps, Tech Lead, 4 Engineers, QA, Security |
| data-pipeline | 12 | Manager, Architect, DevOps, Tech Lead, 4 Engineers, Data Lead, 2 Data Engineers, QA |
| library | 5 | Manager, Tech Lead, 2 Engineers, QA |

Future presets: backend-api, frontend-spa, mobile, desktop

### 3.4 Team Member Generation
- Archetype roles per preset (required + optional)
- User can customize count and levels
- AI generates random names, cultural backgrounds, personality profiles, communication styles
- Deterministic option (seed-based) for reproducible teams

### 3.5 Generated Artifacts
When `2real-team init` runs, it creates:
```
.claude/
├── team/
│   ├── charter.md           # Team rules, processes, branching, reviews
│   ├── roster/              # One file per team member
│   │   ├── manager_*.md
│   │   ├── architect_*.md
│   │   └── ...
│   ├── trust_matrix.md      # Directional trust scores
│   └── feedback_log.md      # Feedback tracking
├── skills/                  # Claude Code slash commands
│   ├── retro.md
│   ├── wave-start.md
│   ├── wave-end.md
│   ├── review-pr.md
│   ├── plan-phase.md
│   └── close-stale-issues.md
CLAUDE.md                    # Project-level instructions
```

### 3.6 Shared Mustache Templates
All artifacts are rendered from Mustache templates with project-specific variables. Templates are shared between Python and Node CLIs.

## 4. Technical Architecture

### 4.1 Dual CLI
- **Python**: typer + chevron (Mustache) + rich (terminal output) + pydantic (models)
- **Node**: commander + mustache + inquirer (prompts) + chalk (terminal output)
- Both CLIs share the same template files and preset definitions

### 4.2 Package Distribution
- **PyPI**: `pip install 2real-team-framework` → `2real-team` command
- **npm**: `npm install -g 2real-team-framework` or `npx 2real-team-framework` → `2real-team` command

### 4.3 Template Engine
Mustache (logic-less templates) — works natively in both Python (chevron) and Node (mustache.js).

## 5. Development Phases

### Phase 1: Core CLI + Templates (Current)
- [x] Project scaffold (Python + Node)
- [x] CLI command stubs
- [x] Mustache templates
- [x] 3 presets
- [x] 6 skill templates
- [x] CI/CD workflows
- [ ] Full `init` implementation with interactive mode
- [ ] Full `add-member` / `remove-member` / `update-member` / `randomize-member`
- [ ] Full `validate` + `status`
- [ ] Template rendering tests (both languages)
- [ ] End-to-end bootstrap test

### Phase 2: Polish + Publish
- [ ] Config file mode (YAML input)
- [ ] AI persona generation (integration with Claude API for name/background generation)
- [ ] Comprehensive test suite (Python pytest + Node vitest)
- [ ] PyPI first publish
- [ ] npm first publish
- [ ] Documentation site (or comprehensive README)

### Phase 3: Ecosystem
- [ ] Additional presets (backend-api, frontend-spa, mobile, desktop)
- [ ] Plugin system for custom presets
- [ ] Team migration tool (update framework version in existing projects)
- [ ] VS Code extension integration
- [ ] GitHub template repository

## 6. Success Metrics
- Bootstrap a working team framework in < 2 minutes
- All generated artifacts pass Claude Code validation
- Both pip and npm installations work on first try
- At least 3 presets cover 80% of use cases
- Test coverage > 90% for both CLIs

## 7. Non-Goals (Phase 1)
- Runtime agent orchestration (Claude Code handles this)
- IDE plugins
- Web UI for team management
- Multi-repo team coordination

## 8. Case Study: isnad-graph

The framework was extracted from the isnad-graph project (github.com/parametrization/isnad-graph):
- **8 phases** of development (scaffold → data → NER → graph → enrichment → API → testing → security)
- **240+ pull requests** managed by simulated team
- **14 team members** with distinct personas and specialties
- **400+ tests** across unit, integration, e2e, and fuzz categories
- **Key learnings**: wave-based execution, deployments branches, tech-debt tracking, retrospectives, trust matrix, peer review pairing

All skills, templates, and processes in this framework were battle-tested across those 8 phases.

## 9. License
Apache Software License 2.0
