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
      validate_pr_ci_status.py      # CI: block gh pr merge on red/empty rollup
      validate_workflow_paths_coverage.py  # CI: empty-rollup discriminator + orphan-workflow flag
    lib/
      pr_ci_state.py                # merge-readiness oracle (shares the gate's classifier)
      upsert_status_keys.py         # text-level JSON upsert (compact-shape-preserving)
    settings.template.json          # the dispatcher wiring the bootstrap merges
  install/
    bootstrap.py                    # deterministic installer (new or existing repo)
  recipes/                          # per-artifact recipe docs (Purpose/enforces/config/adapt)
  tests/
    test_bootstrap_smoke.py         # installs into a tmp repo + fires the gate end-to-end
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
`<repo>/.claude/framework.config.json` (defaults + your flags/config), and
merges the dispatcher wiring into `<repo>/.claude/settings.json` (preserving any
existing settings). Then restart Claude Code in the repo so the hooks load, and
confirm with a blocked action (`git commit --no-verify`).

## What's covered vs. what's next

**In this slice (working, tested end-to-end):** the config keystone, the
loader/logger/parsers, both dispatchers, 7 hooks (4 safety + 1 SCM advisory + 2
CI), 2 libs, and the bootstrapper. `tests/test_bootstrap_smoke.py` installs into
a tmp repo and asserts the gate fires.

**Next (see `intake/.../GENERICISATION-BACKLOG.md`):** the remaining net-new
hooks/libs/skills, the team/identity layer (roster schema, mechanical trust
scoring, the lifecycle skills), and — a larger, separate effort — wiring this
config-driven asset model into the existing `python/`+`node/` CLI so `init` can
render hooks, not just team-scaffolding templates. The two layers meet at the
`framework.config.json` contract.
