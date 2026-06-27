#!/usr/bin/env python3
"""Shared shell-arg-aware parser helper for PreToolUse Bash hooks.

Background
==========

Multiple PreToolUse hooks have repeatedly tripped on substring/regex matching
against the raw Bash command string (issues #118, #134, #144, #188, #189,
#216, #223, #226, #227). Root cause: the matcher cannot tell *command-position*
tokens (e.g. an actual `git config` invocation) from *data-position* text
(e.g. the phrase "git config" inside a heredoc body, a `--body-file` argument
value, or a documentation string).

This module is the unifying primitive: tokenize once with shlex, segment-split
on shell operators, then locate command-position tokens explicitly. Hooks call
the small public API instead of writing one-off regexes.

Public API
==========

    tokenize(cmd) -> list[str] | None
        shlex.split with posix semantics. Returns None on parse failure
        (unbalanced quotes, etc.) so callers can fall back to a regex path.

        Caller contract: callers MUST handle None explicitly. Never treat
        None as "allow" for security-relevant matchers like commit-identity
        validation — fall back to a regex check or a fail-closed decision.
        For warn-only matchers, fail-open on None is acceptable.

    strip_heredocs(cmd) -> str
        Removes <<DELIM .. DELIM, <<'DELIM' .. DELIM, <<"DELIM" .. DELIM and
        <<-DELIM .. DELIM heredoc bodies (delimiter is rfc-shell-style: any
        word). Handles repeated/nested heredocs by iterating until the regex
        is fixed.

    iter_command_segments(tokens) -> Iterator[list[str]]
        Splits a token list on the shell-control tokens `;`, `&&`, `||`, `|`
        (these survive shlex.split as their own tokens because they're not
        inside quotes), strips leading `KEY=value` env-var assignments from
        each segment, and yields the surviving tokens.

    iter_command_segments_ast(command) -> list[list[str]] | None
        Structural (bashlex) alternative to tokenize + iter_command_segments:
        parses `command` into a real Bash AST and returns every
        command-position token segment, walking `&&`/`;`/`||` lists, `|`
        pipelines, `$(...)`/backtick command substitutions, and compound
        bodies. Each segment is the command's word tokens (env-var
        AssignmentNode prefixes excluded) in the SAME shape the shlex path
        emits — so `find_git_subcommand` / `extract_dash_c_pairs` consume AST
        segments unchanged. Returns None when bashlex is unavailable (degraded
        mode) OR the command fails to parse; callers MUST fall back to the
        shlex/regex path and must never treat None as "allow" for a
        security-relevant matcher. A real grammar removes the regex/shlex
        confusion between a command-position `git commit` and the literal
        phrase inside a heredoc body, a quoted arg, or a `--body` value — the
        root of the #118/#134/#144/#188/#189/#216/#223/#226/#227 bug trail
        (#748 D3b).

    bashlex_available() -> bool
        True iff the optional `bashlex` dependency imported successfully at
        module load. The commit-identity hook checks this to decide whether
        the structural path is active or it must warn + run in degraded
        regex-fallback mode. bashlex is the ENFORCED parser in CI + pre-commit
        (where the dependency is declared); a bare checkout without it still
        works via the shlex/regex fallback (zero-setup-on-pull is preserved).

    find_git_subcommand(segment) -> tuple[list[str], list[str]] | None
        Given a single segment's tokens, returns (global_opts, [subcommand,
        ...rest]) if it's a `git ...` invocation, else None. Skips git
        global options (`-c k=v`, `-C dir`, `--git-dir=...`,
        `--work-tree=...`, etc.) so the returned subcommand is the actual
        git verb (`commit`, `config`, `worktree`, ...).

    find_gh_subcommand(segment) -> tuple[list[str], list[str]] | None
        Same shape for `gh ...`. Returns (gh_global_opts, [topic, action,
        ...rest]) — e.g. ([], ["pr", "create", "--repo", ...]).

    is_gh_subcommand(tokens, *verbs) -> bool
        Yes/no convenience for "does this token list contain a `gh <verb1>
        <verb2> ...` invocation?". Walks the token stream allowing the
        match at any position. Use this when you only need the boolean,
        not the post-verb tail; use `find_gh_subcommand` when you need
        to inspect the tail.

    walk_flag_values(tokens, wanted) -> list[str]
        Walks `tokens` and returns the value of every flag in `wanted`,
        in source order. Handles both the two-token form (`--flag value`)
        and the equals form (`--flag=value`). Values inside another flag's
        value (e.g. inside `--body "...--flag X..."`) are correctly
        ignored because they arrive as a SINGLE shlex token, never
        preceded by a flag from `wanted`.

    first_flag_value(command, wanted, *, regex_fallback=True) -> str | None
        Convenience wrapper: tokenizes `command` via `tokenize()` and
        returns the first value from `walk_flag_values()`. If tokenize
        fails AND `regex_fallback=True` (the default), falls back to a
        boundary-anchored regex per the public tokenize contract.
        Security-critical matchers should pass `regex_fallback=False`
        to fail closed on parse failure.

    extract_dash_c_pairs(segment) -> list[tuple[str, str]]
        Walks a tokenized git segment and returns (key, value) pairs for
        every `-c key=value` global option, in source order. shlex has
        already unquoted values, so a simple `split('=', 1)` is correct.

        Repeated-key contract: `git -c user.name=A -c user.name=B commit`
        is legal (last wins per git semantics). This helper returns ALL
        pairs in source order; callers needing last-wins semantics can
        do `dict(extract_dash_c_pairs(...))` (later keys overwrite
        earlier in dict construction). Do not rely on first-occurrence
        unless you handle dedup yourself.

    resolve_tool_cwd(input_data) -> str
        Returns input_data["cwd"] if the harness supplied it, else
        os.getcwd(). The Claude Code harness sets `cwd` on the hook input
        for tool calls that run from a known cwd; subprocess calls that
        want to operate on the *user's* cwd (not the hook's parent process
        cwd) should use this to anchor `subprocess.run(..., cwd=...)`.

    resolve_invocation_cwd(input_data) -> str
        Like resolve_tool_cwd, but FIRST tries to recover the directory the
        command actually runs in by extracting a leading `cd <dir>` segment
        from the Bash command string. This closes the #521 residual: for a
        worktree subagent the harness `cwd` field is captured at agent-spawn
        time (the orchestrator's dir), NOT the subagent's dir after it has
        `cd`'d into its worktree, and subsequent `cd` calls do not propagate
        back to the hook's view of `cwd`. When the triggering command is
        `cd /path/to/worktree && gh pr create ...`, the cd target is the
        only in-band signal that recovers the real repo. Falls back to
        resolve_tool_cwd (stdin cwd → os.getcwd()) when no leading `cd`
        is present. Only absolute existing directories are honored; relative
        cd targets are ambiguous (they'd be relative to the already-wrong
        stdin cwd) so they are ignored.

    resolve_repo_short_name(input_data, *, git_runner=None) -> str | None
        Resolve the GitHub repository NAME (e.g. `noorinalabs-main`) from the
        invocation cwd's `origin` remote. This mirrors how `gh` itself
        resolves a `gh issue edit/create ...` invocation that OMITS `--repo`:
        it falls back to the ambient git context. Hooks that need the repo
        name to drive a GraphQL/REST call (e.g. the Wave-field sync and the
        kickoff-comment hooks) call this to recover the repo when the parsed
        command carried no `--repo` flag. Returns the last path segment of
        the `origin` URL with any trailing `.git` stripped, or None when the
        cwd is not a git repo / has no origin / the runner fails. The
        `git_runner(cwd) -> str | None` injection point lets tests avoid
        shelling out (#650).

    is_shutdown_request_message(message) -> bool
        True only if `message` is a structured shutdown_request JSON
        (dict-form OR str-form parseable to a dict with type==
        "shutdown_request"). Plain prose containing the substring is NOT
        a shutdown request — that was the #189 false-positive root.

Why not eval / parse the full shell grammar?
============================================

shlex.split + segment + command-position lookup is the 95% solution. Hooks
that match against a known shape (`git commit`, `gh pr create`, `git config`)
need exactly this. Full POSIX shell parsing is overkill and would re-introduce
the parser-correctness debt the regexes had.

When shlex.split fails (malformed quotes), callers MUST fall back to a regex
or fail-open (return None to allow the command). Never crash on parse error.

Promotion provenance
====================

Sibling-bug cluster (P3W4 Tier-2): #226 #227 #223 #216 #188 #144 #189.
Tracking PR consolidates the parser into one tested helper and refactors
five hooks (validate_commit_identity, validate_branch_freshness,
block_git_config, block_no_verify, block_shutdown_without_retro).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from typing import Iterator

# Optional structural dependency (#748 D3b). bashlex gives a real Bash-AST
# parse for the commit-identity matcher. It is imported defensively so a
# freshly-pulled checkout's hooks keep working with ZERO install step (the same
# zero-setup-on-pull guarantee as the git-transferable memory) — if bashlex is
# absent the parser silently degrades to the shlex/regex path and the consuming
# hook surfaces a single stderr warning. bashlex.* missing stubs are handled by
# the `[[tool.mypy.overrides]]` entry in pyproject.toml.
try:
    import bashlex
    from bashlex import ast as bashlex_ast

    _BASHLEX_AVAILABLE = True
except ImportError:  # pragma: no cover - degraded mode is exercised via monkeypatch
    bashlex = None
    bashlex_ast = None
    _BASHLEX_AVAILABLE = False

# Shell control tokens that segment a compound command. Any of these,
# appearing as their OWN token after shlex.split, separates one pipeline
# segment from the next.
_SEGMENT_OPS = {";", "&&", "||", "|"}

# Match KEY=value env-var assignment at command position. Must start with a
# letter or underscore and contain only word chars before the '='. shlex has
# already de-quoted any quoted value, so the value half is just "everything
# after the first =".
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*=")

# Heredoc opener: <<-?\s*['"]?DELIM['"]? on a line, then any content, then
# the bare DELIM word terminating it. Supports the four shell variants
# (<<EOF, <<'EOF', <<"EOF", <<-EOF). The `<<-` tabs-stripping form allows
# leading tabs on the closing delimiter line, so we match optional `\t*`
# before \1 in the closer position.
_HEREDOC_RE = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?.*?\n.*?\n\t*\1\b",
    re.DOTALL,
)

# git global options that consume a value (two-token form). Equals-form
# (e.g. `--git-dir=path`) is handled separately as a single token.
_GIT_VALUE_GLOBALS = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path"}

# git global boolean options (no value).
_GIT_BOOL_GLOBALS = {
    "--no-pager",
    "-p",
    "--paginate",
    "--no-replace-objects",
    "--bare",
    "--no-optional-locks",
}

# Backslash + newline = POSIX line continuation. The Claude Code harness passes
# the raw bash command string including these sequences. shlex.split(posix=True)
# does NOT consume them as line continuations — instead it emits the trailing
# newline as a standalone token (issue #287), breaking command-position detection.
_LINE_CONTINUATION_RE = re.compile(r"\\\n[ \t]*")


def tokenize(cmd: str) -> list[str] | None:
    """shlex.split the command. Return None on parse error (unbalanced quote).

    Normalizes POSIX line-continuation sequences (backslash + newline) to a
    single space before tokenizing. Without this, shlex.split(posix=True)
    emits the trailing newline as a stray token that breaks command-position
    detection (issue #287).
    """
    try:
        return shlex.split(_LINE_CONTINUATION_RE.sub(" ", cmd), posix=True)
    except ValueError:
        return None


def strip_heredocs(cmd: str) -> str:
    """Remove all heredoc bodies. Iterates until no more matches (handles nested)."""
    prev = None
    cur = cmd
    while prev != cur:
        prev = cur
        cur = _HEREDOC_RE.sub("", cur)
    return cur


def iter_command_segments(tokens: list[str]) -> Iterator[list[str]]:
    """Split tokens on `;`, `&&`, `||`, `|` and strip leading KEY=val env vars.

    Each yielded segment is a non-empty list of tokens representing one
    command in the pipeline. Empty segments (e.g. trailing `;`) are skipped.
    """
    if not tokens:
        return

    cur: list[str] = []
    for tok in tokens:
        if tok in _SEGMENT_OPS:
            if cur:
                stripped = _strip_leading_env_assignments(cur)
                if stripped:
                    yield stripped
                cur = []
            continue
        cur.append(tok)
    if cur:
        stripped = _strip_leading_env_assignments(cur)
        if stripped:
            yield stripped


def _strip_leading_env_assignments(segment: list[str]) -> list[str]:
    """Drop leading KEY=value tokens from a segment (one-shot env vars)."""
    i = 0
    while i < len(segment) and _ENV_ASSIGN_RE.match(segment[i]):
        i += 1
    return segment[i:]


def bashlex_available() -> bool:
    """True iff the optional bashlex Bash-AST parser imported successfully.

    Read at call time so tests can monkeypatch `_BASHLEX_AVAILABLE` to simulate
    a bare checkout. The commit-identity hook uses this to decide between the
    structural (bashlex) parse and the shlex/regex degraded fallback.
    """
    return _BASHLEX_AVAILABLE


def iter_command_segments_ast(command: str) -> list[list[str]] | None:
    """Structural (bashlex) extraction of command-position token segments.

    Parses `command` into a real Bash AST and walks every CommandNode —
    descending through `&&`/`;`/`||` lists, `|` pipelines, `$(...)`/backtick
    command substitutions, and compound (`{ }`, `( )`, if/while/for) bodies.
    Each yielded segment is the command's WordNode values in source order;
    `KEY=value` env-var prefixes arrive as AssignmentNodes and are naturally
    excluded because only `word`-kind parts are collected — matching the
    leading-env-strip behaviour of the shlex-based `iter_command_segments`.

    Token shape is identical to the shlex path: `-c user.name="A B"` yields
    `["-c", "user.name=A B"]`, so the existing `find_git_subcommand` /
    `extract_dash_c_pairs` consumers work unchanged on AST segments.

    Returns:
      list[list[str]] — the segments (an empty list when the input parsed but
                        held no command, e.g. a bare comment).
      None            — bashlex is unavailable (degraded mode) OR the command
                        failed to parse. The caller MUST fall back to the
                        shlex/regex path; per the tokenize() security contract
                        a None here is NEVER treated as "allow".
    """
    if not _BASHLEX_AVAILABLE:
        return None
    try:
        trees = bashlex.parse(command)
    except Exception:
        # Any bashlex failure — unbalanced quotes, an unsupported construct,
        # etc. — signals the caller to fall back. Fallback is always safe, so a
        # broad catch matches the resilience posture of `tokenize` returning
        # None on a parse error (never crash the hook).
        return None

    segments: list[list[str]] = []

    class _SegmentCollector(bashlex_ast.nodevisitor):
        def visitcommand(self, n, parts):
            tokens = [p.word for p in parts if p.kind == "word"]
            if tokens:
                segments.append(tokens)
            return True  # keep descending into command substitutions, compounds, ...

    collector = _SegmentCollector()
    for tree in trees:
        collector.visit(tree)
    return segments


def _is_equals_form_global(tok: str) -> bool:
    """True if `tok` is the equals-form of a value-taking git global.

    Examples that return True: `-c=user.name=foo`, `--git-dir=.git`,
    `--work-tree=/path`. We only care about the prefix; the value half is
    irrelevant for the skip decision.
    """
    return (
        tok.startswith("-c=")
        or tok.startswith("-C=")
        or tok.startswith("--git-dir=")
        or tok.startswith("--work-tree=")
        or tok.startswith("--namespace=")
        or tok.startswith("--exec-path=")
    )


def find_git_subcommand(segment: list[str]) -> tuple[list[str], list[str]] | None:
    """If `segment` is a `git ...` invocation, return (global_opts, [subcmd, ...]).

    Skips git global options:
      -c key=value          (consumed as one shlex token, possibly quoted)
      -C path
      --git-dir=path / --git-dir path
      --work-tree=path / --work-tree path
      --no-pager / -p / --paginate / --no-replace-objects   (no value)

    Returns None if `segment` is empty, doesn't start with `git`, or doesn't
    have a subcommand after the global-option run.
    """
    if not segment or segment[0] != "git":
        return None

    globals_: list[str] = []
    i = 1
    n = len(segment)
    while i < n:
        tok = segment[i]
        if tok in _GIT_BOOL_GLOBALS:
            globals_.append(tok)
            i += 1
            continue
        if tok in _GIT_VALUE_GLOBALS:
            globals_.append(tok)
            if i + 1 < n:
                globals_.append(segment[i + 1])
                i += 2
            else:
                i += 1
            continue
        if _is_equals_form_global(tok):
            globals_.append(tok)
            i += 1
            continue
        # First non-option token is the subcommand.
        return globals_, segment[i:]
    return None


def find_gh_subcommand(segment: list[str]) -> tuple[list[str], list[str]] | None:
    """If `segment` is a `gh ...` invocation, return ([], [topic, action, ...]).

    `gh` has no pre-subcommand global options worth skipping for the matchers
    in this codebase, so this is a thin shape-mirror of `find_git_subcommand`.
    """
    if not segment or segment[0] != "gh":
        return None
    if len(segment) < 2:
        return None
    return [], segment[1:]


def is_gh_subcommand(tokens: list[str], *verbs: str) -> bool:
    """Return True if `tokens` begins a `gh <verbs[0]> <verbs[1]> ...` invocation.

    Walks `tokens` looking for `gh` followed by the supplied verb sequence in
    order, allowing them to appear at any position (not just the start of the
    list). Used by hooks that want a yes/no "does this command invoke
    `gh issue create`?" check without needing the post-verb token tail.

    Example:
        is_gh_subcommand(tokens, "issue", "create")  # True for `gh issue create ...`
        is_gh_subcommand(tokens, "pr", "create")     # True for `gh pr create ...`
    """
    if not verbs:
        return False
    target = ("gh",) + verbs
    n = len(tokens)
    span = len(target)
    if n < span:
        return False
    for i in range(n - span + 1):
        if tuple(tokens[i : i + span]) == target:
            return True
    return False


def walk_flag_values(tokens: list[str], wanted: set[str]) -> list[str]:
    """Return values for `wanted` flag names, only when they appear as flags.

    A token is treated as a wanted-flag value only if the immediately
    preceding token is exactly one of `wanted` (e.g. `--label`). The
    `--flag=value` equals form is also handled. Values inside other flags
    (e.g. inside the value of `--body`) are ignored because they are a
    SINGLE shlex token, never preceded by a flag from `wanted`.

    Order is preserved: values appear in the order they were encountered
    in the token stream.
    """
    values: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok in wanted:
            if i + 1 < n:
                values.append(tokens[i + 1])
                i += 2
                continue
            i += 1
            continue
        matched = False
        for flag in wanted:
            if tok.startswith(flag + "="):
                values.append(tok[len(flag) + 1 :])
                matched = True
                break
        if matched:
            i += 1
            continue
        i += 1
    return values


def first_flag_value(command: str, wanted: set[str], *, regex_fallback: bool = True) -> str | None:
    """Tokenize `command` and return the first value for any flag in `wanted`.

    Returns None if no wanted flag is present. If shlex tokenization fails
    (malformed quotes) and `regex_fallback=True` (default), falls back to a
    boundary-anchored regex search that tries longer flag names first so
    `--repo` is preferred over a hypothetical shorter prefix collision.
    With `regex_fallback=False`, returns None on tokenize failure (the
    fail-closed shape used by security-critical matchers).
    """
    tokens = tokenize(command)
    if tokens is None:
        if not regex_fallback:
            return None
        for flag in sorted(wanted, key=len, reverse=True):
            pattern = rf"(?:^|\s){re.escape(flag)}(?:=|\s+)(\S+)"
            match = re.search(pattern, command)
            if match:
                return match.group(1)
        return None
    values = walk_flag_values(tokens, wanted)
    return values[0] if values else None


def extract_dash_c_pairs(segment: list[str]) -> list[tuple[str, str]]:
    """Walk a git segment and yield (key, value) for every `-c key=value`.

    Handles `-c k=v` (two tokens) and `-c=k=v` (one token, rare). shlex has
    already unquoted the value half, so `-c user.name="A B"` arrives here as
    `["-c", "user.name=A B"]` (two tokens; the inner `=` is the key/value
    separator handled by `split("=", 1)`).
    """
    pairs: list[tuple[str, str]] = []
    if not segment or segment[0] != "git":
        return pairs

    i = 1
    n = len(segment)
    while i < n:
        tok = segment[i]
        if tok == "-c" and i + 1 < n:
            kv = segment[i + 1]
            if "=" in kv:
                key, value = kv.split("=", 1)
                pairs.append((key, value))
            i += 2
            continue
        if tok.startswith("-c=") and "=" in tok[3:]:
            kv = tok[3:]
            key, value = kv.split("=", 1)
            pairs.append((key, value))
            i += 1
            continue
        # Other value-taking globals — skip the value too.
        if tok in _GIT_VALUE_GLOBALS:
            i += 2
            continue
        if _is_equals_form_global(tok):
            i += 1
            continue
        if tok in _GIT_BOOL_GLOBALS:
            i += 1
            continue
        # First non-option token is the subcommand — done collecting -c pairs.
        break
    return pairs


def resolve_tool_cwd(input_data: dict) -> str:
    """Return the cwd for the tool call.

    The Claude Code harness sets `cwd` on the hook input for tool calls. When
    present, it is the user's actual working directory at tool-call time —
    which is what hooks should reason about, NOT the hook's parent process
    cwd (which is whatever the agent was launched from, often the wrong repo
    for a worktree subagent — see #144).

    Falls back to os.getcwd() if the field is missing or empty (older
    harness versions, manual invocations).
    """
    cwd = input_data.get("cwd")
    if cwd and isinstance(cwd, str):
        return cwd
    return os.getcwd()


def extract_leading_cd_target(command: str) -> str | None:
    """Return the directory of the last `cd <dir>` that precedes other work.

    Walks the command's pipeline segments (see iter_command_segments) and
    records the target of every `cd <dir>` segment, returning the last one.
    Only honors a single-argument absolute `cd` target — relative targets
    are ambiguous because they'd resolve against the (wrong) stdin cwd, and
    multi-arg `cd` (e.g. `cd -P x`) is rare enough to skip rather than
    mis-parse.

    Returns None when the command does not tokenize, has no `cd`, or the
    cd target is not an absolute path. The caller is responsible for
    checking the path actually exists.

    This is the in-band recovery signal for the worktree-subagent cwd-anchor
    bug (#521): `cd /worktree && gh pr create` carries the real cwd in the
    command itself even though the harness `cwd` field points at the
    orchestrator's spawn-time directory.
    """
    tokens = tokenize(command)
    if tokens is None:
        return None
    target: str | None = None
    for segment in iter_command_segments(tokens):
        if len(segment) == 2 and segment[0] == "cd" and segment[1].startswith("/"):
            target = segment[1]
    return target


def resolve_invocation_cwd(input_data: dict) -> str:
    """Resolve the directory the triggering command actually runs in.

    Priority:
      1. An absolute, existing `cd <dir>` target extracted from the command
         string (recovers a worktree subagent's real cwd — #521).
      2. resolve_tool_cwd(input_data) — stdin `cwd` then os.getcwd().

    Use this (rather than resolve_tool_cwd) for any hook that derives repo
    IDENTITY from cwd — i.e. anything that runs `git remote get-url origin`
    or `git rev-parse` to decide which GitHub repo a command targets. The
    plain resolve_tool_cwd is fine for hooks that only need *a* git context
    and don't care about cross-repo misattribution.
    """
    command = input_data.get("tool_input", {}).get("command", "")
    if isinstance(command, str) and command:
        cd_target = extract_leading_cd_target(command)
        if cd_target and os.path.isdir(cd_target):
            return cd_target
    return resolve_tool_cwd(input_data)


def _default_origin_url_runner(cwd: str) -> str | None:
    """Return the `origin` remote URL for the git repo at `cwd`, or None.

    Shells out to `git -C <cwd> remote get-url origin`. Any failure (not a
    git repo, no `origin` remote, git missing) yields None so the caller
    treats the repo as unresolvable rather than crashing.
    """
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def resolve_repo_short_name(input_data: dict, *, git_runner=None) -> str | None:
    """Resolve the GitHub repo NAME from the invocation cwd's `origin` remote.

    When a `gh issue edit/create` command omits `--repo`, gh resolves the
    target repository from the ambient git context (the cwd's `origin`
    remote). Hooks that need the repo name to drive a GraphQL/REST call must
    mirror that resolution. Returns the last path segment of the `origin`
    URL with any trailing `.git` stripped — for both scp-form and https-form
    URLs:

        git@github.com:noorinalabs/noorinalabs-main.git  -> noorinalabs-main
        https://github.com/noorinalabs/noorinalabs-main   -> noorinalabs-main

    Returns None when the cwd is not a git repo, has no `origin` remote, or
    the runner otherwise fails. The cwd is resolved via
    `resolve_invocation_cwd` so a worktree-subagent's real dir is used (the
    `cd <dir> && ...` recovery path, #521).

    `git_runner(cwd) -> str | None` is the injection point for tests; the
    default shells out to `git -C <cwd> remote get-url origin`.
    """
    cwd = resolve_invocation_cwd(input_data)
    runner = git_runner or _default_origin_url_runner
    url = runner(cwd)
    if not url:
        return None
    name = url.strip().rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[: -len(".git")]
    return name or None


def is_shutdown_request_message(message) -> bool:
    """True iff `message` is a structured shutdown_request, NOT prose containing the phrase.

    Accepts either:
      - dict with `type: "shutdown_request"` (already-parsed JSON)
      - str whose JSON-parsed object has `type: "shutdown_request"`

    Plain text messages are NEVER treated as shutdown requests, even if they
    contain the literal substring. Issue #189: subagents writing
    "standing down" / "Acknowledge" prose were tripping the substring matcher.
    """
    if isinstance(message, dict):
        return message.get("type") == "shutdown_request"
    if not isinstance(message, str):
        return False
    s = message.strip()
    if not s.startswith("{"):
        return False
    try:
        obj = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return False
    return isinstance(obj, dict) and obj.get("type") == "shutdown_request"
