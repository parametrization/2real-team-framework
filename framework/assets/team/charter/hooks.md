# Automated Enforcement (Framework Hooks)

Several charter rules are enforced automatically by the framework's Claude Code
hooks, installed under `.claude/hooks/` and wired through dispatchers in
`.claude/settings.json`. Which checks run is **config-driven**: the `hooks.*` lists
in `.claude/framework.config.json` name the active modules per event, and each hook
reads its policy values (owner `{{owner}}`, default branch `{{default_branch}}`,
reviewer count, identity roster, …) from that same config. All hooks are
stdlib-only, and fail open by default — a broken hook never blocks unrelated
work — with one deliberate exception: `require_load_bearing_test` (see below and
[pull-requests.md § Pre-Review Self-Check](pull-requests.md)) fails **closed** on
the review-request path, by owner-approved design (#167). "Fail open" is now an
explicit, per-hook opt-in (`FAIL_OPEN = True`) rather than the dispatcher's
implicit default: if a hook's `check()` raises an uncaught exception, the
dispatcher blocks unless that module declared itself fail-open, so a hook that
forgets to declare (like `require_load_bearing_test`, deliberately) fails closed
on its own crash too (#175).

## Rule → Enforcement Map

| Charter rule | Hook module | Event | Effect |
|---|---|---|---|
| Per-commit `-c` identity from the roster ([commits.md](commits.md)) | `validate_commit_identity` | PreToolUse (Bash) | Blocks `git commit` without `-c user.name`/`-c user.email` matching `{{team_dir}}/roster.json` (opt-in via `identity.enforce`) |
| Never bypass hooks ([commits.md](commits.md)) | `block_no_verify` | PreToolUse (Bash) | Blocks `--no-verify` / `-n` on `git commit` / `git push` |
| Never set global/repo git config ([commits.md](commits.md)) | `block_git_config` | PreToolUse (Bash) | Blocks `git config` writes to the identity namespace (reads allowed) |
| Worktree discipline ([branching.md](branching.md)) | `no_worktree_self_delete` | PreToolUse (Bash) | Refuses `git worktree remove` when the shell's cwd is inside the target |
| Don't merge red CI ([pull-requests.md](pull-requests.md)) | `validate_pr_ci_status` | PreToolUse (Bash) | Blocks `gh pr merge` when any status check is failing/pending |
| Identity survives the merge ([commits.md](commits.md)) | `block_squash_wave_merge` | PreToolUse (Bash) | Blocks `gh pr merge --squash` into an integration branch when identity is enforced (squash rewrites the author) |
| Labels must exist ([issues.md](issues.md)) | `validate_labels` | PreToolUse (Bash) | Validates `--label` values before `gh issue create` |
| Verdict-comment grammar ([issues.md](issues.md)) | `validate_review_comment_format` | PreToolUse (Bash) | Blocks a `gh pr comment` / `gh issue comment` whose body attempts the charter header but is malformed (missing field or unknown `RequestOrReplied` token) — keeps the shape `trust_signals.py` parses reliable (#98) |
| CI covers what a PR touches ([pull-requests.md](pull-requests.md)) | `validate_workflow_paths_coverage` | PreToolUse (Bash) | Blocks `gh pr create` when changed workflow-relevant paths escape every CI `paths:` filter |
| New behavior needs a load-bearing test ([pull-requests.md § Pre-Review Self-Check](pull-requests.md)) | `require_load_bearing_test` | PreToolUse (Bash) | **HARD, fail-CLOSED** — blocks `gh pr create`/`gh pr ready` when the diff adds a substantive line to a behavior file with no test-file change PAIRED to that specific file (checked per file, not once for the whole diff — #174), or when the diff itself can't be verified. Bypass only via a validated `LOAD_BEARING_TEST_EXCEPTION=<class>:<rationale>` naming a class configured under `policy.load_bearing_test_exceptions` (ships pre-seeded with a `refactor` class, #176) (#167) |
| Push unpiped ([pull-requests.md](pull-requests.md)) | `warn_pipe_mask_rc` | PostToolUse (Bash) | Flags `git push` / `gh pr merge` piped through rc-masking commands |
| Shell safety | `warn_zsh_wordsplit` | PreToolUse (Bash) | Advisory on bash-isms under zsh (when `shell: zsh`) |
| Ontology stays fresh | `ontology_tracker` / `ontology_refresh` | PostToolUse / SessionStart | Tracks semantic-overlay drift; regenerates the structural index (inert until an ontology dir exists) |

Not every gate is a runtime hook. Some charter rules are enforced by the CI test suite
(`framework/tests/`) instead — notably **reinstall-on-change**
([pull-requests.md](pull-requests.md)): `test_reinstall_parity.py` fails a PR that edits a
canonical mirrored Claude asset (`framework/assets/**`) without regenerating its live
`.claude/**` copy via `python3 framework/install/reinstall.py` (#116).

## Changing Enforcement

- **Enable/disable a check:** edit the relevant `hooks.pre_bash` / `hooks.post_bash`
  / `hooks.session_start` list in `.claude/framework.config.json`, then restart the
  Claude Code session.
- **Tune policy without touching code:** the same config carries the knobs the hooks
  read (`identity.enforce`, `scm.allow_force`, `policy.reviewers_required`,
  `ci.merge_requires_green`, …).
- **Emergency override:** remove the module name from the config list (preferred)
  or the dispatcher entry from `.claude/settings.json`. Overrides should be
  deliberate, visible, and reverted — a silently weakened gate is how the rules it
  guarded regress.

## Hooks Are the Floor, Not the Ceiling

A hook enforces the mechanical core of a rule; the charter text carries the intent.
Passing the hooks does not exempt anyone from the judgment parts of the charter
(review quality, honest completion reports, ground-truth verification). When a
process failure recurs, prefer promoting the fix into a hook over adding prose —
see the retro step in [agents.md](agents.md).
