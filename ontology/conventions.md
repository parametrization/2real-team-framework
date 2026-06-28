# Conventions — 2real-team-framework

The conventions this project holds itself to. Hand-curated semantic overlay; tracked by
`checksums.json` (edit → dirty → `/ontology-rebuild` reconciles against the code).

## Architecture

- **Config-driven.** Opinionated values are read through the one shared loader
  (`_framework_config.config`), never hard-coded. Behaviour changes are config edits, not code
  forks. The schema (`framework/config/framework.config.schema.json`) is the documented
  contract; `_DEFAULTS` is its runtime shadow — **keep the two in sync.**
- **Stdlib only, fail-open.** Hooks/libs use no third-party deps and never raise into a tool
  call: a missing/malformed config, an unreadable file, or a hook exception degrades to
  generic-but-safe behaviour. Config is JSON (stdlib), not YAML, for the same reason.
- **Dispatcher seam.** New event-time behaviour is a module exposing `check(input_data)` added
  to a `hooks.*` config list — not a new settings.json entry. PreToolUse may block (exit 2);
  PostToolUse and SessionStart are advisory (always exit 0).
- **Inert-by-default subsystems.** A subsystem that isn't configured does nothing (e.g. the
  ontology hooks are inert until an ontology dir exists), so assets are safe to wire everywhere.
- **Dual-deploy.** Every process/skill/hook must work IN this repo (wired into `.claude/`) AND
  deploy to a new/existing repo via `bootstrap.py`. The canonical copy lives in
  `framework/assets/…`; installs are additive/idempotent and never clobber a consumer's files.

## Ontology

- **Two layers, two maintainers.** The semantic overlay (`domain.yaml`, `services.yaml`,
  `conventions.md`) is hand-curated + checksum-tracked. The structural index
  (`structural/`) is generated wholesale by `ontology_gen` — never hand-edited.
- **This repo commits `structural/`** so the index travels with the code; the `ontology_refresh`
  SessionStart hook keeps it fresh (deterministic → only changes when source changes).
- **Generation excludes vendored/build dirs** (`node_modules`, `dist`, `build`, `coverage`) even
  when committed, so the index maps real code, not dependencies.

## Process

- **All work flows through the simulated Team** (`.claude/team/`); no work begins without it.
- **Commit identity** is per-commit via `-c user.name`/`-c user.email` from the roster card —
  **never** global/repo git config — with two `Co-Authored-By` trailers (member + Claude).
- **Branch → PR → review → merge.** Feature branches `{FirstInitial}.{LastName}/{IIII}-{slug}`;
  the default branch is always releasable; CI must be green before merge.
- **Approval gates.** Wave kickoff, merge to main, and release creation require explicit owner
  approval.
- **Worktrees** are the preferred isolation method for code-writing agents.
- **Orchestration core:** gh-cli, GitHub Issues/Projects/Actions — do not introduce alternatives.
