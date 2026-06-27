#!/usr/bin/env python3
"""PreToolUse hook: Refuse `git worktree remove` when cwd is inside target.

Running `git worktree remove <path>` while the shell's cwd is `<path>` (or a
descendant of it) unlinks the worktree while the process still holds the
directory open. The shell ends up in a dangling cwd, which typically requires
a session restart to recover. See noorinalabs/noorinalabs-main#173 for the
motivating incident (wave-8 retro item 5 — the footgun fired again during
cleanup and forced a restart).

The guard is a filesystem-level ancestry check, not a `git worktree list` parse.
Symlinks on either side are collapsed via `os.path.realpath` so that aliased
paths still match.

Input Language
==============

Fires on:
    PreToolUse Bash

Matches (one or more segments in the command, split on &&, ||, ;, |):
    [ENV=val ...] git [ -C <dir> ] [ -c k=v ... ] worktree remove [opts] <path>

    - Leading env-var assignments (`FOO=bar BAZ=qux git ...`) are stripped.
    - Global git options `-C <dir>` and `-c key=value` are skipped.
    - Short-option flags on `worktree remove` (`-f`, `--force`) are skipped.
    - `<path>` is the first non-flag argument after `remove`.
    - A leading `cd <dir>` IS honored when it names an absolute directory
      that exists on disk (#535): the cwd used for the ancestry check is the
      last such `cd` target (last-cd-wins via `resolve_invocation_cwd`),
      because that is where the shell will be when `git worktree remove`
      actually runs. `cd /safe && git worktree remove <wt>` therefore ALLOWS
      (shell moves out first) while `cd <wt> && git worktree remove <wt>`
      BLOCKS (the self-delete). A `cd <nonexistent>` is ignored — recovery
      falls back to the stdin `cwd`, so the guard never relaxes on a path
      that isn't there.

Does NOT match:
    git worktree list            (no `remove` subcommand)
    git worktree add <path>      (different subcommand)
    git worktree prune           (different subcommand)
    non-git commands containing the substring "worktree remove"
    git commit / git push / etc. (different subcommand)

Flag pass-through:
    None. The hook only needs the <path> argument; all other flags are
    parser-skipped, not extracted.

Block condition:
    Resolved(cwd) == Resolved(path)   OR
    Resolved(cwd) starts with Resolved(path) + os.sep

Allow condition:
    Any other arrangement (cwd is sibling, unrelated, or ancestor of path;
    path does not resolve to an existing directory on disk; parse failure).

Remediation message:
    Names a safe cwd to move to. Best-guess priority:
      1. `git rev-parse --show-superproject-working-tree` (if cwd is a
         worktree of a superproject; returns the superproject root).
      2. `git rev-parse --show-toplevel` with cwd set to the parent of the
         target worktree (gives the managing repo's root).
      3. Generic fallback: "cd to a known path outside <target> first".

Exit codes (per Claude Code hook convention):
    0 — allow (not a Bash call, not a `git worktree remove`, cwd is safe)
    2 — block (cwd is inside the target worktree)

Fail-open: any unexpected exception returns None (allow). Matches parent
dispatcher convention — hook bugs must never block the user.

Enforcement artifact for: noorinalabs/noorinalabs-main#173
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shell_parse import resolve_invocation_cwd  # noqa: E402
from annunaki_log import log_pretooluse_block  # noqa: E402

# Shell operators that separate command segments. We split on these to reach
# each `git worktree remove` invocation individually.
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||;|\|")

# Leading `FOO=bar` env-var assignments (one or more, space-separated).
_ENV_PREFIX_RE = re.compile(r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)+")

# `git` invocation with optional global options (-C dir, -c k=v).
# We shlex-split the segment and walk tokens instead of a monolithic regex —
# easier to reason about and robust to spacing.


def _strip_env_prefix(segment: str) -> str:
    """Drop leading `KEY=value ...` assignments from a command segment."""
    return _ENV_PREFIX_RE.sub("", segment, count=1).lstrip()


def _tokenize(segment: str) -> list[str]:
    """shlex-split the segment; return empty list on parse failure."""
    import shlex

    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        # Unmatched quotes etc. — we can't reason about it; fail open.
        return []


def _extract_worktree_remove_path(segment: str) -> str | None:
    """Return the `<path>` arg of `git worktree remove <path>`, else None.

    Handles:
      git worktree remove <path>
      git -C <dir> worktree remove <path>
      git -c k=v worktree remove <path>
      git worktree remove -f <path>
      git worktree remove --force <path>

    Returns None for all other shapes (list, add, prune, non-git, malformed).
    """
    clean = _strip_env_prefix(segment)
    tokens = _tokenize(clean)
    if len(tokens) < 4:
        return None

    if tokens[0] != "git":
        return None

    i = 1
    # Skip git-level options: -C <dir>, -c key=value, --flag, --flag=value
    while i < len(tokens):
        t = tokens[i]
        if t == "-C" and i + 1 < len(tokens):
            i += 2
            continue
        if t == "-c" and i + 1 < len(tokens):
            i += 2
            continue
        if t.startswith("--") or (t.startswith("-") and len(t) > 1 and not t.startswith("--")):
            # Some other short/long flag before the subcommand — skip.
            # Treat `-X=val` (no space) as one token. Treat `-X val` as two
            # only when X is known (-C, -c already handled above). Otherwise
            # assume single-token to avoid eating an argument we shouldn't.
            i += 1
            continue
        break

    # Subcommand: must be `worktree`
    if i >= len(tokens) or tokens[i] != "worktree":
        return None
    i += 1

    # Sub-subcommand: must be `remove`
    if i >= len(tokens) or tokens[i] != "remove":
        return None
    i += 1

    # Remaining tokens: skip flags (-f, --force, etc.), take the first
    # non-flag token as the <path>.
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("-"):
            i += 1
            continue
        return t

    return None


def _resolve(p: str) -> str:
    """Expand `~` and return an absolute realpath. Never raises."""
    try:
        return os.path.realpath(os.path.expanduser(p))
    except (OSError, ValueError):
        return p


def _cwd_is_inside(cwd: str, target: str) -> bool:
    """True if cwd == target or cwd is a strict descendant of target.

    Both paths are resolved to realpaths before comparison. Uses Path
    relative_to semantics to avoid prefix-string false positives like
    `/foo/bar` matching `/foo/bar-sibling`.
    """
    cwd_r = _resolve(cwd)
    tgt_r = _resolve(target)
    if not cwd_r or not tgt_r:
        return False
    if cwd_r == tgt_r:
        return True
    try:
        Path(cwd_r).relative_to(tgt_r)
        return True
    except ValueError:
        return False


def _suggest_safe_cwd(target: str) -> str:
    """Best-guess a safe cwd to recommend in the remediation message.

    Runs `git rev-parse` with the parent of <target> as cwd so we pick up
    the managing repo's root, not the target worktree itself.
    """
    parent = str(Path(_resolve(target)).parent)
    # First try superproject (if target is under a submodule-ish layout).
    for cmd in (
        ["git", "rev-parse", "--show-superproject-working-tree"],
        ["git", "rev-parse", "--show-toplevel"],
    ):
        try:
            out = subprocess.run(
                cmd,
                cwd=parent,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if out.returncode == 0:
            path = out.stdout.strip()
            if path:
                return path
    return ""


def _block_reason(target: str, cwd: str) -> str:
    safe = _suggest_safe_cwd(target)
    lines = [
        "BLOCKED: `git worktree remove` refuses — current directory is inside",
        "the worktree being removed.",
        f"  cwd:    {_resolve(cwd)}",
        f"  target: {_resolve(target)}",
        "",
        "Removing a worktree while your shell is inside it leaves the session in a dangling",
        "directory and typically forces a restart (see noorinalabs-main#173).",
        "",
    ]
    if safe:
        lines.append(f"Remediation: `cd {safe}` first, then re-run `git worktree remove`.")
    else:
        lines.append(
            "Remediation: cd to a known path outside the worktree being removed first, "
            "then re-run `git worktree remove`."
        )
    return "\n".join(lines)


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point.

    Returns None to allow; returns a block-dict to block.
    """
    try:
        tool_name = input_data.get("tool_name", "")
        if tool_name != "Bash":
            return None

        command = input_data.get("tool_input", {}).get("command", "")
        if not command or "worktree" not in command or "remove" not in command:
            # Cheap pre-filter — most Bash calls don't touch worktree remove.
            return None

        # Recover the cwd the shell will actually be in when `git worktree
        # remove` runs (#535). resolve_invocation_cwd applies last-cd-wins
        # recovery: it returns the target of the last `cd <absolute-existing
        # -dir>` in the command, else the stdin `cwd`, else os.getcwd().
        #
        # Unlike the gh-pr-create hooks — which adopt recovery to fix repo
        # IDENTITY — here recovery fixes the block/allow SAFETY verdict, and it
        # makes it MORE correct in BOTH directions:
        #   cd <wt> && git worktree remove <wt>   → resolves to <wt>  → BLOCK
        #       (this is the #173 self-delete the pre-#535 stdin-cwd read MISSED
        #        when the harness cwd was anchored at the parent, not <wt>).
        #   cd /safe && git worktree remove <wt>  → resolves to /safe → ALLOW
        #       (the shell moves out of <wt> first; not a self-delete).
        # The recovery only honors an absolute cd target that EXISTS on disk;
        # a `cd <nonexistent>` falls back to the stdin cwd, so we never relax
        # the guard on the strength of a directory that isn't there.
        cwd = resolve_invocation_cwd(input_data)

        for segment in _SEGMENT_SPLIT_RE.split(command):
            target = _extract_worktree_remove_path(segment)
            if target is None:
                continue
            if _cwd_is_inside(cwd, target):
                reason = _block_reason(target, cwd)
                return {"decision": "block", "reason": reason}

        return None
    except Exception:
        # Fail open — never let a hook bug block the user.
        return None


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result is None:
        sys.exit(0)

    print(json.dumps(result))
    if result.get("decision") == "block":
        command = input_data.get("tool_input", {}).get("command", "")
        log_pretooluse_block("no_worktree_self_delete", command, result["reason"])
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
