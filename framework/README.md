# `framework/` — the genericised, installable layer

This directory is the **product-neutral, config-driven** extraction of the
orchestration machinery scanned in `intake/noorinalabs-2026-06/`. Where the
intake is raw candidate material and `generic_prompts/` is authoring recipes,
this is **runnable code you install into a repo**.

It is a working vertical slice — the keystone config + the highest-value
safety/SCM/CI hooks + a deterministic bootstrapper — built so the rest of the
corpus (the 36 net-new artifacts in `intake/.../GENERICISATION-BACKLOG.md`) can
be added against the same contract.

## Architecture: config → assets → bootstrap → dispatcher

```
                       framework/config/framework.config.schema.json   ← the contract
                                        │ (documented, defaults baked in)
                                        ▼
   operator writes  ──►  .claude/framework.config.json   ← one shared-config object
                                        │
   _framework_config.config(input_data).get("dotted.key", default)     ← every hook reads it
                                        │
   bootstrap.py  ──►  copies framework/assets/{hooks,lib}/ into <repo>/.claude/
                 ──►  writes <repo>/.claude/framework.config.json
                 ──►  merges dispatcher wiring into <repo>/.claude/settings.json
                                        │
   Claude Code fires  ──►  .claude/hooks/dispatcher.py (PreToolUse/Bash)
                       ──►  .claude/hooks/post_dispatcher.py (PostToolUse/Bash)
                                        │ reads hooks.pre_bash / hooks.post_bash
                                        ▼
                       runs each check(input_data) in order; first block wins
```

Three design rules make this robust:

1. **One shared-config object.** Every opinionated value (org, branch grammar,
   reviewer count, admin-merge exceptions, CI policy, shell) lives in
   `.claude/framework.config.json`. Hooks read it through `_framework_config`;
   none hard-codes a project choice. This is the lever that turned ~77
   "needs-genericisation" artifacts into a config edit instead of a rewrite.
2. **Stdlib only, fail-open.** No third-party deps — a freshly-cloned repo's
   hooks run with zero install step. A missing/invalid config degrades to safe
   defaults; a hook that raises is skipped; the gate never crashes the tool call.
3. **The dispatcher seam is config.** `hooks.pre_bash` / `hooks.post_bash` list
   the active checks in order. Enable/disable/reorder a check by editing config,
   not code.

## Layout

```
framework/
  config/
    framework.config.schema.json    # JSON Schema — the documented contract
    framework.config.example.json   # a filled meta-and-children example
    README.md                       # field-by-field docs
  assets/                           # what the bootstrapper installs into <repo>/.claude/
    hooks/
      _framework_config.py          # config loader (dotted-path getter over defaults)
      _framework_log.py             # generic event/audit logger (JSONL)
      _shell_parse.py               # command-position git/gh parser (foundation)
      _repo_flag_parse.py           # --repo/-R extractor
      dispatcher.py                 # PreToolUse entry point (reads hooks.pre_bash)
      post_dispatcher.py            # PostToolUse entry point (reads hooks.post_bash)
      block_no_verify.py            # SAFETY: refuse --no-verify
      block_git_config.py           # SAFETY: refuse git config user.* mutation
      no_worktree_self_delete.py    # SAFETY: refuse a worktree deleting itself
      warn_zsh_wordsplit.py         # SAFETY: zsh bash-ism advisory (shell==zsh)
      warn_pipe_mask_rc.py          # SCM: rc-masking pipe advisory (PostToolUse)
      validate_labels.py            # SCM: block gh issue create on a missing label
      validate_pr_ci_status.py      # CI: block gh pr merge on red/empty rollup
      validate_workflow_paths_coverage.py  # CI: empty-rollup discriminator + orphan-workflow flag
      block_squash_wave_merge.py    # CI: block --squash into an integration branch (identity on)
      validate_commit_identity.py   # TEAM: commits must carry a roster identity (opt-in)
    lib/
      pr_ci_state.py                # merge-readiness oracle (shares the gate's classifier)
      upsert_status_keys.py         # text-level JSON upsert (compact-shape-preserving)
      trust_signals.py              # TEAM: mechanical per-engineer trust scoring
      lifecycle.py                  # TEAM: wave/iteration state machine (allocator + transitions + merge model)
      ontology_gen/                 # ONTOLOGY: structural code-graph generator + cross-repo aggregator
    hooks/ (ontology, cont.)
      ontology_tracker.py           # ONTOLOGY: PostToolUse change-tracker (semantic-overlay checksums)
    skills/
      wave-lifecycle/SKILL.md       # the generic config-driven orchestration skill
      session-start/SKILL.md        # SESSION: first-action orientation (memory/team/handoff/git/CI/lifecycle/ontology)
      handoff/SKILL.md              # SESSION: write a durable pickup note to project memory
      ontology-librarian/SKILL.md   # ONTOLOGY: read-only two-layer staleness + lookup
      ontology-rebuild/SKILL.md     # ONTOLOGY: reconcile the semantic overlay from code
    settings.template.json          # the dispatcher wiring the bootstrap merges
  install/
    bootstrap.py                    # deterministic installer (new or existing repo)
    roster_gen.py                   # repo-introspecting roster generator (used by bootstrap)
  recipes/                          # per-artifact recipe docs (Purpose/enforces/config/adapt)
  tests/
    test_bootstrap_smoke.py         # installs into a tmp repo + fires the gate end-to-end
    test_roster_gen.py              # introspection + role derivation + identity loop
```

