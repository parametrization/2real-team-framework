# Recipe: `block_no_verify` hook

**Purpose**
Block `--no-verify` / `-n` on `git commit`/`git push` so the pre-commit gate
can't be skipped.

**What it enforces / matches**
- Matches `git [globals] commit ...` or `git [globals] push ...` carrying
  `--no-verify` (either subcommand) or `-n` (commit only — `push -n` is dry-run,
  not a bypass), in any segment of a compound command.
- False-positive guards: heredocs/`--body`/`--body-file` bodies are stripped,
  and the command is shlex-tokenized so a data-position `--no-verify` (in
  `echo`, `gh issue create --body`, or a `-F msg.txt` file) is never confused
  with a command-position flag.

**Config keys used**
- `scm.allow_force` (bool, default `false`) — when `true`, `check()` returns
  `None` (the guard is disabled).

**Adaptation notes**
- Flip `scm.allow_force` to `true` to allow `--no-verify` for projects that
  intentionally permit force/no-verify.
- Logging path comes from `paths.events_log` via `_framework_log`.
