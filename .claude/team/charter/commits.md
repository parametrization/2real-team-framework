# Commit Identity

Every team member MUST commit using their personal git identity (from their roster
card's `## Git Identity` section). Identity is passed **per commit** with `-c` flags —
**never** modify the global or repo-level git config (enforced — see
[hooks.md](hooks.md)).

Every commit message MUST carry **two** `Co-Authored-By` trailers: one for the team
member and one for Claude.

```bash
git -c user.name="Firstname Lastname" -c user.email="<member-email>" commit -F /tmp/msg.txt
```

where `/tmp/msg.txt` contains:

```
Short imperative summary.

Optional body.

Co-Authored-By: Firstname Lastname <member-email>
Co-Authored-By: Claude <noreply@anthropic.com>
```

- **Email pattern:** member emails follow `{First}.{Last}@gmail.com` (diacritics removed
  from the email, preserved in `user.name`).
- **Message via `-F <file>`** (or a simple `-m "..."`), not a `-m "$(cat <<EOF …)"`
  heredoc — inline heredocs confuse shell-parsing enforcement hooks.
- **Source of truth:** the machine-readable roster (`.claude/team/roster.json`) is
  what the identity gate validates against. When a member is hired or replaced,
  update the roster — do not maintain a separate identity table here.
- **Never `--no-verify`**, and never bypass hooks to get a commit through
  (enforced — see [hooks.md](hooks.md)).