## Bootstrapping a repo

Determinism is the priority; prompts are opt-in. All of these are idempotent —
re-running changes nothing unless you pass `--force`.

```bash
# Minimal deterministic install (new or existing repo):
python3 framework/install/bootstrap.py /path/to/repo --owner my-org

# Reproducible install from a prepared config:
python3 framework/install/bootstrap.py /path/to/repo --config my.framework.config.json

# Preview only:
python3 framework/install/bootstrap.py /path/to/repo --owner my-org --dry-run

# Interactive fill of missing required fields (TTY):
python3 framework/install/bootstrap.py /path/to/repo --interactive
```

The bootstrapper: copies `assets/{hooks,lib}` into `<repo>/.claude/`, writes
`<repo>/.claude/framework.config.json` (defaults + your flags/config), merges
the dispatcher wiring into `<repo>/.claude/settings.json` (preserving any existing
settings), and — by default — **introspects the repo and generates a fitting team
roster** (next section). Then restart Claude Code in the repo so the hooks load.

The settings merge also ships a **curated `permissions.allow` allowlist** so a fresh
install doesn't prompt for the framework's own runtime: Edit/Read/Write on `.claude/**`,
running the installed hooks/libs via `python3`, and common `.claude` directory shell ops
(mkdir/ls/cat/cp/mv). Every rule is relative and `.claude/`-scoped — nothing broad, no
absolute paths. The merge is a union: your existing rules are preserved and re-running
adds nothing twice. Opt out with `--no-permissions` (hook wiring still merges; an
existing permissions block is left untouched).

## The team / identity layer (generated by introspection)

By default the bootstrapper examines the target repo and writes a simulated-team
roster that fits it (`roster_gen.py`; full detail in
`recipes/ROSTER_GENERATION.md`):

- **Detects the model** — single repo, or a meta-repo + child repos (a child is a
  subdir that is its own git repo).
- **Sniffs each repo's stack** (Python/Node/TS/frontend/Rust/Go/Java/infra/CI/
  data/security) from marker files + name hints.
- **Derives a role mix** — single repo → Tech Lead + Engineer + QA; meta+children
  → Program Director + TPM + per-domain engineers (Frontend / DevOps / Security /
  Data as detected) scaled by repo count + QA + Standards Lead.
- **Writes** `<repo>/.claude/team/`: `roster.json` (the name→email allowlist),
  one persona card per member, a seeded `trust_matrix.md`, an empty `feedback_log.md`.
