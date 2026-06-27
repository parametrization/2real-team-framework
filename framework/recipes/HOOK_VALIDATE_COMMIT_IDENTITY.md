# Recipe: `validate_commit_identity` hook

**Purpose**
Make every commit attributable to a persona: require `git commit` to set its
author via per-commit `-c user.name=... -c user.email=...` flags (never global
or repo git config) and validate the pair against the team roster.

**What it enforces / matches**
- Matches a command-position `git [globals] commit ...` in any compound-command
  segment (bashlex AST when available, else shlex; heredoc bodies stripped).
- Also blocks indirect-exec wrappers that hide the commit from the outer
  command: `printf '...' | bash`, `bash -c '...'`, `bash <(...)`,
  `bash <<EOF...EOF`, `bash <<<'...'`, `eval '...'`, and `bash <script>`.
- Blocks when: a `-c user.name`/`-c user.email` flag is missing; the name is not
  in the roster; or the email does not match the roster entry for that name.
- Allows when: the email is in `identity.allow_emails`; the name/email pair
  matches a roster entry; or the command is not a git commit.
- Fail-CLOSED: if the command can't be parsed but looks like a git commit, it is
  blocked (this is a security-relevant matcher — it does not fail open).

**Roster shape** — flat JSON object, full name → email:

    { "Ada Lovelace": "team+Ada.Lovelace@example.com", ... }

A parent repo hosting the same `roster_source` is merged one level up
(meta-and-children); child entries win on a name collision.

**Config keys used**
- `identity.enforce` (bool, default `false`) — GATE; off → hook is a no-op.
- `identity.roster_source` (str, default `.claude/team/roster.json`) — repo-relative
  roster path; resolved from the config root, or a `cd`-target/cwd child repo.
- `identity.allow_emails` (list[str]) — emails accepted without a roster match.
- `identity.email_pattern` (str) — documentation only; shown in the error hint.

**Adaptation notes**
- Opt-in: set `identity.enforce: true` AND add `validate_commit_identity` to
  `hooks.pre_bash`. Leaving `enforce` false ships the file inert.
- Roster lives at `<config-root>/<roster_source>`; point `roster_source`
  elsewhere to relocate it. Install `bashlex` for the stronger structural parse.
