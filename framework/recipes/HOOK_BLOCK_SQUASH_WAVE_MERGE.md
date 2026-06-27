# HOOK: block_squash_wave_merge

## Purpose

Block `gh pr merge <N> --squash` when the PR's base is an **integration branch**
and commit identity is enforced. A squash collapses every per-author content
commit into one squash commit re-authored to the merging principal — so the
integration→default PR then fails the commit-author identity gate
(`validate_commit_identity`) at wrapup. The fix is `--merge` (preserves per-author
commits; the merge commit is excluded by `--no-merges`).

## Enforces

A squash-merge into the integration branch (under enforced identity) is a
PreToolUse **hard block** (exit 2) with a `--merge` diagnostic. It is a hard
block, not advisory, because the fix is unambiguous and the failure mode is a red
gate at wrapup.

## Trigger / scope

Command-position `gh pr merge <N> --squash` (or `-s`) only. Narrowly scoped:

- **Gated on `identity.enforce`** — off → never blocks (the failure only exists
  when per-author commits matter). A normal GitHub-flow squash into the default
  branch on a non-persona project is untouched.
- **Integration-branch match** — the PR's base (resolved via `gh pr view`) is
  matched against a regex derived from `branch.integration` (its `{phase}` /
  `{wave}` tokens → `\d+`). A squash into `main`/default is allowed.

## Config

- `identity.enforce` (bool) — the gate.
- `branch.integration` (template, e.g. `deployments/phase-{phase}/wave-{wave}`) —
  the integration-branch pattern.

Ordered **last** in `hooks.pre_bash` (it makes a `gh pr view` network call).

## Fail posture

Fails **open** on any base-resolution error (offline, gh failure, non-numeric PR
token). `base_runner` is a test injection seam.

## Adapt

- A fixed integration branch name (e.g. `develop`): set `branch.integration` to
  the literal name (no tokens) — the regex matches it exactly.
- Pairs with `lifecycle.py` (`merge-model`) — both enforce the one-merge-model
  discipline; this is the squash half.