- **For meta+children, writes per-child union rosters** — the meta roster holds
  org roles (PD/TPM/QA/Standards) + the Tech Lead; each child gets its own
  `roster.json` (lead + that child's domain engineers). The identity gate
  enforces `meta ∪ child` via its parent-merge, so a child PR is signable by that
  child's engineers + the org leads, not by another child's engineers.
- **Enables the identity gate** — sets `identity.enforce=true` and puts
  `validate_commit_identity` first in `hooks.pre_bash`, so every commit must carry
  a roster identity (`git -c user.name=… -c user.email=…`).

```bash
python3 framework/install/bootstrap.py /path/to/repo --owner my-org              # generate + enforce
python3 framework/install/bootstrap.py /path/to/repo --owner my-org --interactive  # review/adjust first
python3 framework/install/bootstrap.py /path/to/repo --owner my-org --team-size 6  # pin headcount
python3 framework/install/bootstrap.py /path/to/repo --owner my-org --no-team       # hooks only
python3 framework/install/bootstrap.py /path/to/repo --owner my-org --no-enforce-identity
```

Trust is scored mechanically from wave signals (`lib/trust_signals.py` — the pure
scoring model is product-neutral; the merged-PR extraction is config-driven with
two documented project-coupling points feeding off the lifecycle/state file).

## Installing via the `2real-team` CLI

The standalone `framework/install/bootstrap.py` above is the canonical installer.
The published `2real-team` CLI (`python/`) now drives it too: `2real-team init`
scaffolds the mustache team (charter/roster/trust matrix) **and** installs this
config-driven runtime by default (`--with-hooks`, on by default; `--no-hooks` to
skip). The framework assets are bundled into the wheel (`real_team/_bundled/
framework/`) and the CLI invokes the bundled `install/bootstrap.py --no-team`
(the CLI already wrote the roster). So a single `init` lays down a complete,
runnable `.claude/` — hooks, libs, lifecycle, the skill, config, and the
dispatcher wiring — not templates alone.

## What's covered vs. what's next

**Working, tested end-to-end (`tests/`, 47 passing):** the config keystone, the
loader/logger/parsers, both dispatchers (Bash + file-tool), 11 hooks (4 safety +
2 SCM + 3 CI + 1 identity + 1 ontology change-tracker), 4 libs + the
`ontology_gen` structural generator/aggregator, the deterministic bootstrapper
(installing the hook set, a recursive `lib/` incl. subpackages, and a skills
tree), the repo-introspecting roster generator with per-child union rosters
(single-repo + meta+children + the generated-roster→identity-gate loop), and the
skills: `wave-lifecycle` (driving `lifecycle.py` + `trust_signals.py`),
`session-start` + `handoff` (config-driven session lifecycle), and
`ontology-librarian` + `ontology-rebuild` (the two-layer ontology, applied to
meta+child git-repo subfolders — per-repo structural index + cross-repo
aggregation, plus the hand-curated semantic overlay tracked by the change-tracker
hook).

**Next (see `intake/.../GENERICISATION-BACKLOG.md`):** the full wave/phase
lifecycle skill chain (`phase-review` → `wave-scope` → `wave-kickoff` →
`wave-wrapup` → `wave-retro` + `board-audit`, on the `lifecycle.py` engine); the
review-gate tranche (`validate_pr_review` — the ~1189-line N-reviewer/TechDebt
gate — + the `pr_review_state` oracle that reuses it, + `validate_review_comment_format`);
`validate_branch_freshness`; a mid-wave reachability gh wrapper around
`lifecycle.classify_reachability`; optional LLM persona personalities (wire in
`python/src/real_team/personas.py`); and the **node CLI** runtime install (the
Python `2real-team init` is wired; the node `init` would subprocess `python3`
the same bundled bootstrap, since the runtime is Python-only). All layers meet at
the `framework.config.json` contract.
