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
6. **For meta+children, splits into per-child union rosters** (see below).

## Per-child union rosters (meta+children model)

A single flat roster would let any persona commit in any repo. For the
meta+children model the generator partitions the team (`partition_for_children`)
so the commit-identity gate scopes engineers to their repo, reconstructing the
full allowlist per child via the gate's parent-merge:

- **Meta roster** (`<meta>/.claude/team/roster.json`) — org-level coordination
  roles only: Program Director, TPM, QA, Standards Lead, **plus the Tech Lead**
  and any domain engineer that matched no child (fallback, never dropped). The
  meta dir also holds **all** persona cards (org documentation) + the org
  `trust_matrix.md` / `feedback_log.md`.
- **Each child roster** (`<child>/.claude/team/roster.json`) — the Tech Lead (so
  a child cloned alone still has a lead identity) + every domain engineer whose
  `domains` intersect that child's sniffed stacks. Child dirs get their members'
  persona cards but **not** the org artifacts (those stay at the meta).
- **The gate enforces `meta ∪ child`.** `validate_commit_identity` loads the
  child's roster and merges its parent (meta) roster one level up (child wins on
  collision). So a child PR is signable by that child's engineers **and** the org
  leads — but not by a *different* child's engineers.

Role→domain mapping lives in `_ROLE_DOMAINS` / `_ORG_ROLES` / `_LEAD_ROLE` in
`roster_gen.py` — the single place to tune which stacks a role serves.

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
- **Per-child rosters** — implemented (see "Per-child union rosters" above). The
  meta gets org roles + all cards + org artifacts; each child gets its own
  `.claude/team/roster.json` (lead + domain engineers) and the gate enforces
  `meta ∪ child`. To change who lands where, edit `partition_for_children` /
  `_ROLE_DOMAINS` in `roster_gen.py`.
