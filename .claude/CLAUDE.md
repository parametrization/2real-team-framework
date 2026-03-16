# CLAUDE.md — 2real-team-framework

## Project Overview
CLI tool for bootstrapping AI agent team frameworks in Claude Code projects. Dual Python (typer) + Node (commander) with shared Mustache templates.

## Tech Stack
- **Python 3.10+** with typer, chevron, rich, pydantic
- **Node 18+** with commander, mustache, inquirer, chalk
- **Templates**: Mustache (shared between both CLIs)
- **CI**: GitHub Actions (Python 3.10-3.13 + Node 18/20/22 matrix)
- **Publishing**: PyPI + npm on GitHub Release

## Build & Dev Commands
```bash
# Python
cd python && pip install -e ".[dev]"
pytest tests/
ruff check src/ tests/
mypy src/

# Node
cd node && npm install
npm test
npm run lint
npm run build
```

## Architecture
- `templates/` — Shared Mustache templates (both CLIs read these)
- `presets/` — JSON preset definitions (team shapes)
- `skills/` — Skill template files
- `python/src/real_team/` — Python CLI implementation
- `node/src/` — Node CLI implementation

## Code Conventions
- Python: ruff for linting/formatting, mypy strict, pydantic models
- Node: TypeScript strict, eslint, vitest
- Templates: Mustache (logic-less, works in both ecosystems)
- All changes need tests in BOTH Python and Node

## Key Design Decisions
- Mustache over Jinja2/Handlebars: only template engine native to both Python and Node
- Separate CLIs over wrapper: neither ecosystem depends on the other
- Presets as JSON: easily extensible, readable, no code required
- Apache 2.0: permissive but with patent protection
