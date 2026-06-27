# Recipe: `warn_pipe_mask_rc` hook

## Purpose
Catch the universal footgun where a `git push` / `gh pr merge` is piped into a
downstream command (`| tail`, `| head`, `| cat`, `| tee`, `| grep`, …). Absent
`set -o pipefail`, the pipeline's exit code is the LAST stage's rc, so a
REJECTED push or failed merge exits 0 and reads as SUCCESS.

## What it does
PostToolUse / Bash, advisory only (never blocks). Exposes
`check(input_data) -> dict | None` returning `{"systemMessage": ...}` plus a
`main()`. Two tiers:
- **TIER 1 — confirmed masked failure:** rc-masking shape present AND the
  captured output carries a real failure signal (or pipeline exited non-zero).
  Hard, prominent diagnostic.
- **TIER 2 — footgun shape only:** masking shape present but no failure this
  run. Soft nudge to drop the pipe / add `; echo rc=$?` / `set -o pipefail`.

Detection: bashlex AST (command-position correct) with a shlex/regex fallback
when bashlex is unavailable or a command fails to parse. Pipefail anywhere in
the command suppresses the warning. Heredoc/quoted/data positions are excluded
via the shared `_shell_parse` parsers.

## Config keys used
None. Generic-ready — no `_framework_config` / `_framework_log` import, no
opinionated knob.

## Adaptation notes
- Requires `_shell_parse.py` in the same hooks dir (imports
  `find_git_subcommand`, `find_gh_subcommand`, `iter_command_segments`,
  `strip_heredocs`, `tokenize`).
- `bashlex` is an optional dep; install it for AST-accurate detection, otherwise
  the degraded fallback runs. No new required deps.
- Wire into the PostToolUse dispatcher (`post_dispatcher.py`) like other Bash
  PostToolUse hooks.
- To cover more VCS/host verbs, extend `_tokens_push_merge_label`; to recognise
  more failure text, extend `_FAILURE_MARKERS`.
