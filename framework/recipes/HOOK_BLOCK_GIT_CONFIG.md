# Recipe: `block_git_config` hook

**Purpose**
Block `git config` writes to the `user.*` identity namespace so commit identity
is set only via per-commit `-c` flags.

**What it enforces / matches**
- Matches `git [globals] config ...` in any compound-command segment whose args
  name a `user.*` key (e.g. `user.name`, `user.email`, `user.signingkey`).
- Allowed (returns `None`): read-only ops (`--get`, `--get-all`, `--get-regexp`,
  `--list`/`-l`, `--show-origin`, `--show-scope`, incl. `=`-suffixed forms);
  writes to non-identity/operational keys (`core.hooksPath`, `commit.gpgsign`, …);
  and per-commit `git -c user.name=X commit` (that's a global flag, not `config`).
- False-positive guards: heredocs stripped + shlex tokenization so a literal
  "git config" inside prose/`--body-file`/`grep`/`echo` doesn't match.

**Config keys used**
- None. Generic message only (no opinionated knob).

**Adaptation notes**
- To protect more than identity, widen `_IDENTITY_KEY_RE`. To loosen, narrow it.
- Logging path comes from `paths.events_log` via `_framework_log`.
