# Shell-Aware Command Parser (shared hook helper)

**Purpose:** Give your `Bash` PreToolUse/PostToolUse hooks a single, tested primitive for understanding a shell command instead of matching raw substrings/regexes against the command string. This eliminates the entire class of false positives where a matcher cannot distinguish a *command-position* token (an actual `git config` invocation) from *data-position* text (the words "git config" inside a heredoc body, a `--body` argument value, or a documentation string).

This is a **library module** (no `check()` entry point) that the other Bash hooks import. Build it first — most blocking/validating hooks depend on it.

---

## The rule it enforces (indirectly)

There is no single "rule" here. This helper is the substrate that makes every command-shape rule reliable:

- "Block `git config` user changes" must fire on a real `git config user.email=…` and **not** on a commit message that mentions `git config`.
- "Require 2 reviewers" / "block `<vcs> pr review`" must key on the command verb, not a substring.
- "Forward `--repo OWNER/NAME` to internal sub-calls" must read the flag value as a token, not greedily regex it out of an arbitrary string.

The transferable principle: **tokenize once, segment on shell operators, then locate command-position tokens explicitly.** Never crash on a malformed command — return a sentinel and let callers fall back.

## Code template (stdlib only — `shlex`, `re`, `subprocess`, `json`)

```python
#!/usr/bin/env python3
"""Shared shell-arg-aware parser helper for Bash hooks.

Tokenize with shlex, split on shell operators, locate command-position
tokens. Hooks import this instead of writing one-off regexes.

Caller contract: any function that returns None on a parse failure means
"could not parse". Security-relevant matchers MUST NOT treat None as
"allow" — fall back to a conservative regex or fail closed. Advisory
matchers may fail open.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from typing import Iterator

# Shell control tokens that separate one pipeline segment from the next.
# After shlex.split these survive as their own tokens (they are unquoted).
_SEGMENT_OPS = {";", "&&", "||", "|"}

# KEY=value env-var assignment at command position.
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*=")

# Heredoc opener <<['"]?DELIM['"]? ... DELIM (the four shell variants),
# matched non-greedily so repeated/nested heredocs collapse via iteration.
_HEREDOC_RE = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?.*?\n.*?\n\t*\1\b", re.DOTALL)

# POSIX line-continuation (backslash + newline). The harness passes the raw
# command including these; shlex would otherwise emit a stray newline token.
_LINE_CONTINUATION_RE = re.compile(r"\\\n[ \t]*")


def tokenize(cmd: str) -> list[str] | None:
    """shlex.split (posix). Returns None on parse error (unbalanced quote)."""
    try:
        return shlex.split(_LINE_CONTINUATION_RE.sub(" ", cmd), posix=True)
    except ValueError:
        return None


def strip_heredocs(cmd: str) -> str:
    """Remove all heredoc bodies; iterate to fixpoint for nested heredocs."""
    prev, cur = None, cmd
    while prev != cur:
        prev, cur = cur, _HEREDOC_RE.sub("", cur)
    return cur


def _strip_leading_env(seg: list[str]) -> list[str]:
    i = 0
    while i < len(seg) and _ENV_ASSIGN_RE.match(seg[i]):
        i += 1
    return seg[i:]


def iter_command_segments(tokens: list[str]) -> Iterator[list[str]]:
    """Split tokens on ; && || | and strip leading KEY=val env assignments."""
    cur: list[str] = []
    for tok in tokens:
        if tok in _SEGMENT_OPS:
            if cur:
                stripped = _strip_leading_env(cur)
                if stripped:
                    yield stripped
                cur = []
            continue
        cur.append(tok)
    if cur:
        stripped = _strip_leading_env(cur)
        if stripped:
            yield stripped


def find_tool_subcommand(
    segment: list[str], tool: str, value_globals: set[str], bool_globals: set[str]
) -> tuple[list[str], list[str]] | None:
    """If `segment` invokes `tool`, return (global_opts, [subcommand, ...rest]).

    Skips pre-subcommand global options so the returned subcommand is the
    real verb. `value_globals` consume a following token (e.g. `-c k=v`);
    `bool_globals` take none. Equals-forms (`--opt=val`) are single tokens.
    """
    if not segment or segment[0] != tool:
        return None
    globals_: list[str] = []
    i, n = 1, len(segment)
    while i < n:
        tok = segment[i]
        if tok in bool_globals:
            globals_.append(tok); i += 1; continue
        if tok in value_globals:
            globals_.append(tok)
            if i + 1 < n:
                globals_.append(segment[i + 1]); i += 2
            else:
                i += 1
            continue
        if "=" in tok and tok.split("=", 1)[0] in value_globals:
            globals_.append(tok); i += 1; continue
        return globals_, segment[i:]  # first non-option token = subcommand
    return None


def walk_flag_values(tokens: list[str], wanted: set[str]) -> list[str]:
    """Values of every flag in `wanted`, in source order. Handles
    `--flag value` and `--flag=value`. A value buried inside another flag's
    value is ignored because it arrives as a SINGLE shlex token."""
    values: list[str] = []
    i, n = 0, len(tokens)
    while i < n:
        tok = tokens[i]
        if tok in wanted and i + 1 < n:
            values.append(tokens[i + 1]); i += 2; continue
        hit = next((f for f in wanted if tok.startswith(f + "=")), None)
        if hit:
            values.append(tok[len(hit) + 1:])
        i += 1
    return values


def first_flag_value(command, wanted, *, regex_fallback=True) -> str | None:
    """Tokenize and return the first value for any flag in `wanted`.
    On tokenize failure, optionally fall back to a boundary-anchored regex
    (longest flag first). Security-critical callers pass regex_fallback=False
    to fail closed."""
    tokens = tokenize(command)
    if tokens is None:
        if not regex_fallback:
            return None
        for flag in sorted(wanted, key=len, reverse=True):
            m = re.search(rf"(?:^|\s){re.escape(flag)}(?:=|\s+)(\S+)", command)
            if m:
                return m.group(1)
        return None
    vals = walk_flag_values(tokens, wanted)
    return vals[0] if vals else None


def resolve_tool_cwd(input_data: dict) -> str:
    """Return the harness-supplied cwd, else os.getcwd(). Reason about the
    USER's working dir, not the hook's parent-process dir."""
    cwd = input_data.get("cwd")
    return cwd if isinstance(cwd, str) and cwd else os.getcwd()


def extract_leading_cd_target(command: str) -> str | None:
    """Last absolute `cd <dir>` target in the command, or None. Recovers a
    worktree/subdir agent's real cwd from `cd /path && <work>` when the
    harness cwd field is captured at spawn time and lags later cd's."""
    tokens = tokenize(command)
    if tokens is None:
        return None
    target = None
    for seg in iter_command_segments(tokens):
        if len(seg) == 2 and seg[0] == "cd" and seg[1].startswith("/"):
            target = seg[1]
    return target


def resolve_invocation_cwd(input_data: dict) -> str:
    """Prefer an absolute existing `cd` target from the command; else
    resolve_tool_cwd. Use for any hook that derives repo IDENTITY from cwd."""
    cmd = (input_data.get("tool_input") or {}).get("command", "")
    if isinstance(cmd, str) and cmd:
        t = extract_leading_cd_target(cmd)
        if t and os.path.isdir(t):
            return t
    return resolve_tool_cwd(input_data)
```

