# Contributing to 2real-team-framework

## Development Setup

### Python

```bash
cd python
pip install -e ".[dev]"
```

### Node

```bash
cd node
npm install
```

## Running Tests

```bash
# Python (97+ tests)
cd python && pytest tests/

# Node (83+ tests)
cd node && npm test
```

## Linting

```bash
# Python
cd python && ruff check src/ tests/

# Node
cd node && npm run lint
```

## Type Checking

```bash
# Python
cd python && mypy src/

# Node
cd node && npx tsc --noEmit
```

## Project Structure

```
2real-team-framework/
  templates/     # Shared Mustache templates (both CLIs read these)
  presets/       # JSON preset definitions (team shapes)
  skills/        # Skill template files
  examples/      # Example YAML config files
  python/        # Python CLI (typer, pydantic, chevron)
    src/real_team/
      cli.py         # CLI commands
      bootstrap.py   # Core bootstrap logic
      models.py      # Pydantic models
      personas.py    # AI persona generation
      presets.py     # Preset loading
      templates.py   # Template rendering
    tests/
  node/          # Node CLI (commander, mustache)
    src/
      index.ts       # CLI entry point
      bootstrap.ts   # Core bootstrap logic
      personas.ts    # AI persona generation
      presets.ts     # Preset loading
      templates.ts   # Template rendering
    tests/
```

## Adding a New Preset

1. Create `presets/<name>.json` with the preset schema:

```json
{
  "name": "my-preset",
  "description": "Description of the team shape",
  "default_team_size": 5,
  "roles": [
    {"role": "Manager", "level": "Senior VP", "count": 1, "required": true},
    {"role": "Engineer", "level": "Senior", "count": 2, "required": false}
  ],
  "skills": ["retro", "wave-start", "wave-end", "review-pr", "plan-phase", "close-stale-issues"],
  "default_ci": "github-actions"
}
```

2. Add tests in both `python/tests/test_cli.py` and `node/tests/cli.test.ts`.

## Adding a New Template

1. Create `templates/<name>.md.mustache` using Mustache syntax.
2. Available variables: `{{project_name}}`, `{{#team_members}}...{{/team_members}}`.
3. Each team member has: `{{name}}`, `{{role}}`, `{{level}}`, `{{email}}`, `{{personality}}`, `{{agent_name}}`, `{{reports_to}}`.

## Adding a New Skill

1. Create `skills/<name>.md.mustache` with the skill template.
2. Add the skill name to the relevant preset's `skills` array.
3. The skill file will be rendered and installed to `.claude/skills/<name>.md`.

## PR Process

1. Fork the repository
2. Create a feature branch from `main`
3. Make changes in **both** Python and Node implementations
4. Run tests and linting for both
5. Submit a PR with a clear description

## Code Conventions

- **Python**: ruff for linting/formatting, mypy strict mode, pydantic models
- **Node**: TypeScript strict, eslint, vitest for testing
- **Templates**: Mustache (logic-less, works in both ecosystems)
- **All changes need tests in BOTH Python and Node**
