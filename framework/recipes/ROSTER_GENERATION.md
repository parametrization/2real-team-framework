# Roster generation (bootstrap-time, repo-introspecting)

## Purpose

Generate a simulated-team roster **by examining the repo the framework is being
installed into**, so the team fits what's actually there — instead of a generic
stub. Runs as part of `bootstrap.py`; implemented in `framework/install/roster_gen.py`.

## What it does

1. **Detects the model** — single repo, or a meta-repo with child repos (child =
   an immediate subdir that is its own git repo). A `project.model` /
   `project.repos` in config overrides filesystem detection.
2. **Sniffs each repo's stack** from marker files + name hints: Python
   (`pyproject.toml`/`setup.py`), Node/TS (`package.json`/`tsconfig.json`),
   frontend (react/vue/svelte/next/astro deps), Rust/Go/Java, Docker/Terraform/
   K8s (→ infra), CI (`.github/workflows`), data, and security (auth/user/identity).
3. **Derives a fitting role mix** (deterministic): single repo → a focused team
   (Tech Lead + Engineer + QA). meta+children → Program Director + TPM + Tech
   Lead + per-domain engineers (Frontend if a UI repo, DevOps if infra, Security
   if an auth/user repo, Data if a pipeline repo), engineers scaled by repo
   count, + QA + Standards Lead. `--team-size N` trims/pads.
4. **Assigns personas** — distinct names from a built-in diverse pool (stable
   order → deterministic), emails from `identity.email_pattern`.
5. **Writes** into `<repo>/.claude/team/`: `roster.json` (the name→email
   allowlist the commit-identity gate reads), one persona card per member,
   a seeded `trust_matrix.md`, and an empty `feedback_log.md`.

When a roster is generated, the bootstrapper also sets `identity.enforce=true`
and puts `validate_commit_identity` first in `hooks.pre_bash` — so commits must
carry a roster identity. `--no-enforce-identity` writes the roster without the gate.

## Config keys used

`identity.email_pattern` (persona emails), `project.model` / `project.repos`
(override detection; also written back from detection). Output path:
`<repo>/.claude/team/` (sibling of `paths.team`).

## Usage

```bash
# Default: introspect + generate the team + enable the identity gate.
python3 framework/install/bootstrap.py /path/to/repo --owner my-org

# Review/adjust the proposed team before writing (TTY):
python3 framework/install/bootstrap.py /path/to/repo --owner my-org --interactive

# Pin the headcount / skip the team / roster-without-enforcement:
python3 framework/install/bootstrap.py /path/to/repo --owner my-org --team-size 6
python3 framework/install/bootstrap.py /path/to/repo --owner my-org --no-team
python3 framework/install/bootstrap.py /path/to/repo --owner my-org --no-enforce-identity
```

## Adaptation notes

- **Name pool** — extend `_NAME_POOL` in `roster_gen.py`; assignment is in-order
  for determinism. For richer, LLM-generated personalities, the existing
  `python/src/real_team/personas.py` is the upstream to wire in (needs an API key);
  this stdlib path stays deterministic and dependency-free.
- **Role heuristic** — `derive_roles()` is the single place to tune the mix; it
  reads the detected stacks/model. Mirror the `presets/*.json` role vocabulary.
- **Per-child rosters** — currently one roster at the install target. For the
  meta+children union-roster model, generate per-child `.claude/team/roster.json`
  and union them (the source project's `roster_union_sync` pattern) — a follow-up.