### Optional: structural (AST) parse path

If a real grammar is available (e.g. an installed `bashlex`), add an `iter_command_segments_ast(command)` that walks a true AST — descending `&&`/`;`/`||` lists, pipelines, `$()`/backtick substitutions, and compound bodies — and returns the same `list[list[str]]` segment shape so existing consumers work unchanged. Import the dependency defensively (`try/except ImportError`) and return `None` when it is absent **or** the parse fails, so a fresh checkout with zero install still works via the shlex/regex path. Gate it behind a `parser_available() -> bool` so security-critical hooks can warn when running in degraded mode.

## How to adapt

- **Pick your tools.** The reference parses `git`/`gh` subcommands. Replace with whatever CLIs your rules key on (`docker`, `kubectl`, your own CLI). `find_tool_subcommand` is generic over the tool name and its global-option sets.
- **Structured-message guard.** If any hook reacts to a control message (e.g. a "shutdown request"), recognize it **only** as structured JSON (`type == "..."`), never as prose containing the phrase — plain text mentioning the keyword must not trigger it.
- **Repo-name resolution.** If a hook needs the repo name when a `--repo` flag is omitted, shell out to your VCS (`git -C <cwd> remote get-url origin`) and take the last path segment minus `.git`. Inject the runner so tests don't shell out.
- **Never crash.** Every entry point returns a sentinel (`None`/`[]`) on bad input. The dispatcher swallows exceptions too, but the helper should not rely on that.
- **Test against the failure shapes:** the keyword inside a heredoc body, inside a `--body`/`--message` value, behind a `KEY=val` env prefix, after a `cd && `, and with a malformed quote.
